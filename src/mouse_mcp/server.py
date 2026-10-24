from __future__ import annotations

import functools
import json
from typing import Annotated, Any, Literal

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ImageContent, TextContent, ToolAnnotations
from pydantic import Field

from .config import Settings
from .errors import HighRiskBlocked, MouseMcpError
from .runtime import MouseRuntime
from .safety import (
    ConfirmationInput,
    RiskAssessment,
    classify_risk,
    confirmation_message,
)


SERVER_INSTRUCTIONS = """OpenMouse MCP controls one virtual cursor through a shared interface.
Routing is automatic: an attached, focused Chromium companion uses page-level JS events;
Windows otherwise uses PyAutoGUI on the real desktop; non-Windows/cloud hosts can use an
embedded Playwright Chromium browser.

Before clicking a visual target, call computer_observe (or mouse_screenshot), identify the target, and convert its
position to the screenshot's reported coordinate space. Use CSS viewport pixels for browser
actions and physical desktop pixels for Windows. `computer_observe` additionally reports the
Windows active window, taskbar, monitors and visible windows for taskbar/application workflows.
Every click, drag, and scroll requires a concrete
`intent`; `target_description` should quote the visible label when available. Never describe a
destructive, bulk-submit, or close-all action in vague language.

For a known URL, use browser_open as the fast path instead of screenshots, taskbar clicks, or
address-bar automation. On Windows it launches the default browser or Edge/Chrome; in cloud mode
it navigates the embedded Playwright browser.
For a known local application, use app_open instead of visually searching the taskbar.
The server asks the user for MCP elicitation approval before executing detected high-risk actions.
If approval is unavailable or denied, do not retry around the safety gate. Press ESC or call
mouse_stop to cancel. Verify meaningful actions with another observation and stop on repeated
errors. Mouse control is probabilistic: do not operate unattended.
"""


Coordinate = Annotated[int, Field(description="Horizontal coordinate in the reported coordinate space.")]


