from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError


class MouseMcpError(ToolError):
    """Base error returned to the agent."""


class ActionCancelled(MouseMcpError):
    """The user pressed Escape or called mouse_stop."""


class RouteUnavailable(MouseMcpError):
    """No valid browser or desktop target is currently available."""


class HighRiskBlocked(MouseMcpError):
    """A high-risk action needs explicit human confirmation."""

    def __init__(self, message: str, evidence: list[str] | None = None) -> None:
        super().__init__(message)
        self.evidence = evidence or []


class BoundaryViolation(MouseMcpError):
    """A requested coordinate is outside the active surface."""
