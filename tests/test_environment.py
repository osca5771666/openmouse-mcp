from __future__ import annotations

from mouse_mcp.browser_bridge import BrowserSession
from mouse_mcp.environment import EnvironmentRouter


class FakeBridge:
    def __init__(self, session: BrowserSession, fresh: bool) -> None:
        self.session = session
        self.fresh = fresh

    def snapshot(self) -> BrowserSession:
        return self.session

    def is_fresh(self) -> bool:
        return self.fresh


def _session(*, focused: bool = True) -> BrowserSession:
    return BrowserSession(
        client_id="test",
        last_seen=1.0,
        focused=focused,
        viewport_width=1280,
        viewport_height=720,
    )


def test_routes_to_browser_for_focused_chromium_page() -> None:
    router = EnvironmentRouter(
        FakeBridge(_session(), True),  # type: ignore[arg-type]
        foreground_process=lambda: "chrome.exe",
        desktop_available=lambda: True,
    )

    decision = router.route()

    assert decision.environment == "browser"
    assert "chrome.exe" in decision.reason


def test_routes_to_desktop_when_non_browser_app_is_foreground() -> None:
    router = EnvironmentRouter(
        FakeBridge(_session(), True),  # type: ignore[arg-type]
        foreground_process=lambda: "Code.exe",
        desktop_available=lambda: True,
    )

    decision = router.route()

    assert decision.environment == "desktop"


def test_routes_to_desktop_when_browser_is_not_focused() -> None:
    router = EnvironmentRouter(
        FakeBridge(_session(focused=False), True),  # type: ignore[arg-type]
        foreground_process=lambda: "chrome.exe",
        desktop_available=lambda: True,
    )

    decision = router.route()

    assert decision.environment == "desktop"


def test_routes_to_browser_on_non_windows_when_companion_is_active() -> None:
    router = EnvironmentRouter(
        FakeBridge(_session(), True),  # type: ignore[arg-type]
        foreground_process=lambda: None,
        desktop_available=lambda: False,
    )

    decision = router.route()

    assert decision.environment == "browser"


def test_routes_to_cloud_when_non_windows_cloud_browser_is_available() -> None:
    router = EnvironmentRouter(
        FakeBridge(BrowserSession(), False),  # type: ignore[arg-type]
        foreground_process=lambda: None,
        desktop_available=lambda: False,
        cloud_available=lambda: True,
        cloud_mode="on",
    )

    decision = router.route()

    assert decision.environment == "cloud"


def test_forced_cloud_requires_playwright() -> None:
    router = EnvironmentRouter(
        FakeBridge(BrowserSession(), False),  # type: ignore[arg-type]
        mode="cloud",
        desktop_available=lambda: False,
        cloud_available=lambda: False,
    )

    try:
        router.route()
    except Exception as exc:
        assert "Playwright" in str(exc)
    else:
        raise AssertionError("Forced cloud mode should fail when Playwright is unavailable.")
