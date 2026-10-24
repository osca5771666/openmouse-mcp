from __future__ import annotations

import os
import platform
import random
import ipaddress
import socket
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .errors import ActionCancelled, BoundaryViolation, HighRiskBlocked, MouseMcpError
from .humanize import Point, build_trajectory
from .safety import classify_risk


@dataclass(frozen=True)
class CloudCapture:
    data: bytes
    width: int
    height: int
    metadata: dict[str, Any]
    format: str = "png"


_CURSOR_INIT_SCRIPT = """
(() => {
  if (window.__openMouseCloudCursor) return;
  const build = () => {
    if (!document.documentElement || window.__openMouseCloudCursor) return;
    const host = document.createElement("div");
    host.setAttribute("data-openmouse-cloud-cursor", "true");
    Object.assign(host.style, {
      position: "fixed",
      left: "0",
      top: "0",
      width: "20px",
      height: "20px",
      borderRadius: "50%",
      border: "2px solid #ff5a36",
      background: "radial-gradient(circle at center, #ff5a36 0 2px, transparent 3px)",
      boxShadow: "0 0 0 1px rgba(255,255,255,.85), 0 1px 5px rgba(0,0,0,.35)",
      pointerEvents: "none",
      zIndex: "2147483647",
      transform: "translate(-40px, -40px)",
      willChange: "transform"
    });
    document.documentElement.appendChild(host);
    window.__openMouseCloudCursor = {
      move(x, y) {
        host.style.transform = `translate(${x - 10}px, ${y - 10}px)`;
      },
      visible(value) {
        host.style.display = value ? "block" : "none";
      }
    };
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build, { once: true });
  } else {
    build();
  }
})();
"""


