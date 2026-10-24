from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from typing import Callable

from .browser_bridge import BrowserBridge, BrowserSession
from .errors import RouteUnavailable


LOGGER = logging.getLogger(__name__)
BROWSER_PROCESSES = {
    "chrome.exe",
    "msedge.exe",
    "brave.exe",
    "firefox.exe",
    "opera.exe",
    "vivaldi.exe",
    "chromium.exe",
}


@dataclass(frozen=True)
class RouteDecision:
    environment: str
    reason: str
    session: BrowserSession | None = None


class EnvironmentRouter:
    def __init__(
        self,
        bridge: BrowserBridge,
        mode: str = "auto",
        foreground_process: Callable[[], str | None] | None = None,
        desktop_available: Callable[[], bool] | None = None,
        cloud_available: Callable[[], bool] | None = None,
        cloud_mode: str = "auto",
    ) -> None:
        self._bridge = bridge
        self._mode = mode
        self._foreground_process = foreground_process or windows_foreground_process
        self._desktop_available = desktop_available or _is_windows
        self._cloud_available = cloud_available or (lambda: False)
        self._cloud_mode = cloud_mode

    def route(self) -> RouteDecision:
        session = self._bridge.snapshot()
        browser_ready = self._bridge.is_fresh() and session.focused

        if self._mode == "browser":
            if not self._bridge.is_fresh():
                raise RouteUnavailable("Browser mode is selected but the extension is not connected.")
            return RouteDecision("browser", "MOUSE_MCP_ENV=browser", session)

        if self._mode == "desktop":
            if not self._desktop_available():
                raise RouteUnavailable("Desktop mode is selected but Windows/PyAutoGUI is unavailable.")
            return RouteDecision("desktop", "MOUSE_MCP_ENV=desktop")

        if self._mode == "cloud":
            if not self._cloud_available():
                raise RouteUnavailable("Cloud mode is selected but Playwright is unavailable.")
            return RouteDecision("cloud", "MOUSE_MCP_ENV=cloud")

        process = self._foreground_process()
        browser_process_active = bool(process and process.lower() in BROWSER_PROCESSES)
        if browser_ready and browser_process_active:
            return RouteDecision(
                "browser",
                f"foreground browser process {process} with an active companion heartbeat",
                session,
            )

        cloud_allowed = self._cloud_mode == "on" or (
            self._cloud_mode == "auto" and not _is_windows()
        )
        if cloud_allowed and self._cloud_available():
            return RouteDecision(
                "cloud",
                "Playwright cloud browser is enabled and no focused browser companion is active",
            )

        if self._desktop_available():
            if session.last_seen and not browser_ready:
                reason = "browser companion is not focused or its heartbeat is stale"
            else:
                reason = f"foreground process {process or 'unknown'} is not an attached browser"
            return RouteDecision("desktop", reason)

        if self._bridge.is_fresh():
            return RouteDecision("browser", "non-Windows host with active browser companion", session)
        raise RouteUnavailable(
            "No mouse target is available. Start the browser extension, enable the cloud browser, "
            "or run this plugin on Windows."
        )

    def status(self) -> dict[str, object]:
        try:
            decision = self.route()
            return {
                "mode": self._mode,
                "environment": decision.environment,
                "reason": decision.reason,
            }
        except RouteUnavailable as exc:
            return {"mode": self._mode, "environment": None, "reason": str(exc)}


def _is_windows() -> bool:
    return platform.system().lower() == "windows"


def windows_foreground_process() -> str | None:
    if not _is_windows():
        return None
    try:
        import psutil
        import win32gui
        import win32process

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name().lower()
    except Exception:
        LOGGER.debug("Could not inspect foreground process", exc_info=True)
        return None
