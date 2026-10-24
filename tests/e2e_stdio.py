from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "MOUSE_MCP_ENV": "auto",
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mouse_mcp"],
        cwd=ROOT,
        env=env,
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]
            expected = {
                "mouse_move",
                "mouse_click",
                "mouse_drag",
                "mouse_scroll",
                "mouse_position",
                "mouse_screenshot",
                "computer_observe",
                "browser_open",
                "mouse_stop",
                "mouse_status",
            }
            assert set(names) == expected
            status = await session.call_tool("mouse_status", {})
            assert status.content
            text = status.content[0].text
            payload = json.loads(text)
            assert payload["emergency_key"] == "ESC"
            screenshot = await session.call_tool("computer_observe", {})
            assert len(screenshot.content) == 2
            assert screenshot.content[0].type == "text"
            assert screenshot.content[1].type == "image"
            observation = json.loads(screenshot.content[0].text)
            assert observation["desktop_context"]["available"] is True
            assert observation["desktop_context"]["taskbars"]
            assert initialized.server_info.name == "openmouse-mcp"
            print(
                json.dumps(
                    {
                        "stdio_e2e": "ok",
                        "server": initialized.server_info.name,
                        "tool_count": len(names),
                        "route": payload["route"],
                        "browser_connected": payload["browser"]["connected"],
                    },
                    ensure_ascii=True,
                    indent=2,
                )
            )


if __name__ == "__main__":
    asyncio.run(main())
