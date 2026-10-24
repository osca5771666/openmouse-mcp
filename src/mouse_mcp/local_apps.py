from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .errors import MouseMcpError


APP_ALIASES: dict[str, tuple[str, ...]] = {
    "feishu": ("feishu", "lark", "飞书"),
    "notepad": ("notepad", "记事本"),
    "explorer": ("explorer", "文件资源管理器"),
    "cmd": ("cmd", "命令提示符"),
    "powershell": ("powershell",),
    "calculator": ("calc", "calculator", "计算器"),
    "edge": ("msedge", "microsoft edge"),
    "chrome": ("chrome", "google chrome"),
}
_SHORTCUT_CACHE: list[Path] | None = None
_RUNNING_EXECUTABLE_CACHE: dict[str, str] = {}


def open_local_app(name: str) -> dict[str, str]:
    normalized = name.strip().lower()
    if not normalized or len(normalized) > 100:
        raise MouseMcpError("Application name is empty or too long.")
    candidates = APP_ALIASES.get(normalized, (normalized,))

    existing = _focus_existing(candidates)
    if existing:
        return {"app": normalized, "method": "focused-existing-window", "window": existing}

    executable = _find_executable(candidates)
    if executable:
        try:
            subprocess.Popen(
                [executable],
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise MouseMcpError(f"Could not launch {name}: {exc}") from exc
        return {"app": normalized, "method": executable}

    running_executable = _find_running_executable(candidates)
    if running_executable:
        if hasattr(os, "startfile"):
            os.startfile(running_executable)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(
                [running_executable],
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return {
            "app": normalized,
            "method": "activated-running-executable",
            "executable": running_executable,
        }

    shortcut = _find_start_menu_shortcut(candidates)
    if shortcut:
        if not hasattr(os, "startfile"):
            raise MouseMcpError("Start Menu shortcuts are only supported on Windows.")
        os.startfile(str(shortcut))  # type: ignore[attr-defined]
        return {"app": normalized, "method": "start-menu-shortcut", "shortcut": str(shortcut)}

    raise MouseMcpError(f"Could not find an installed application matching '{name}'.")


def _focus_existing(candidates: tuple[str, ...]) -> str | None:
    try:
        import psutil
        import win32con
        import win32gui
    except Exception:
        return None

    windows: list[tuple[int, int, str]] = []

    def enum_window(hwnd: int, _extra: object) -> None:
        _thread, pid = win32gui.GetWindowThreadProcessId(hwnd)
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title or win32gui.GetClassName(hwnd) in {"Progman", "WorkerW"}:
            return
        windows.append((hwnd, pid, title))

    try:
        win32gui.EnumWindows(enum_window, None)
    except Exception:
        return None

    matched: list[tuple[int, str]] = []
    process_cache: dict[int, tuple[str, str]] = {}
    for hwnd, pid, title in windows:
        try:
            if pid not in process_cache:
                process = psutil.Process(pid)
                process_cache[pid] = (
                    process.name().lower(),
                    Path(process.exe()).stem.lower() if process.exe() else "",
                )
            name, stem = process_cache[pid]
            if any(candidate in name or candidate == stem for candidate in candidates):
                matched.append((hwnd, title))
        except Exception:
            continue
    if not matched:
        return None
    hwnd, title = matched[0]
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception as exc:
        raise MouseMcpError(f"Could not focus an existing window: {exc}") from exc
    return title


def _find_executable(candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
        found = shutil.which(f"{candidate}.exe")
        if found:
            return found
    known_paths = (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Feishu" / "app" / "Feishu.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Feishu" / "Feishu.exe",
    )
    for path in known_paths:
        if path.is_file() and any(alias in path.name.lower() for alias in candidates):
            return str(path)
    return None


def _find_running_executable(candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        cached = _RUNNING_EXECUTABLE_CACHE.get(candidate)
        if cached and Path(cached).is_file():
            return cached
    try:
        import psutil
    except Exception:
        return None
    found_paths: dict[str, int] = {}
    for process in psutil.process_iter(["name", "exe"]):
        try:
            name = (process.info.get("name") or "").lower()
            exe = process.info.get("exe") or ""
            if not exe:
                continue
            stem = Path(exe).stem.lower()
            if any(candidate in name or candidate == stem for candidate in candidates):
                found_paths[exe] = found_paths.get(exe, 0) + 1
        except Exception:
            continue
    if not found_paths:
        return None
    result = max(found_paths, key=found_paths.get)
    for candidate in candidates:
        _RUNNING_EXECUTABLE_CACHE[candidate] = result
    return result


def _find_start_menu_shortcut(candidates: tuple[str, ...]) -> Path | None:
    global _SHORTCUT_CACHE
    if _SHORTCUT_CACHE is None:
        _SHORTCUT_CACHE = _index_start_menu_shortcuts()
    for shortcut in _SHORTCUT_CACHE:
        stem = shortcut.stem.lower()
        if any(candidate in stem for candidate in candidates):
            return shortcut
    return None


def _index_start_menu_shortcuts() -> list[Path]:
    roots = []
    for env_name in ("APPDATA", "PROGRAMDATA"):
        value = os.getenv(env_name)
        if value:
            roots.append(Path(value) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    shortcuts: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            shortcuts.extend(root.rglob("*.lnk"))
        except OSError:
            continue
    return shortcuts
