from __future__ import annotations

import base64
import logging
import platform
import random
import threading
import time
from dataclasses import dataclass
from typing import Any

from .browser_bridge import BrowserBridge
from .cloud_browser import CloudBrowserDriver, cloud_browser_supported
from .config import Settings
from .desktop_observer import collect_desktop_context
from .desktop_driver import DesktopCapture, DesktopDriver
from .environment import EnvironmentRouter, RouteDecision
from .errors import (
    ActionCancelled,
    BoundaryViolation,
    HighRiskBlocked,
    MouseMcpError,
    RouteUnavailable,
)
from .humanize import random_action_delay
from .local_browser import open_local_url
from .scheduler import ActionRunner


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureResult:
    data_base64: str
    mime_type: str
    metadata: dict[str, Any]


class MouseRuntime:
    """Shared action runtime for browser and desktop environments."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bridge = BrowserBridge(
            host=settings.bridge_host,
            port=settings.bridge_port,
            token=settings.browser_token,
            heartbeat_timeout=settings.heartbeat_timeout,
            command_timeout=settings.command_timeout,
        )
        self.desktop = self._create_desktop_driver(settings.screen_poll_interval)
        self.cloud = self._create_cloud_driver(settings)
        self.router = EnvironmentRouter(
            self.bridge,
            mode=settings.environment_mode,
            desktop_available=self._desktop_available,
            cloud_available=self._cloud_available,
            cloud_mode=settings.cloud_browser_mode,
        )
        self.runner = ActionRunner()
        self._rng = random.Random()
        self._failure_lock = threading.Lock()
        self._consecutive_failures = 0
        self._failure_threshold = 3
        self._keyboard_listener: Any = None
        self._closed = False
        self.bridge.set_emergency_callback(self.emergency_stop)

    def start(self) -> None:
        self.bridge.start()
        self._start_escape_listener()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._keyboard_listener is not None:
            try:
                self._keyboard_listener.stop()
            except Exception:
                pass
        self.bridge.emergency_stop("plugin_shutdown")
        self.bridge.close()
        if self.cloud is not None:
            try:
                self.runner.submit(lambda _cancel: self.cloud.close())
            except Exception:
                LOGGER.debug("Cloud browser shutdown failed", exc_info=True)
        if self.desktop is not None:
            self.desktop.release_buttons()
        self.runner.close()

    def act(
        self,
        action: str,
        params: dict[str, Any],
        retries: int = 0,
        apply_action_delay: bool = True,
    ) -> dict[str, Any]:
        decision = self.router.route()
        last_error: Exception | None = None
        for _attempt in range(retries + 1):
            try:
                result = self.runner.submit(
                    lambda cancel: self._act_once(
                        decision,
                        action,
                        params,
                        cancel,
                        apply_action_delay,
                    )
                )
                self._record_success()
                return result
            except (HighRiskBlocked, ActionCancelled, BoundaryViolation, RouteUnavailable):
                raise
            except Exception as exc:
                last_error = exc
                time.sleep(0.05)
        assert last_error is not None
        self._record_failure(last_error)
        raise MouseMcpError(self._failure_text(last_error))

    def read_position(self) -> dict[str, Any]:
        decision = self.router.route()
        try:
            result = self.runner.submit(lambda cancel: self._position_once(decision, cancel))
            self._record_success()
            return result
        except (ActionCancelled, RouteUnavailable):
            raise
        except Exception as exc:
            self._record_failure(exc)
            raise MouseMcpError(self._failure_text(exc)) from exc

    def capture(self) -> CaptureResult:
        decision = self.router.route()
        try:
            result = self.runner.submit(lambda cancel: self._capture_once(decision, cancel))
            self._record_success()
            return result
        except (ActionCancelled, RouteUnavailable):
            raise
        except Exception as exc:
            self._record_failure(exc)
            raise MouseMcpError(self._failure_text(exc)) from exc

    def observe(self) -> CaptureResult:
        decision = self.router.route()
        try:
            result = self.runner.submit(lambda cancel: self._observe_once(decision, cancel))
            self._record_success()
            return result
        except (ActionCancelled, RouteUnavailable):
            raise
        except Exception as exc:
            self._record_failure(exc)
            raise MouseMcpError(self._failure_text(exc)) from exc

    def open_browser_url(self, url: str, browser: str = "default") -> dict[str, Any]:
        decision = self.router.route()
        if decision.environment != "cloud":
            result = open_local_url(url, browser)
            return {**result, "environment": decision.environment, "route_reason": decision.reason}
        try:
            if self.cloud is None:
                raise RouteUnavailable("Cloud browser driver is unavailable.")
            result = self.runner.submit(lambda cancel: self.cloud.open_url(url, cancel))
            self._record_success()
            return {**result, "environment": "cloud", "route_reason": decision.reason}
        except (ActionCancelled, RouteUnavailable):
            raise
        except Exception as exc:
            self._record_failure(exc)
            raise MouseMcpError(self._failure_text(exc)) from exc

    def emergency_stop(self, reason: str = "emergency_stop") -> None:
        LOGGER.warning("Emergency mouse stop: %s", reason)
        self.runner.emergency_stop(reason)
        self.bridge.emergency_stop(reason)
        if self.desktop is not None:
            self.desktop.release_buttons()

    def status(self) -> dict[str, Any]:
        return {
            "platform": platform.system(),
            "route": self.router.status(),
            "browser": self.bridge.status(),
            "desktop_available": self.desktop is not None and self.desktop.available(),
            "cloud_browser": {
                "configured": self.cloud is not None,
                "mode": self.settings.cloud_browser_mode,
                "playwright_available": cloud_browser_supported(),
            },
            "consecutive_failures": self._consecutive_failures,
            "emergency_key": "ESC",
        }

    def _act_once(
        self,
        decision: RouteDecision,
        action: str,
        params: dict[str, Any],
        cancel: threading.Event,
        apply_action_delay: bool,
    ) -> dict[str, Any]:
        if decision.environment == "browser":
            result = self.bridge.command(action, params)
            if result.get("blocked"):
                raise HighRiskBlocked(
                    str(result.get("message") or "The browser blocked a high-risk action."),
                    evidence=[str(item) for item in result.get("evidence", [])],
                )
        elif decision.environment == "desktop":
            if self.desktop is None:
                raise RouteUnavailable("Windows desktop driver is unavailable.")
            result = self._desktop_action(self.desktop, action, params, cancel)
        elif decision.environment == "cloud":
            if self.cloud is None:
                raise RouteUnavailable("Cloud browser driver is unavailable.")
            result = self._cloud_action(self.cloud, action, params, cancel)
        else:
            raise RouteUnavailable(f"Unknown environment: {decision.environment}")

        if apply_action_delay:
            self._action_delay(cancel)
        return {**result, "environment": decision.environment, "route_reason": decision.reason}

    def _position_once(
        self,
        decision: RouteDecision,
        cancel: threading.Event,
    ) -> dict[str, Any]:
        if decision.environment == "browser":
            result = self.bridge.command("position", {})
        elif decision.environment == "cloud":
            if self.cloud is None:
                raise RouteUnavailable("Cloud browser driver is unavailable.")
            result = self.cloud.position(cancel)
        else:
            assert self.desktop is not None
            result = self.desktop.position(cancel)
        return {**result, "environment": decision.environment}

    def _capture_once(
        self,
        decision: RouteDecision,
        cancel: threading.Event,
    ) -> CaptureResult:
        if decision.environment == "browser":
            result = self.bridge.command("screenshot", {}, timeout=self.settings.command_timeout)
            data_url = str(result.pop("data_url", ""))
            if "," not in data_url:
                raise MouseMcpError("Browser screenshot did not return a valid PNG data URL.")
            header, encoded = data_url.split(",", 1)
            mime_type = "image/png"
            if "image/" in header:
                mime_type = header.split(";", 1)[0].split(":", 1)[-1]
            result["environment"] = "browser"
            return CaptureResult(encoded, mime_type, result)

        if decision.environment == "cloud":
            if self.cloud is None:
                raise RouteUnavailable("Cloud browser driver is unavailable.")
            capture = self.cloud.capture(cancel)
            encoded = base64.b64encode(capture.data).decode("ascii")
            return CaptureResult(
                data_base64=encoded,
                mime_type=f"image/{capture.format}",
                metadata=capture.metadata,
            )

        if self.desktop is None:
            raise RouteUnavailable("Windows desktop driver is unavailable.")
        capture: DesktopCapture = self.desktop.screenshot(cancel)
        encoded = base64.b64encode(capture.data).decode("ascii")
        return CaptureResult(
            data_base64=encoded,
            mime_type=f"image/{capture.format}",
            metadata={
                "environment": "desktop",
                "image_width": capture.width,
                "image_height": capture.height,
                "coordinate_space": "physical desktop pixels used by PyAutoGUI and screenshots",
            },
        )

    def _observe_once(
        self,
        decision: RouteDecision,
        cancel: threading.Event,
    ) -> CaptureResult:
        capture = self._capture_once(decision, cancel)
        metadata = dict(capture.metadata)
        metadata["environment"] = decision.environment
        metadata["route_reason"] = decision.reason
        if decision.environment == "desktop":
            metadata["desktop_context"] = collect_desktop_context()
            metadata["visual_workflow"] = [
                "Identify the target visually in the screenshot.",
                "Use the active window, taskbar and window rectangles as coordinate hints.",
                "Move or click with mouse tools.",
                "Capture another screenshot to verify the result.",
            ]
        elif decision.environment == "browser":
            metadata["visual_workflow"] = [
                "Identify the target in the browser screenshot.",
                "Scale image pixels to CSS viewport pixels before clicking.",
                "Capture another screenshot after the action.",
            ]
        else:
            metadata["visual_workflow"] = [
                "Identify the target in the cloud browser screenshot.",
                "Cloud coordinates are CSS viewport pixels.",
                "Capture another screenshot after the action.",
            ]
        return CaptureResult(capture.data_base64, capture.mime_type, metadata)

    def _desktop_action(
        self,
        driver: DesktopDriver,
        action: str,
        params: dict[str, Any],
        cancel: threading.Event,
    ) -> dict[str, Any]:
        if action == "move":
            return driver.move(int(params["x"]), int(params["y"]), cancel)
        if action == "click":
            return driver.click(
                params.get("x"),
                params.get("y"),
                str(params.get("button", "left")),
                int(params.get("clicks", 1)),
                cancel,
            )
        if action == "drag":
            return driver.drag(
                int(params["from_x"]),
                int(params["from_y"]),
                int(params["to_x"]),
                int(params["to_y"]),
                str(params.get("button", "left")),
                cancel,
            )
        if action == "scroll":
            if params.get("x") is not None and params.get("y") is not None:
                driver.move(int(params["x"]), int(params["y"]), cancel)
            return driver.scroll(
                str(params.get("direction", "down")),
                int(params.get("clicks", 3)),
                cancel,
            )
        raise MouseMcpError(f"Unsupported mouse action: {action}")

    def _cloud_action(
        self,
        driver: CloudBrowserDriver,
        action: str,
        params: dict[str, Any],
        cancel: threading.Event,
    ) -> dict[str, Any]:
        if action == "move":
            return driver.move(int(params["x"]), int(params["y"]), cancel)
        if action == "click":
            return driver.click(
                params.get("x"),
                params.get("y"),
                str(params.get("button", "left")),
                int(params.get("clicks", 1)),
                params,
                cancel,
            )
        if action == "drag":
            return driver.drag(
                int(params["from_x"]),
                int(params["from_y"]),
                int(params["to_x"]),
                int(params["to_y"]),
                str(params.get("button", "left")),
                params,
                cancel,
            )
        if action == "scroll":
            return driver.scroll(
                str(params.get("direction", "down")),
                int(params.get("clicks", 3)),
                params.get("x"),
                params.get("y"),
                params,
                cancel,
            )
        raise MouseMcpError(f"Unsupported cloud mouse action: {action}")

    def _action_delay(self, cancel: threading.Event) -> None:
        delay = random_action_delay(
            self.settings.min_action_delay,
            self.settings.max_action_delay,
            self._rng,
        )
        if cancel.wait(delay):
            raise ActionCancelled("Mouse action cancelled during the humanized pause.")

    def _record_success(self) -> None:
        with self._failure_lock:
            self._consecutive_failures = 0

    def _record_failure(self, error: Exception) -> None:
        with self._failure_lock:
            self._consecutive_failures += 1
            count = self._consecutive_failures
        if count >= self._failure_threshold:
            self.emergency_stop("consecutive_failure_threshold")

    def _failure_text(self, error: Exception) -> str:
        with self._failure_lock:
            count = self._consecutive_failures
        suffix = " Emergency stop triggered." if count >= self._failure_threshold else ""
        return f"{error}{suffix}"

    def _start_escape_listener(self) -> None:
        if platform.system().lower() != "windows":
            return
        try:
            from pynput import keyboard

            def on_press(key: Any) -> None:
                if key == keyboard.Key.esc:
                    self.emergency_stop("escape_key")

            self._keyboard_listener = keyboard.Listener(on_press=on_press)
            self._keyboard_listener.daemon = True
            self._keyboard_listener.start()
            LOGGER.info("Global Escape emergency stop is active")
        except Exception:
            LOGGER.warning("Could not start global Escape listener", exc_info=True)
            self._keyboard_listener = None

    def _desktop_available(self) -> bool:
        return self.desktop is not None and self.desktop.available()

    def _cloud_available(self) -> bool:
        return self.cloud is not None

    @staticmethod
    def _create_desktop_driver(poll_interval: float) -> DesktopDriver | None:
        if platform.system().lower() != "windows":
            return None
        try:
            return DesktopDriver(poll_interval=poll_interval)
        except Exception:
            LOGGER.exception("Desktop driver initialization failed")
            return None

    @staticmethod
    def _create_cloud_driver(settings: Settings) -> CloudBrowserDriver | None:
        if settings.cloud_browser_mode == "off" or not cloud_browser_supported():
            return None
        return CloudBrowserDriver(
            headless=settings.cloud_browser_headless,
            viewport_width=settings.cloud_browser_viewport_width,
            viewport_height=settings.cloud_browser_viewport_height,
            user_data_dir=settings.cloud_browser_user_data_dir,
            executable=settings.cloud_browser_executable,
            allow_private_urls=settings.cloud_allow_private_urls,
            poll_interval=settings.screen_poll_interval,
        )