class CloudBrowserDriver:
    """Headless Chromium target running inside the MCP process."""

    def __init__(
        self,
        headless: bool = True,
        viewport_width: int = 1440,
        viewport_height: int = 900,
        user_data_dir: str | None = None,
        executable: str | None = None,
        allow_private_urls: bool = False,
        poll_interval: float = 0.02,
    ) -> None:
        self._headless = headless
        self._viewport_width = max(320, viewport_width)
        self._viewport_height = max(240, viewport_height)
        self._configured_user_data_dir = user_data_dir
        self._configured_executable = executable
        self._allow_private_urls = allow_private_urls
        self._poll_interval = poll_interval
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None
        self._position = {
            "x": self._viewport_width / 2,
            "y": self._viewport_height / 2,
        }
        self._rng = random.Random()
        self._temp_user_data_dir: str | None = None
        self._closed = False

    def open_url(self, url: str, cancel: threading.Event) -> dict[str, Any]:
        self._ensure_started(cancel)
        parsed = urlparse(url)
        if url != "about:blank" and parsed.scheme not in {"http", "https"}:
            raise MouseMcpError("Cloud browser URLs must use http:// or https://.")
        if url != "about:blank":
            default_port = 443 if parsed.scheme == "https" else 80
            self._validate_public_url(parsed.hostname, parsed.port or default_port)
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            raise MouseMcpError(f"Cloud browser navigation failed: {exc}") from exc
        self._install_cursor_overlay()
        self._check_cancel(cancel)
        return self._page_metadata()

    def _validate_public_url(self, hostname: str | None, port: int | None) -> None:
        if self._allow_private_urls:
            return
        if not hostname:
            raise MouseMcpError("Cloud browser URL has no hostname.")
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(
                    hostname,
                    port,
                    type=socket.SOCK_STREAM,
                )
            }
        except OSError as exc:
            raise MouseMcpError(f"Cloud browser hostname resolution failed: {hostname}") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_unspecified
                or ip.is_reserved
            ):
                raise MouseMcpError(
                    "Cloud browser blocked a private or special network address. "
                    "Set MOUSE_MCP_CLOUD_ALLOW_PRIVATE_URLS=1 only in a trusted environment."
                )

    def position(self, _cancel: threading.Event) -> dict[str, Any]:
        self._ensure_started(_cancel)
        return {
            "x": round(self._position["x"]),
            "y": round(self._position["y"]),
            "environment": "cloud",
            **self._viewport(),
        }

    def move(self, x: int, y: int, cancel: threading.Event) -> dict[str, Any]:
        self._ensure_started(cancel)
        width, height = self._viewport_size()
        target = Point(
            max(0, min(width - 1, x)),
            max(0, min(height - 1, y)),
        )
        self._animate(Point(self._position["x"], self._position["y"]), target, cancel)
        return {
            "x": round(target.x),
            "y": round(target.y),
            "clamped": round(target.x) != x or round(target.y) != y,
        }

    def click(
        self,
        x: int | None,
        y: int | None,
        button: str,
        clicks: int,
        params: dict[str, Any],
        cancel: threading.Event,
    ) -> dict[str, Any]:
        self._ensure_started(cancel)
        if x is not None and y is not None:
            self._validate_target(x, y)
            self.move(x, y, cancel)
        self._guard_target(params, cancel)
        self._check_cancel(cancel)
        self._page.mouse.click(
            self._position["x"],
            self._position["y"],
            button=button,
            click_count=clicks,
            delay=self._rng.uniform(35, 90),
        )
        return {
            "x": round(self._position["x"]),
            "y": round(self._position["y"]),
            "button": button,
            "clicks": clicks,
            "trusted_events": True,
        }

    def drag(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        button: str,
        params: dict[str, Any],
        cancel: threading.Event,
    ) -> dict[str, Any]:
        self._ensure_started(cancel)
        self._validate_target(from_x, from_y)
        self._validate_target(to_x, to_y)
        self.move(from_x, from_y, cancel)
        self._guard_target({**params, "x": from_x, "y": from_y}, cancel)
        self._check_cancel(cancel)
        self._page.mouse.down(button=button)
        try:
            self._animate(
                Point(from_x, from_y),
                Point(to_x, to_y),
                cancel,
                longer_pause=True,
            )
            self._check_cancel(cancel)
        finally:
            try:
                self._page.mouse.up(button=button)
            except Exception:
                pass
        return {
            "from": {"x": from_x, "y": from_y},
            "to": {"x": to_x, "y": to_y},
            "button": button,
            "trusted_events": True,
        }

    def scroll(
        self,
        direction: str,
        clicks: int,
        x: int | None,
        y: int | None,
        params: dict[str, Any],
        cancel: threading.Event,
    ) -> dict[str, Any]:
        self._ensure_started(cancel)
        if x is not None and y is not None:
            self._validate_target(x, y)
            self.move(x, y, cancel)
        self._guard_target(params, cancel)
        amount = clicks * 110
        delta_y = amount if direction == "down" else -amount
        self._page.mouse.wheel(0, delta_y)
        self._check_cancel(cancel)
        scroll_y = float(
            self._page.evaluate("() => window.scrollY || document.documentElement.scrollTop || 0")
        )
        return {
            "direction": direction,
            "clicks": clicks,
            "delta_y": delta_y,
            "page_scroll_y": scroll_y,
            "trusted_events": True,
        }

    def capture(self, cancel: threading.Event) -> CloudCapture:
        self._ensure_started(cancel)
        self._check_cancel(cancel)
        width, height = self._viewport_size()
        try:
            self._page.evaluate(
                "() => window.__openMouseCloudCursor?.visible(false)"
            )
            cancel.wait(0.05)
            self._check_cancel(cancel)
            data = self._page.screenshot(type="png")
        finally:
            try:
                self._page.evaluate(
                    "() => window.__openMouseCloudCursor?.visible(true)"
                )
            except Exception:
                pass
        metadata = {
            "environment": "cloud",
            **self._page_metadata(),
            "image_width": width,
            "image_height": height,
            "coordinate_space": "CSS viewport pixels",
            "virtual_cursor": {
                "x": round(self._position["x"]),
                "y": round(self._position["y"]),
                "visible": False,
            },
        }
        return CloudCapture(
            data=data,
            width=width,
            height=height,
            metadata=metadata,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        if self._temp_user_data_dir:
            try:
                import shutil

                shutil.rmtree(self._temp_user_data_dir, ignore_errors=True)
            except Exception:
                pass
            self._temp_user_data_dir = None

    def _ensure_started(self, cancel: threading.Event) -> None:
        if self._page is not None:
            return
        self._check_cancel(cancel)
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise MouseMcpError(
                "Cloud browser requires the optional Playwright dependency: "
                "pip install 'openmouse-mcp[cloud]'."
            ) from exc

        user_data_dir = self._configured_user_data_dir
        if not user_data_dir:
            self._temp_user_data_dir = tempfile.mkdtemp(prefix="openmouse-cloud-")
            user_data_dir = self._temp_user_data_dir
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        executable = self._configured_executable or _find_playwright_chromium()
        launch_args: dict[str, Any] = {
            "user_data_dir": user_data_dir,
            "headless": self._headless,
            "viewport": {
                "width": self._viewport_width,
                "height": self._viewport_height,
            },
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if executable:
            launch_args["executable_path"] = executable
        try:
            self._playwright = sync_playwright().start()
            self._context = self._playwright.chromium.launch_persistent_context(**launch_args)
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            self._context.add_init_script(_CURSOR_INIT_SCRIPT)
            self._page.goto("about:blank", wait_until="domcontentloaded", timeout=15000)
            self._install_cursor_overlay()
            self._sync_position_to_center()
        except Exception as exc:
            self.close()
            raise MouseMcpError(f"Could not start cloud Chromium: {exc}") from exc

    def _install_cursor_overlay(self) -> None:
        try:
            self._page.evaluate(_CURSOR_INIT_SCRIPT)
            self._page.evaluate(
                "([x,y]) => window.__openMouseCloudCursor?.move(x,y)",
                [self._position["x"], self._position["y"]],
            )
        except Exception:
            pass

    def _sync_position_to_center(self) -> None:
        width, height = self._viewport_size()
        self._position = {"x": width / 2, "y": height / 2}

    def _animate(
        self,
        start: Point,
        end: Point,
        cancel: threading.Event,
        longer_pause: bool = False,
    ) -> None:
        trajectory = build_trajectory(start, end, self._rng)
        for index, step in enumerate(trajectory):
            self._check_cancel(cancel)
            delay = step.delay
            if longer_pause and delay > 0 and self._rng.random() < 0.35:
                delay *= self._rng.uniform(1.1, 1.6)
            if delay > 0 and cancel.wait(delay):
                raise ActionCancelled("Cloud browser action cancelled.")
            self._page.mouse.move(step.point.x, step.point.y)
            self._position = {"x": step.point.x, "y": step.point.y}
            if index % 2 == 0 or index == len(trajectory) - 1:
                try:
                    self._page.evaluate(
                        "([x,y]) => window.__openMouseCloudCursor?.move(x,y)",
                        [step.point.x, step.point.y],
                    )
                except Exception:
                    pass

    def _guard_target(self, params: dict[str, Any], cancel: threading.Event) -> None:
        if params.get("risk_approved"):
            return
        try:
            target = self._page.evaluate(
                """
                ([x, y]) => {
                  const element = document.elementFromPoint(x, y);
                  if (!element) return null;
                  const semantic = element.closest(
                    "button, a, input, textarea, select, [role='button'], [role='link'], [role='menuitem']"
                  ) || element;
                  const form = element.closest ? element.closest("form") : null;
                  return {
                    text: [
                      semantic.innerText,
                      semantic.textContent,
                      semantic.getAttribute?.("aria-label"),
                      semantic.getAttribute?.("title"),
                      semantic.getAttribute?.("name"),
                      semantic.getAttribute?.("value"),
                      semantic.getAttribute?.("data-openmouse-risk")
                    ].filter(Boolean).join(" ").replace(/\\s+/g, " ").slice(0, 800),
                    marked_high: Boolean(
                      element.closest?.("[data-openmouse-risk='high']")
                    ),
                    form_fields: form
                      ? form.querySelectorAll("input, select, textarea").length
                      : 0
                  };
                }
                """,
                [self._position["x"], self._position["y"]],
            )
        except Exception:
            target = None
        self._check_cancel(cancel)
        if not target:
            return
        combined = " | ".join(
            str(value)
            for value in (
                target.get("text"),
                params.get("intent"),
                params.get("target_description"),
            )
            if value
        )
        assessment = classify_risk(combined)
        evidence = list(assessment.evidence)
        if target.get("marked_high"):
            evidence.append("target is marked data-openmouse-risk=high")
        if int(target.get("form_fields") or 0) >= 10:
            evidence.append("target form contains 10 or more fields")
        if evidence:
            raise HighRiskBlocked(
                "High-risk cloud browser target detected before dispatch.",
                evidence=list(dict.fromkeys(evidence)),
            )

    def _validate_target(self, x: int, y: int) -> None:
        width, height = self._viewport_size()
        if x < 0 or y < 0 or x >= width or y >= height:
            raise BoundaryViolation(
                f"Target ({x}, {y}) is outside the cloud viewport 0..{width - 1}, "
                f"0..{height - 1}."
            )

    def _viewport_size(self) -> tuple[int, int]:
        viewport = self._page.viewport_size if self._page is not None else None
        if viewport:
            return int(viewport["width"]), int(viewport["height"])
        return self._viewport_width, self._viewport_height

    def _viewport(self) -> dict[str, Any]:
        width, height = self._viewport_size()
        return {
            "width": width,
            "height": height,
            "device_pixel_ratio": 1.0,
            "scroll_x": 0,
            "scroll_y": 0,
        }

    def _page_metadata(self) -> dict[str, Any]:
        width, height = self._viewport_size()
        try:
            scroll = self._page.evaluate(
                "() => ({x: window.scrollX, y: window.scrollY})"
            )
        except Exception:
            scroll = {"x": 0, "y": 0}
        return {
            "url": self._page.url,
            "title": self._page.title(),
            "viewport_width": width,
            "viewport_height": height,
            "device_pixel_ratio": 1.0,
            "scroll_x": scroll.get("x", 0),
            "scroll_y": scroll.get("y", 0),
        }

    @staticmethod
    def _check_cancel(cancel: threading.Event) -> None:
        if cancel.is_set():
            raise ActionCancelled("Cloud browser action cancelled.")


def cloud_browser_supported() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("playwright") is not None
    except Exception:
        return False


def _find_playwright_chromium() -> str | None:
    if platform.system().lower() != "windows":
        return None
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    candidates = sorted(root.glob("chromium-*/chrome-win64/chrome.exe"), reverse=True)
    return str(candidates[0]) if candidates else None
