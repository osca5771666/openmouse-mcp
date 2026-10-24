from __future__ import annotations

import io
import random
import threading
import time
from dataclasses import dataclass
from typing import Any

from .errors import ActionCancelled, BoundaryViolation, MouseMcpError
from .humanize import Point, build_trajectory


@dataclass(frozen=True)
class DesktopCapture:
    data: bytes
    width: int
    height: int
    format: str = "png"


class DesktopDriver:
    """PyAutoGUI-backed Windows desktop driver."""

    def __init__(self, poll_interval: float = 0.02) -> None:
        try:
            import pyautogui
        except Exception as exc:
            raise MouseMcpError(f"PyAutoGUI is unavailable: {exc}") from exc
        self._pyautogui = pyautogui
        self._poll_interval = poll_interval
        self._rng = random.Random()
        self._button_lock = threading.Lock()
        self._pressed_button: str | None = None
        self._size = self._read_size()

    def available(self) -> bool:
        try:
            self._size = self._read_size()
            return self._size[0] > 0 and self._size[1] > 0
        except Exception:
            return False

    def _read_size(self) -> tuple[int, int]:
        size = self._pyautogui.size()
        return int(size.width), int(size.height)

    def screen_size(self) -> tuple[int, int]:
        self._size = self._read_size()
        return self._size

    def position(self, _cancel: threading.Event) -> dict[str, Any]:
        x, y = self._pyautogui.position()
        return {"x": int(x), "y": int(y), "screen_width": self._size[0], "screen_height": self._size[1]}

    def move(
        self,
        x: int,
        y: int,
        cancel: threading.Event,
    ) -> dict[str, Any]:
        width, height = self.screen_size()
        target = Point(max(0, min(width - 1, x)), max(0, min(height - 1, y)))
        start_x, start_y = self._pyautogui.position()
        self._animate(Point(float(start_x), float(start_y)), target, cancel)
        return {
            "x": int(target.x),
            "y": int(target.y),
            "clamped": int(target.x) != x or int(target.y) != y,
        }

    def click(
        self,
        x: int | None,
        y: int | None,
        button: str,
        clicks: int,
        cancel: threading.Event,
    ) -> dict[str, Any]:
        if x is not None and y is not None:
            self._validate_target(x, y)
            self.move(x, y, cancel)
        self._check_cancel(cancel)
        interval = self._rng.uniform(0.08, 0.2)
        self._pyautogui.click(
            button=button,
            clicks=clicks,
            interval=interval,
            _pause=False,
        )
        pos_x, pos_y = self._pyautogui.position()
        return {"x": int(pos_x), "y": int(pos_y), "button": button, "clicks": clicks}

    def drag(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        button: str,
        cancel: threading.Event,
    ) -> dict[str, Any]:
        self._validate_target(from_x, from_y)
        self._validate_target(to_x, to_y)
        self.move(from_x, from_y, cancel)
        self._check_cancel(cancel)
        with self._button_lock:
            self._pyautogui.mouseDown(button=button, _pause=False)
            self._pressed_button = button
        try:
            self._animate(
                Point(float(from_x), float(from_y)),
                Point(float(to_x), float(to_y)),
                cancel,
                longer_pause=True,
            )
            self._check_cancel(cancel)
        finally:
            with self._button_lock:
                if self._pressed_button is not None:
                    try:
                        self._pyautogui.mouseUp(button=self._pressed_button, _pause=False)
                    finally:
                        self._pressed_button = None
        return {
            "from": {"x": from_x, "y": from_y},
            "to": {"x": to_x, "y": to_y},
            "button": button,
        }

    def scroll(
        self,
        direction: str,
        clicks: int,
        cancel: threading.Event,
    ) -> dict[str, Any]:
        amount = clicks if direction == "up" else -clicks
        remaining = amount
        while remaining:
            self._check_cancel(cancel)
            chunk = 1 if remaining > 0 else -1
            self._pyautogui.scroll(chunk, _pause=False)
            remaining -= chunk
            if remaining:
                self._sleep(self._rng.uniform(0.035, 0.1), cancel)
        pos_x, pos_y = self._pyautogui.position()
        return {"x": int(pos_x), "y": int(pos_y), "direction": direction, "clicks": clicks}

    def screenshot(self, _cancel: threading.Event) -> DesktopCapture:
        image = self._pyautogui.screenshot()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return DesktopCapture(data=buffer.getvalue(), width=image.width, height=image.height)

    def release_buttons(self) -> None:
        with self._button_lock:
            if self._pressed_button is None:
                return
            button = self._pressed_button
            self._pressed_button = None
        try:
            self._pyautogui.mouseUp(button=button, _pause=False)
        except Exception:
            pass

    def _animate(
        self,
        start: Point,
        end: Point,
        cancel: threading.Event,
        longer_pause: bool = False,
    ) -> None:
        trajectory = build_trajectory(start, end, self._rng)
        for step in trajectory:
            self._check_cancel(cancel)
            delay = step.delay
            if longer_pause and delay > 0 and self._rng.random() < 0.35:
                delay *= self._rng.uniform(1.1, 1.6)
            self._sleep(delay, cancel)
            self._check_cancel(cancel)
            self._pyautogui.moveTo(round(step.point.x), round(step.point.y), _pause=False)

    def _validate_target(self, x: int, y: int) -> None:
        width, height = self.screen_size()
        if x < 0 or y < 0 or x >= width or y >= height:
            raise BoundaryViolation(
                f"Target ({x}, {y}) is outside the desktop bounds 0..{width - 1}, "
                f"0..{height - 1}."
            )

    def _sleep(self, seconds: float, cancel: threading.Event) -> None:
        if seconds <= 0:
            return
        if cancel.wait(seconds):
            raise ActionCancelled("Mouse action cancelled.")

    @staticmethod
    def _check_cancel(cancel: threading.Event) -> None:
        if cancel.is_set():
            raise ActionCancelled("Mouse action cancelled.")
