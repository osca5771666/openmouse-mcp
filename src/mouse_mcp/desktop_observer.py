from __future__ import annotations

import ctypes
import platform
from typing import Any


def collect_desktop_context() -> dict[str, Any]:
    """Return screenshot-coordinate metadata for the Windows desktop."""
    if platform.system().lower() != "windows":
        return {"environment": "desktop", "available": False}
    try:
        import psutil
        import win32api
        import win32gui
        import win32process
    except Exception as exc:
        return {
            "environment": "desktop",
            "available": False,
            "error": f"Windows inspection dependencies are unavailable: {exc}",
        }

    try:
        import pyautogui

        physical_width, physical_height = pyautogui.size()
    except Exception:
        physical_width = int(ctypes.windll.user32.GetSystemMetrics(0))
        physical_height = int(ctypes.windll.user32.GetSystemMetrics(1))

    logical_width = max(1, int(ctypes.windll.user32.GetSystemMetrics(0)))
    logical_height = max(1, int(ctypes.windll.user32.GetSystemMetrics(1)))
    scale_x = physical_width / logical_width
    scale_y = physical_height / logical_height

    def scaled_rect(rect: tuple[int, int, int, int]) -> dict[str, int]:
        left, top, right, bottom = rect
        return {
            "x": round(left * scale_x),
            "y": round(top * scale_y),
            "width": round((right - left) * scale_x),
            "height": round((bottom - top) * scale_y),
            "right": round(right * scale_x),
            "bottom": round(bottom * scale_y),
        }

    def process_name(pid: int) -> str:
        try:
            return psutil.Process(pid).name()
        except Exception:
            return ""

    foreground_hwnd = int(win32gui.GetForegroundWindow())
    active_window = _window_info(
        foreground_hwnd,
        foreground_hwnd,
        physical_width,
        physical_height,
        scale_x,
        scale_y,
        process_name,
        win32gui,
        win32process,
    )

    monitors: list[dict[str, Any]] = []
    try:
        for index, (hmonitor, _hdc, _rect) in enumerate(win32api.EnumDisplayMonitors()):
            info = win32api.GetMonitorInfo(hmonitor)
            monitors.append(
                {
                    "index": index,
                    "device": info.get("Device", ""),
                    "primary": bool(info.get("Flags", 0) & 1),
                    "bounds": scaled_rect(info["Monitor"]),
                    "work_area": scaled_rect(info["Work"]),
                }
            )
    except Exception:
        monitors = []

    taskbars: list[dict[str, Any]] = []
    for window_class in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        hwnd = int(win32gui.FindWindow(window_class, None) or 0)
        if not hwnd:
            continue
        taskbars.append(
            {
                "class": window_class,
                "hwnd": hwnd,
                "visible": bool(win32gui.IsWindowVisible(hwnd)),
                "rect": scaled_rect(win32gui.GetWindowRect(hwnd)),
            }
        )

    windows: list[dict[str, Any]] = []

    def enum_window(hwnd: int, _extra: Any) -> None:
        if len(windows) >= 80 or not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        info = _window_info(
            hwnd,
            foreground_hwnd,
            physical_width,
            physical_height,
            scale_x,
            scale_y,
            process_name,
            win32gui,
            win32process,
        )
        if info is not None:
            windows.append(info)

    try:
        win32gui.EnumWindows(enum_window, None)
    except Exception:
        pass
    windows.sort(key=lambda item: (not item["foreground"], item["process"].lower(), item["title"].lower()))

    return {
        "environment": "desktop",
        "available": True,
        "screen": {
            "width": physical_width,
            "height": physical_height,
            "logical_width": logical_width,
            "logical_height": logical_height,
            "dpi_scale_x": scale_x,
            "dpi_scale_y": scale_y,
            "coordinate_space": "physical desktop pixels used by PyAutoGUI and screenshots",
        },
        "active_window": active_window,
        "taskbars": taskbars,
        "monitors": monitors,
        "visible_windows": windows,
        "notes": [
            "Taskbar icons are visual targets. Capture a fresh screenshot before clicking them.",
            "Window rectangles are converted to the same physical pixel space as the screenshot.",
            "Mixed per-monitor DPI layouts may require visual re-verification after moving between monitors.",
        ],
    }


def _window_info(
    hwnd: int,
    foreground_hwnd: int,
    physical_width: int,
    physical_height: int,
    scale_x: float,
    scale_y: float,
    process_name: Any,
    win32gui: Any,
    win32process: Any,
) -> dict[str, Any] | None:
    if not hwnd:
        return None
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        rect = {
            "x": round(left * scale_x),
            "y": round(top * scale_y),
            "width": round((right - left) * scale_x),
            "height": round((bottom - top) * scale_y),
            "right": round(right * scale_x),
            "bottom": round(bottom * scale_y),
        }
        if rect["width"] <= 0 or rect["height"] <= 0:
            return None
        _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        return {
            "hwnd": hwnd,
            "title": win32gui.GetWindowText(hwnd),
            "class_name": win32gui.GetClassName(hwnd),
            "process": process_name(pid),
            "pid": pid,
            "foreground": hwnd == foreground_hwnd,
            "minimized": bool(win32gui.IsIconic(hwnd)),
            "rect": rect,
            "onscreen": _intersects_screen(rect, physical_width, physical_height),
        }
    except Exception:
        return None


def _intersects_screen(rect: dict[str, int], width: int, height: int) -> bool:
    return (
        rect["right"] > 0
        and rect["bottom"] > 0
        and rect["x"] < width
        and rect["y"] < height
    )
