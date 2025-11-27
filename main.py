"""
MUSTER MCP Server (stdio transport)

Provides access to Moodle courses, content, calendar events, resource download, and class schedule.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from MUSTerClient import MUSTerClient, MUSTerClientWithHead

server = Server("MUSTER")
muster_client = MUSTerClient()


def list_muster_tools() -> List[Tool]:
    """Return all tools with their input schema."""
    return [
        Tool(
            name="get_all_courses",
            description="Get all available courses and URLs from Moodle.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_course_content",
            description="Get all assignments/resources for a course by exact name (call get_all_courses first).",
            inputSchema={
                "type": "object",
                "properties": {
                    "course_name": {
                        "type": "string",
                        "description": "Course name exactly as returned by get_all_courses",
                    }
                },
                "required": ["course_name"],
            },
        ),
        Tool(
            name="get_pending_events",
            description="Get upcoming events and deadlines from Moodle calendar.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="download_resource",
            description="Download Moodle resource file(s) (PPT, PDF, etc.) from a URL. Supports saving to a custom local directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_url": {
                        "type": "string",
                        "description": "The exact Moodle resource URL to download from.",
                    },
                    "download_path": {
                        "type": ["string", "null"],
                        "description": "The absolute folder path string (e.g. '/Users/cosmos/Desktop'). \nIMPORTANT: This must be a STRING value, NOT a boolean. \nWRONG: true, false. \nRIGHT: '/path/to/folder'. \nIf not provided, it uses the default system download folder.",
                    },
                },
                "required": ["resource_url"],
            },
        ),
        Tool(
            name="open_URL_with_authorization",
            description="Open a URL in a new authorized browser window after Moodle login (show to user).",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Target URL to open after Moodle login",
                    }
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="get_current_time",
            description="Get current local datetime as YYYY-MM-DD HH:MM:SS.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_class_schedule",
            description="Get class schedule in this week; pass null for full week, or date (YYYY-MM-DD) to filter. If you need multiple days, pass null once instead of multiple calls.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": ["string", "null"],
                        "description": "Date filter YYYY-MM-DD; null returns full week",
                    }
                },
                "required": [],
            },
        ),
    ]


def _wrap_json(data: Any) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))]


def tool_get_all_courses() -> List[Dict[str, str]]:
    try:
        courses = muster_client.get_courses()
        return [{"name": course.name, "url": course.url} for course in courses]
    except Exception as e:
        return [{"error": f"Failed to get courses: {str(e)}"}]


def tool_get_course_content(course_name: str) -> List[Dict[str, Any]]:
    try:
        all_courses = muster_client.get_courses()

        match = next((c for c in all_courses if c.name == course_name), None)
        if not match:
            return [{"error": f"No courses found matching '{course_name}'. Please call get_all_courses first."}]

        try:
            assignments = muster_client.get_course_content(match.url)
            return [
                {
                    "name": assignment.name,
                    "type": assignment.type,
                    "url": assignment.url,
                    "course_name": match.name,
                    "course_url": match.url,
                }
                for assignment in assignments
            ]
        except Exception as e:
            return [{"error": f"Failed to get content from course '{match.name}': {str(e)}"}]

    except Exception as e:
        return [{"error": f"Failed to get course content: {str(e)}"}]


def tool_get_pending_events() -> List[Dict[str, str]]:
    try:
        events = muster_client.get_pending_events()
        return [
            {"name": event.name, "course": event.course, "due_date": event.due_date, "url": event.url}
            for event in events
        ]
    except Exception as e:
        return [{"error": f"Failed to get pending events: {str(e)}"}]


def tool_download_resource(resource_url: str, download_path: Optional[str] = None) -> Dict[str, Any]:
    try:
        return muster_client.download_resource(resource_url, download_path)
    except Exception as e:
        return {"error": f"Failed to download resource: {str(e)}"}


def tool_open_URL_with_authorization(url: str) -> Dict[str, Any]:
    try:
        muster_client_with_head = MUSTerClientWithHead()
        driver = muster_client_with_head.openUrl(url)

        if driver:
            current_url = driver.current_url
            page_title = driver.title

            return {
                "success": True,
                "message": "URL opened successfully with Moodle authorization",
                "opened_url": url,
                "current_url": current_url,
                "page_title": page_title,
                "note": "A new browser window is now open and logged in. It will remain open until manually closed.",
            }
        else:
            return {"error": "Failed to open URL - driver not initialized"}

    except Exception as e:
        return {"error": f"Failed to open URL with authorization: {str(e)}"}


def tool_get_current_time() -> str:
    current_time = datetime.now()
    return current_time.strftime("%Y-%m-%d %H:%M:%S")


def tool_get_class_schedule(date: Optional[str] = None) -> Any:
    try:
        schedule_data = muster_client.get_class_schedule(date=date)
        return schedule_data
    except Exception as e:
        return {"error": f"Failed to fetch schedule data: {str(e)}"}


@server.list_tools()
async def list_tools() -> List[Tool]:
    return list_muster_tools()


@server.call_tool()
async def call_tool(name: str, arguments: Optional[Dict[str, Any]]) -> List[TextContent]:
    args = arguments or {}
    try:
        if name == "get_all_courses":
            return _wrap_json(tool_get_all_courses())
        if name == "get_course_content":
            return _wrap_json(tool_get_course_content(args["course_name"]))
        if name == "get_pending_events":
            return _wrap_json(tool_get_pending_events())
        if name == "download_resource":
            return _wrap_json(tool_download_resource(args["resource_url"], args.get("download_path")))
        if name == "open_URL_with_authorization":
            return _wrap_json(tool_open_URL_with_authorization(args["url"]))
        if name == "get_current_time":
            return _wrap_json(tool_get_current_time())
        if name == "get_class_schedule":
            return _wrap_json(tool_get_class_schedule(args.get("date")))

        return _wrap_json({"error": f"Unknown tool: {name}"})
    except Exception as e:
        return _wrap_json({"error": str(e)})


async def main():
    async with stdio_server() as (read_stream, write_stream):
        try:
            await server.run(read_stream, write_stream, server.create_initialization_options())
        finally:
            try:
                muster_client.close()
            except Exception:
                pass


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
