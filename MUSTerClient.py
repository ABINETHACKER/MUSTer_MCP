from dataclasses import dataclass
import json
import os
import requests
import tempfile
import urllib.parse
import threading
import time
import glob
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import time

MOODLE_URL = os.environ.get("MOODLE_URL", "https://moodle.must.edu.mo/")
SCHEDULE_URL = os.environ.get(
    "SCHEDULE_URL",
    "https://classtimetable-coes-wmweb.must.edu.mo/my-class-timetable-student",
)
USERNAME = os.environ.get("MUSTER_USERNAME")
PASSWORD = os.environ.get("MUSTER_PASSWORD")
DOWNLOAD_DIR = os.environ.get("MUSTER_DOWNLOAD_PATH", os.path.expanduser("~/Downloads"))

if not USERNAME or not PASSWORD:
    raise RuntimeError(
        "Please set MUSTER_USERNAME and MUSTER_PASSWORD in the environment:)"
    )

@dataclass
class Course:
    name: str
    url: str
    id: str = ""

@dataclass
class Assignment:
    name: str
    type: str
    url: str
    due_date: str = ""
    course: str = ""

@dataclass
class Event:
    name: str
    due_date: str
    event_type: str
    course: str
    course_url: str
    url: str = ""
    description: str = ""


class MUSTerClientWithHead:
    def __init__(self):
        self.driver = None
        self.logged_in = False
        self.setup_driver()

    def _ensure_driver(self):
        """Ensure the headed driver is alive; recreate if it was closed or crashed."""
        alive = False
        if self.driver:
            try:
                _ = self.driver.title  # lightweight liveness check
                if getattr(self.driver, "session_id", None):
                    alive = True
            except WebDriverException:
                self.driver = None
                self.logged_in = False

        if not alive:
            self.setup_driver()
            self.logged_in = False

    def setup_driver(self):        
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        self.driver = webdriver.Chrome(options=chrome_options)

    def login(self) -> bool:
        self._ensure_driver()
        try:
            self.driver.get(MOODLE_URL)
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "checkboxByPrivacyPolicy"))
            ).click()
            self.driver.find_element(By.ID, "username").send_keys(USERNAME)
            self.driver.find_element(By.ID, "password").send_keys(PASSWORD)
            self.driver.find_element(By.ID, "submitButton").click()
            WebDriverWait(self.driver, 10).until(
                lambda driver: "dashboard" in driver.current_url.lower() or "my" in driver.current_url.lower()
            )
            self.logged_in = True
            return True
        except TimeoutException:
            print("Login failed: Timeout while waiting for page to load.")
            return False
        except Exception as e:
            print(f"An unexpected error occurred during login: {e}")
            return False

    def openUrl(self, url: str):
        if not self.logged_in:
            if not self.login():
                raise Exception("Failed to login to Moodle")
        self.driver.get(url)
        return self.driver
    
    def close(self):
        """Close the browser session."""
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.logged_in = False


