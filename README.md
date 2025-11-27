# MUSTer MCP Server

> An MCP server prepared for MUSTer. Enables LLM interaction with the M.U.S.T. (Macau University of Science and Technology) campus system.

![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![MCP](https://img.shields.io/badge/MCP-Server-orange)
![Package Manager](https://img.shields.io/badge/uv-fast-purple)

English | [简体中文](README_CN.md)

Now, LLMs can automatically log in to Wemust and Moodle, retrieve class schedules, query course PPTs, assignments, view to-do items, download course materials, and automatically open pages.


## Tools Overview
- `get_class_schedule`: **Check Schedule**. Directly fetches this week's class arrangements.
- `get_pending_events`: **Check DDL**. Lists upcoming assignments and to-dos on Moodle.
- `get_all_courses`: **List Courses**. Gets the names and links of all courses on the Moodle dashboard.
- `get_course_content`: **Check Details**. Reads assignment or quiz information within specific courses.
- `download_resource`: **Download Courseware**. Downloads files from Moodle resource pages (especially convenient for bulk downloading PPTs). This also allows the large model to select a specific folder.
- `open_URL_with_authorization`: **Open without password**. Directly pops up an automatically logged-in Chrome window, no need to manually enter account password, automatically opens the specified page.
- `get_current_time`: Gets the current system timestamp.

## Environmental Dependencies
- Python 3.12+
- Locally available Chrome/Chromedriver (for Selenium).
- Environment variables: `MUSTER_USERNAME`, `MUSTER_PASSWORD` (required); `MUSTER_DOWNLOAD_PATH` (optional, default download path, defaults to `~/Downloads`).

## Installation
1) Install [uv](https://docs.astral.sh/uv/) (a fast Python package manager).
2) Clone the repository and install dependencies:
```bash
git clone https://github.com/Cosmostima/MUSTer_MCP

cd MUSTer_MCP

uv sync
```

## MCP Client Configuration Example
```json
{
  "mcpServers": {
    "muster": {
      "command": "UV_PATH_HERE",
      "args": [
        "--directory",
        "MCP_FOLDER_PATH_HERE",
        "run",
        "main.py"
      ],
      "env": {
              "MUSTER_USERNAME": "YOUR_ID_HERE",
              "MUSTER_PASSWORD": "YOUR_PASSWORD_HERE"
      }
    }
}
```

If you need to customize the default download path, you can add `MUSTER_DOWNLOAD_PATH` :

```json
{
  "mcpServers": {
    "muster": {
      "command": "UV_PATH_HERE",
      "args": [
        "--directory",
        "MCP_FOLDER_PATH_HERE",
        "run",
        "main.py"
      ],
      "env": {
              "MUSTER_USERNAME": "YOUR_ID_HERE",
              "MUSTER_PASSWORD": "YOUR_PASSWORD_HERE",
              "MUSTER_DOWNLOAD_PATH": "/Users/cosmos/Desktop/"
      }
    }
}
```