def build_server(runtime: MouseRuntime, settings: Settings) -> MCPServer:
    server = MCPServer(
        name="openmouse-mcp",
        title="OpenMouse MCP",
        version="1.0.2",
        instructions=SERVER_INSTRUCTIONS,
        log_level="WARNING",
    )

    async def run_blocking(function: Any) -> Any:
        return await anyio.to_thread.run_sync(function)

    async def approve(
        ctx: Context,
        action_name: str,
        risk: RiskAssessment | None,
        details: str,
    ) -> None:
        if not settings.confirm_high_risk:
            raise MouseMcpError(
                "High-risk confirmation is disabled by configuration. The operation is blocked."
            )
        assessment = risk or RiskAssessment(True, ["semantic high-risk action"])
        try:
            result = await ctx.elicit(
                confirmation_message(action_name, assessment, details),
                ConfirmationInput,
            )
        except Exception as exc:
            raise MouseMcpError(
                "This MCP client cannot request explicit human confirmation. "
                "The high-risk action was not executed."
            ) from exc
        if not hasattr(result, "data") or not bool(result.data.confirm):
            raise MouseMcpError("The user did not approve the high-risk mouse action.")

    @server.tool(
        name="mouse_move",
        title="Move the mouse cursor",
        description=(
            "Move the active mouse cursor along a human-like curved path. Browser coordinates use "
            "CSS viewport pixels; Windows coordinates use physical desktop pixels. Out-of-range move "
            "targets are clamped to the surface."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def mouse_move(x: Coordinate, y: Coordinate) -> str:
        result = await run_blocking(
            functools.partial(runtime.act, "move", {"x": int(x), "y": int(y)})
        )
        return json.dumps(result, ensure_ascii=False)

    @server.tool(
        name="mouse_click",
        title="Click with the mouse",
        description=(
            "Move to x/y if supplied, then perform one left/right click or a left double click. "
            "`intent` is mandatory and must state the expected real-world effect. Destructive "
            "actions, bulk submissions, and close-all operations trigger an explicit user prompt."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def mouse_click(
        x: Coordinate | None,
        y: Coordinate | None,
        button: Literal["left", "right"],
        clicks: Annotated[int, Field(ge=1, le=2)],
        intent: Annotated[
            str,
            Field(
                min_length=4,
                max_length=500,
                description="Concrete expected effect, for example 'open the Save button'.",
            ),
        ],
        target_description: Annotated[
            str,
            Field(
                default="",
                max_length=500,
                description="Visible label or accessibility text of the intended target.",
            ),
        ] = "",
        ctx: Context | None = None,
    ) -> str:
        if (x is None) != (y is None):
            raise MouseMcpError("x and y must either both be provided or both omitted.")
        if button == "right" and clicks == 2:
            raise MouseMcpError("Use left double click; right double click is not supported.")
        risk = classify_risk(intent, target_description)
        risk_approved = False
        if risk.is_high_risk and ctx is not None:
            await approve(
                ctx,
                "mouse_click",
                risk,
                f"button={button}, clicks={clicks}, target={target_description or (x, y)}",
            )
            risk_approved = True

        params: dict[str, Any] = {
            "x": int(x) if x is not None else None,
            "y": int(y) if y is not None else None,
            "button": button,
            "clicks": int(clicks),
            "intent": intent,
            "target_description": target_description,
            "risk_approved": risk_approved,
        }
        try:
            result = await run_blocking(
                functools.partial(runtime.act, "click", params, retries=2)
            )
        except HighRiskBlocked as blocked:
            if ctx is None:
                raise MouseMcpError(f"{blocked}. Human confirmation is required.") from blocked
            await approve(
                ctx,
                "mouse_click",
                RiskAssessment(True, blocked.evidence),
                f"button={button}, clicks={clicks}, target={target_description or (x, y)}",
            )
            params["risk_approved"] = True
            result = await run_blocking(
                functools.partial(runtime.act, "click", params, retries=2)
            )
        return json.dumps(result, ensure_ascii=False)

    @server.tool(
        name="mouse_drag",
        title="Drag with the mouse",
        description=(
            "Drag from one point to another using a human-like curved path. `intent` is mandatory. "
            "High-risk semantic intent triggers an explicit user prompt."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def mouse_drag(
        from_x: Coordinate,
        from_y: Coordinate,
        to_x: Coordinate,
        to_y: Coordinate,
        button: Literal["left", "right"],
        intent: Annotated[str, Field(min_length=4, max_length=500)],
        target_description: Annotated[str, Field(default="", max_length=500)] = "",
        ctx: Context | None = None,
    ) -> str:
        risk = classify_risk(intent, target_description)
        risk_approved = False
        if risk.is_high_risk and ctx is not None:
            await approve(
                ctx,
                "mouse_drag",
                risk,
                f"from=({from_x},{from_y}), to=({to_x},{to_y}), target={target_description}",
            )
            risk_approved = True
        params = {
            "from_x": int(from_x),
            "from_y": int(from_y),
            "to_x": int(to_x),
            "to_y": int(to_y),
            "button": button,
            "intent": intent,
            "target_description": target_description,
            "risk_approved": risk_approved,
        }
        try:
            result = await run_blocking(functools.partial(runtime.act, "drag", params))
        except HighRiskBlocked as blocked:
            if ctx is None:
                raise MouseMcpError(f"{blocked}. Human confirmation is required.") from blocked
            await approve(
                ctx,
                "mouse_drag",
                RiskAssessment(True, blocked.evidence),
                f"from=({from_x},{from_y}), to=({to_x},{to_y})",
            )
            params["risk_approved"] = True
            result = await run_blocking(functools.partial(runtime.act, "drag", params))
        return json.dumps(result, ensure_ascii=False)

    @server.tool(
        name="mouse_scroll",
        title="Scroll with the mouse wheel",
        description=(
            "Scroll up or down at the current cursor location. One click is one wheel notch. "
            "`intent` is mandatory; high-risk semantic intent is confirmed first."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def mouse_scroll(
        direction: Literal["up", "down"],
        clicks: Annotated[int, Field(ge=1, le=20)],
        intent: Annotated[str, Field(min_length=4, max_length=500)],
        x: Coordinate | None = None,
        y: Coordinate | None = None,
        target_description: Annotated[str, Field(default="", max_length=500)] = "",
        ctx: Context | None = None,
    ) -> str:
        if (x is None) != (y is None):
            raise MouseMcpError("x and y must either both be provided or both omitted.")
        risk = classify_risk(intent, target_description)
        risk_approved = False
        if risk.is_high_risk and ctx is not None:
            await approve(
                ctx,
                "mouse_scroll",
                risk,
                f"direction={direction}, clicks={clicks}, target={target_description}",
            )
            risk_approved = True
        params = {
            "direction": direction,
            "clicks": int(clicks),
            "x": int(x) if x is not None else None,
            "y": int(y) if y is not None else None,
            "intent": intent,
            "target_description": target_description,
            "risk_approved": risk_approved,
        }
        try:
            result = await run_blocking(functools.partial(runtime.act, "scroll", params))
        except HighRiskBlocked as blocked:
            if ctx is None:
                raise MouseMcpError(f"{blocked}. Human confirmation is required.") from blocked
            await approve(
                ctx,
                "mouse_scroll",
                RiskAssessment(True, blocked.evidence),
                f"direction={direction}, clicks={clicks}",
            )
            params["risk_approved"] = True
            result = await run_blocking(functools.partial(runtime.act, "scroll", params))
        return json.dumps(result, ensure_ascii=False)

    @server.tool(
        name="mouse_position",
        title="Read the mouse position",
        description="Read the current virtual browser cursor or real Windows cursor position.",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def mouse_position() -> str:
        result = await run_blocking(runtime.read_position)
        return json.dumps(result, ensure_ascii=False)

    @server.tool(
        name="mouse_screenshot",
        title="Capture the active mouse surface",
        description=(
            "Capture the active local browser tab, the cloud browser, or the full Windows desktop. "
            "The text content includes image/viewport dimensions and the coordinate space. Use that "
            "metadata to map a visual target into mouse tool coordinates."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
    )
    async def mouse_screenshot() -> list[TextContent | ImageContent]:
        capture = await run_blocking(runtime.capture)
        return [
            TextContent(
                type="text",
                text=json.dumps(capture.metadata, ensure_ascii=False),
            ),
            ImageContent(
                type="image",
                data=capture.data_base64,
                mimeType=capture.mime_type,
            ),
        ]

    @server.tool(
        name="computer_observe",
        title="Observe the active computer surface",
        description=(
            "Capture the active desktop/browser and return richer context. On Windows this "
            "includes the active window, taskbar rectangles, monitors and visible application "
            "windows. Use this before visual targeting and again for verification."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
    )
    async def computer_observe() -> list[TextContent | ImageContent]:
        capture = await run_blocking(runtime.observe)
        return [
            TextContent(
                type="text",
                text=json.dumps(capture.metadata, ensure_ascii=False),
            ),
            ImageContent(
                type="image",
                data=capture.data_base64,
                mimeType=capture.mime_type,
            ),
        ]

    @server.tool(
        name="browser_open",
        title="Open a URL directly in a browser",
        description=(
            "Fast path for opening a known http:// or https:// URL. On Windows this launches the "
            "default browser, Edge, or Chrome directly without screenshots or mouse movement. In "
            "cloud mode it navigates the embedded Playwright browser and blocks private addresses "
            "by default."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
    )
    async def browser_open(
        url: Annotated[
            str,
            Field(
                min_length=9,
                max_length=4096,
                description="Absolute http:// or https:// URL.",
            ),
        ],
        browser: Literal["default", "edge", "chrome"] = "default",
    ) -> str:
        result = await run_blocking(functools.partial(runtime.open_browser_url, url, browser))
        return json.dumps(result, ensure_ascii=False)

    @server.tool(
        name="app_open",
        title="Open or focus a local application",
        description=(
            "Fast path for local applications. Focuses an existing running window, or launches a "
            "known executable/Start Menu application. Supports aliases such as feishu, notepad, "
            "explorer, cmd, powershell, calculator, edge, and chrome."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def app_open(
        name: Annotated[
            str,
            Field(
                min_length=2,
                max_length=100,
                description="Application name or alias, for example 'feishu' or 'notepad'.",
            ),
        ],
    ) -> str:
        result = await run_blocking(functools.partial(runtime.open_app, name))
        return json.dumps(result, ensure_ascii=False)

    @server.tool(
        name="mouse_stop",
        title="Emergency stop",
        description=(
            "Immediately cancel the current mouse action, drain queued mouse actions, release held "
            "buttons, and send stop to the browser companion."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def mouse_stop() -> str:
        await run_blocking(functools.partial(runtime.emergency_stop, "mouse_stop_tool"))
        return json.dumps({"stopped": True, "queue_cleared": True, "key": "ESC"})

    @server.tool(
        name="mouse_status",
        title="Inspect mouse environment status",
        description=(
            "Read automatic routing state, browser companion freshness, viewport, platform, and "
            "consecutive failure count. This does not move the mouse."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def mouse_status() -> str:
        result = await run_blocking(runtime.status)
        return json.dumps(result, ensure_ascii=False)

    return server