class MUSTerClient:
    """
    Handles all interactions with Moodle and Wemust.
    """
    def __init__(self):
        self.driver = None
        self.logged_in = False
        self.session_cookies: Optional[List[Dict[str, Any]]] = None

        self.SESSION_TIMEOUT = 60
        self.last_activity_time = None
        self.guardian_thread = None
        self.prewarm_thread = None
        self.prewarm_started = False

        self.lock = threading.Lock()

        # Prewarm a session on startup to speed up first call.
        self.start_prewarm()

    def _ensure_driver(self):
        """Ensure driver exists and is alive; recreate if needed."""
        with self.lock:
            alive = False
            if self.driver:
                try:
                    # A lightweight call to verify session liveness
                    _ = self.driver.title  # type: ignore[attr-defined]
                    if getattr(self.driver, "session_id", None):
                        alive = True
                except WebDriverException:
                    self.driver = None
                    self.logged_in = False

            if not alive:
                self.setup_driver()
                self.logged_in = False

    def _guardian(self):
        while True:
            time.sleep(30)

            with self.lock:
                if not self.driver:
                    break
                if self.last_activity_time is None:
                    self.last_activity_time = time.time()
                    continue
                idle_time = time.time() - self.last_activity_time
                if idle_time > self.SESSION_TIMEOUT:
                    print("Session timed out. Closing browser.")
                    self.driver.quit()
                    self.driver = None
                    self.logged_in = False
                    break

    def start_guardian(self):
        if self.guardian_thread is None or not self.guardian_thread.is_alive():
            self.guardian_thread = threading.Thread(target=self._guardian, daemon=True)
            self.guardian_thread.start()

    def start_prewarm(self):
        if self.prewarm_started:
            return
        self.prewarm_started = True
        self.prewarm_thread = threading.Thread(target=self._prewarm_login, daemon=True)
        self.prewarm_thread.start()

    def _prewarm_login(self):
        try:
            self.login()
        except Exception as e:
            print(f"Prewarm login failed: {e}")

    def _load_cookies(self) -> bool:
        """Try to restore a logged-in session from ookies."""
        if not self.session_cookies or not self.driver:
            return False
        try:
            self.driver.get(MOODLE_URL)
            for cookie in self.session_cookies:
                self.driver.add_cookie({k: v for k, v in cookie.items() if k in {"name", "value", "domain", "path", "expiry", "secure", "httpOnly"}})
            self.driver.get(f"{MOODLE_URL}/my")
            WebDriverWait(self.driver, 5).until(
                lambda driver: "login" not in driver.current_url.lower()
            )
            return True
        except Exception:
            return False

    def _save_cookies(self):
        """Persist current session cookies in memory for reuse within the MCP lifecycle."""
        if not self.driver:
            return
        try:
            self.session_cookies = self.driver.get_cookies()
        except Exception:
            pass

    def heartBeat(self):
        with self.lock:
            self.last_activity_time = time.time()

    def setup_driver(self):
        """Setup Chrome driver"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        self.driver = webdriver.Chrome(options=chrome_options)
        self.last_activity_time = time.time()
        self.start_guardian()
    

    def login(self) -> bool:
        """Login to Moodle"""
        self._ensure_driver()

        try:
            if self._load_cookies():
                self.logged_in = True
                self.heartBeat()
                return True
        except Exception:
            pass

        try:
            self.driver.get(SCHEDULE_URL)
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "checkboxByPrivacyPolicy"))
            ).click()
            self.driver.find_element(By.ID, "username").send_keys(USERNAME)
            self.driver.find_element(By.ID, "password").send_keys(PASSWORD)
            self.driver.find_element(By.ID, "submitButton").click()

            WebDriverWait(self.driver, 10).until(
                lambda driver: "dashboard" in driver.current_url.lower() or "my" in driver.current_url.lower()
            )
            self.logged_in = True
            self.heartBeat()
            self._save_cookies()
            return True
        except TimeoutException:
            print("Login failed: Timeout while waiting for page to load.")
            return False
        except Exception as e:
            print(f"An unexpected error occurred during login: {e}")
            return False
    
    def get_courses(self) -> List[Course]:
        """Get all available courses from Moodle."""
        
        self._ensure_driver()
        self.heartBeat()
        if not self.logged_in:
            if not self.login():
                raise Exception("Login required to get courses.")
        

        try:
            self.driver.get(f"{MOODLE_URL}/my")
            WebDriverWait(self.driver, 10).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "li.list-group-item.course-listitem a.aalink.coursename")) > 0
            )
            self._wait_stable_count(self.driver, "li.list-group-item.course-listitem a.aalink.coursename", stable_for=1.0)
            items = self.driver.find_elements(By.CSS_SELECTOR, "li.list-group-item.course-listitem")
            courses = []
            for li in items:
                try:
                    a = li.find_element(By.CSS_SELECTOR, "a.aalink.coursename")
                    url = a.get_attribute("href") or ""
                    if url:
                        text_lines = [line for line in a.text.splitlines() if line.strip()]
                        course_name = text_lines[1] if len(text_lines) > 1 else text_lines[0] if text_lines else ""
                        courses.append(Course(name=course_name, url=url))
                except Exception:
                    continue
            self.heartBeat()
            return courses
        except TimeoutException:
            print("Timeout while waiting for courses to load.")
            return []
        except Exception as e:
            print(f"An error occurred while getting courses: {e}")
            return []

    def get_course_content(self, course_url: str) -> List[Assignment]:
        """Get all assignments and content from a specific course."""
        self._ensure_driver()
        self.heartBeat()
        if not self.logged_in:
            if not self.login():
                raise Exception("Login required to get courses.")

        try:
            self.driver.get(course_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".course-content, .topics, li.section"))
            )
            assignments = []
            sections = self.driver.find_elements(By.CSS_SELECTOR, "li.section.main")
            for section in sections:
                try:
                    section_title_element = section.find_element(By.CSS_SELECTOR, ".sectionname span a, .sectionname a")
                    section_title = section_title_element.text.strip()
                    if section_title.lower() in ["general", ""]:
                        continue

                    activities = section.find_elements(By.CSS_SELECTOR, ".activity")
                    for activity in activities:
                        try:
                            activity_link = activity.find_element(By.CSS_SELECTOR, ".activityinstance a")
                            instance_name_element = activity_link.find_element(By.CSS_SELECTOR, ".instancename")
                            activity_name = " ".join(instance_name_element.text.strip().split())
                            activity_url = activity_link.get_attribute('href')
                            activity_type = "resource"
                            if "forum" in activity.get_attribute("class"):
                                activity_type = "forum"
                            elif "assign" in activity.get_attribute("class"):
                                activity_type = "assignment"
                            elif "quiz" in activity.get_attribute("class"):
                                activity_type = "quiz"
                            elif "resource" in activity.get_attribute("class"):
                                activity_type = "file"

                            if activity_name and activity_url:
                                hierarchical_name = f"{section_title} > {activity_name}"
                                assignments.append(Assignment(
                                    name=hierarchical_name,
                                    type=activity_type,
                                    url=activity_url,
                                    course=section_title
                                ))
                        except Exception:
                            continue
                except Exception:
                    continue
            self.heartBeat()
            return assignments
        except TimeoutException:
            print(f"Timeout while waiting for course content to load for url: {course_url}")
            return []
        except Exception as e:
            print(f"An error occurred while getting course content: {e}")
            return []

    def get_pending_events(self) -> List[Event]:
        """Get all pending events and assignment deadlines with detailed information."""
        
        self._ensure_driver()
        self.heartBeat()
        if not self.logged_in:
            if not self.login():
                raise Exception("Login required to get events.")

        events = []
        try:
            # Navigate to upcoming events page
            self.driver.get(f"{MOODLE_URL}/calendar/view.php?view=upcoming")

            # Wait for events to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-type='event']"))
            )

            # Find all event containers
            event_elements = self.driver.find_elements(By.CSS_SELECTOR, "[data-type='event']")

            for element in event_elements:
                try:
                    # Extract event name from header
                    event_name = ""
                    try:
                        event_name = element.find_element(By.CSS_SELECTOR, "h3.name").text.strip()
                    except Exception:
                        # Fallback to data attribute
                        event_name = element.get_attribute("data-event-title") or ""

                    if not event_name:
                        continue

                    # Extract due date/time
                    due_date = ""
                    try:
                        # Find the row containing the "When" icon
                        date_row = element.find_element(By.XPATH, ".//div[@class='row'][.//i[@title='When']]")
                        date_col = date_row.find_element(By.CSS_SELECTOR, ".col-11")
                        due_date = date_col.text.strip()
                    except Exception:
                        pass

                    # Extract event type
                    event_type = ""
                    try:
                        # Find the row containing the "Event type" icon
                        type_row = element.find_element(By.XPATH, ".//div[@class='row mt-1'][.//i[@title='Event type']]")
                        type_col = type_row.find_element(By.CSS_SELECTOR, ".col-11")
                        event_type = type_col.text.strip()
                    except Exception:
                        # Fallback to data attribute
                        event_type = element.get_attribute("data-event-eventtype") or "unknown"

                    # Extract course name and URL
                    course_name = ""
                    course_url = ""
                    try:
                        # Find the row containing the "Course" icon
                        course_row = element.find_element(By.XPATH, ".//div[@class='row mt-1'][.//i[@title='Course']]")
                        course_link = course_row.find_element(By.CSS_SELECTOR, ".col-11 a")
                        course_name = course_link.text.strip()
                        course_url = course_link.get_attribute("href") or ""
                    except Exception:
                        pass

                    # Extract description (if available)
                    description = ""
                    try:
                        desc_element = element.find_element(By.CSS_SELECTOR, ".description-content")
                        description = desc_element.text.strip()
                    except Exception:
                        pass

                    # Extract activity URL
                    activity_url = ""
                    try:
                        activity_link = element.find_element(By.CSS_SELECTOR, ".card-footer a.card-link")
                        activity_url = activity_link.get_attribute("href") or ""
                    except Exception:
                        pass

                    # Create Event object
                    event = Event(
                        name=event_name,
                        due_date=due_date,
                        event_type=event_type,
                        course=course_name,
                        course_url=course_url,
                        url=activity_url,
                        description=description
                    )
                    events.append(event)

                except Exception as e:
                    print(f"Error parsing individual event: {e}")
                    continue

        except TimeoutException:
            print("Timeout while waiting for events to load")
        except Exception as e:
            print(f"Error retrieving pending events: {e}")

        self.heartBeat()
        return events

    def download_resource(self, resource_url: str, download_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Download resource(s) from Moodle using the authenticated session."""

        resolved_download_path = download_path or DOWNLOAD_DIR
        self._ensure_driver()

        if not self.logged_in:
            if not self.login():
                raise Exception("Login required to download resources.")
        

        self.heartBeat()
        try:
            # Navigate to the resource page to get the actual download URL
            self.driver.get(resource_url)
            
            # Wait for the page to load and find download links
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[onclick*='target='], a[href*='pluginfile.php']"))
            )

            # Find all direct download links
            download_links = self.driver.find_elements(By.CSS_SELECTOR, "a[onclick*='target='], a[href*='pluginfile.php']")
            if not download_links:
                return {"error": "No download links found on the resource page"}
            
            # Get cookies from Selenium session for requests
            cookies = {}
            for cookie in self.driver.get_cookies():
                cookies[cookie['name']] = cookie['value']
            self.heartBeat()
            # Download headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            self.heartBeat()
            downloaded_files = []
            skipped_files = []
            errors = []
            self.heartBeat()
            # Create download directory
            Path(resolved_download_path).mkdir(parents=True, exist_ok=True)
            self.heartBeat()
            for i, link in enumerate(download_links):
                try:
                    download_url = link.get_attribute('href')
                    if not download_url or not download_url.startswith('http'):
                        continue
                    self.heartBeat()
                    # Skip non-file links
                    if 'pluginfile.php' not in download_url:
                        continue
                    self.heartBeat()
                    # Extract filename from URL or link text
                    filename = None
                    try:
                        # Try to get filename from the link text first
                        link_text = link.text.strip()
                        if link_text and '.' in link_text and len(link_text) < 200:
                            filename = link_text
                        else:
                            # Extract from URL
                            parsed_url = urllib.parse.urlparse(download_url)
                            path_parts = parsed_url.path.split('/')
                            for part in reversed(path_parts):
                                if '.' in part and len(part) < 200:
                                    filename = urllib.parse.unquote(part)
                                    break
                    except Exception:
                        pass
                    self.heartBeat()
                    if not filename:
                        filename = f"download_{int(time.time())}_{i}"

                    # Skip if file exists
                    file_path = Path(resolved_download_path) / filename
                    if file_path.exists():
                        skipped_files.append(filename)
                        continue
                    
                    # Download the file
                    response = requests.get(download_url, cookies=cookies, headers=headers, stream=True)
                    response.raise_for_status()
                    
                    # Write file
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    file_size = file_path.stat().st_size
                    
                    downloaded_files.append({
                        "filename": file_path.name,
                        "file_path": str(file_path),
                        "file_size": file_size,
                        "download_url": download_url
                    })
                    
                except requests.exceptions.RequestException as e:
                    errors.append(f"Failed to download {download_url}: {str(e)}")
                except Exception as e:
                    errors.append(f"Unexpected error downloading file {i+1}: {str(e)}")
            
            if downloaded_files or skipped_files:
                result = {
                    "success": True,
                    "total_downloaded": len(downloaded_files),
                    "total_skipped": len(skipped_files),
                    "downloaded_files": downloaded_files,
                    "skipped_files": skipped_files,
                }
                if errors:
                    result["errors"] = errors
                return result
            else:
                return {"error": f"No files were downloaded. Errors: {'; '.join(errors)}"}
            
        except Exception as e:
            return {"error": f"Unexpected error during download: {str(e)}"}


    def get_class_schedule(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get class schedule data from the MUST schedule website.
        Args:
            date: Optional date in YYYY-MM-DD format to filter results
        """      
        
        self._ensure_driver()
        
        self.heartBeat()

        if not self.logged_in:
            if not self.login():
                raise Exception("Login required to get courses.")
        
        # Create temporary download directory for Excel file
        with tempfile.TemporaryDirectory() as download_dir:
            try:
                # Update download preferences for this session
                self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {
                    'behavior': 'allow',
                    'downloadPath': download_dir
                })
                
                # Navigate to schedule page
                self.driver.get(SCHEDULE_URL)
                
                # Login if we're redirected to login page
                current_url = self.driver.current_url.lower()
                if "login" in current_url or "signin" in current_url:
                    try:
                        self.login()
                    except Exception as e:
                        return {"error": f"Failed to login to schedule system: {str(e)}"}
                
                self.heartBeat()
                
                # Export process
                export_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[span[text()='導出']]")
                    )
                )
                export_btn.click()
                
                # Expand collapse panel and download
                collapse_header = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'ivu-collapse-header') and contains(.,'下載任務')]"))
                )
                collapse_header.click()
                
                download_buttons = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.XPATH, "//button[.//span[contains(text(),'下载') or contains(text(),'下載')]]"))
                )
                
                WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(download_buttons[-1]))
                download_buttons[-1].click()
                time.sleep(1)
                
                self.heartBeat()
                
                # Cancel any dialogs
                try:
                    cancel_buttons = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_all_elements_located((By.XPATH, "//button[contains(., '取消')]"))
                    )
                    for button in cancel_buttons:
                        try:
                            button.click()
                        except:
                            pass
                except:
                    pass
                
                # Wait for file download
                timeout = 30
                start = time.time()
                
                while True:
                    xlsx_files = glob.glob(os.path.join(download_dir, "*.xlsx"))
                    if xlsx_files:
                        break
                    elif time.time() - start > timeout:
                        return {"error": "Failed to download schedule file within 30 seconds"}
                    else:
                        time.sleep(0.5)
                
                self.heartBeat()
                
                # Process the downloaded file
                xlsx_files = sorted(
                    glob.glob(os.path.join(download_dir, "*.xlsx")),
                    key=os.path.getmtime,
                    reverse=True
                )
                
                latest_xlsx = xlsx_files[0]
                df = pd.read_excel(latest_xlsx)
                schedule_data = df.to_dict('records')

                response = {
                    "success": True,
                    "total_classes": len(schedule_data),
                    "schedule": schedule_data
                }
                if date:
                    filtered = [cls for cls in schedule_data if isinstance(cls, dict) and cls.get("日期") == date]
                    response["schedule"] = filtered
                    response["total_classes"] = len(filtered)
                    if not filtered:
                        response["warning"] = "Only current week's schedule is available."
                return response
                
            except Exception as e:
                return {"error": f"Failed to fetch schedule data: {str(e)}"}
            finally:
                self.heartBeat()



    def close(self):
        """Close the browser session."""
        with self.lock:
            if self.driver:
                self.driver.quit()
                self.driver = None
                self.logged_in = False



    def _wait_stable_count(self,driver, css: str, stable_for=1.0, timeout=20, poll=0.25) -> int:
        deadline = time.time() + timeout
        last_n = -1
        stable_since = None
        while time.time() < deadline:
            n = len(driver.find_elements(By.CSS_SELECTOR, css))
            if n == last_n:
                if stable_since is None:
                    stable_since = time.time()
                if time.time() - stable_since >= stable_for:
                    return n
            else:
                last_n = n
                stable_since = None
            time.sleep(poll)
        return last_n
