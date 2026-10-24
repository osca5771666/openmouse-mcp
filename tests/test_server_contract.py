from __future__ import annotations

import asyncio

from mouse_mcp.config import Settings
from mouse_mcp.runtime import MouseRuntime
from mouse_mcp.server import build_server


EXPECTED_TOOLS = {
    "mouse_move",
    "mouse_click",
    "mouse_drag",
    "mouse_scroll",
    "mouse_position",
    "mouse_screenshot",
    "computer_observe",
    "browser_open",
    "app_open",
    "mouse_stop",
    "mouse_status",
}


def test_tool_contract_is_shared_and_context_is_hidden() -> None:
    runtime = MouseRuntime(Settings(environment_mode="auto"))
    try:
        server = build_server(runtime, runtime.settings)
        tools = asyncio.run(server.list_tools())
    finally:
        runtime.close()

    assert {tool.name for tool in tools} == EXPECTED_TOOLS
    for tool in tools:
        assert "ctx" not in tool.input_schema.get("properties", {})

    click = next(tool for tool in tools if tool.name == "mouse_click")
    required = set(click.input_schema.get("required", []))
    assert {"button", "clicks", "intent"} <= required
    assert "target_description" in click.input_schema["properties"]
    browser_open = next(tool for tool in tools if tool.name == "browser_open")
    assert "browser" in browser_open.input_schema["properties"]
    assert browser_open.input_schema["properties"]["browser"]["default"] == "default"


def test_server_instructions_fit_openclaw_prompt_cap() -> None:
    runtime = MouseRuntime(Settings(environment_mode="auto"))
    try:
        server = build_server(runtime, runtime.settings)
        instructions = server.instructions or ""
    finally:
        runtime.close()

    assert "high-risk" in instructions.lower()
    assert "mouse_screenshot" in instructions
    assert "computer_observe" in instructions
    assert len(instructions) <= 2000
