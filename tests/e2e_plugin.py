from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-u", "./bin/openmouse-mcp-launcher.py"],
        cwd=ROOT,
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
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
            assert names == expected
            status = await session.call_tool("mouse_status", {})
            status_payload = json.loads(status.content[0].text)
            print(
                json.dumps(
                    {
                        "plugin_e2e": "ok",
                        "server": initialized.server_info.name,
                        "tool_count": len(names),
                        "route": status_payload["route"],
                    },
                    ensure_ascii=True,
                    indent=2,
                )
            )


if __name__ == "__main__":
    asyncio.run(main())
