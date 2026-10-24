from __future__ import annotations

import os
import platform
import shutil
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from .errors import MouseMcpError


def validate_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise MouseMcpError("Browser URLs must be absolute http:// or https:// URLs.")


def open_local_url(url: str, browser: str = "default") -> dict[str, str]:
    """Open a URL without GUI automation so simple navigation stays fast."""
    validate_http_url(url)
    browser = browser.strip().lower()
    if browser == "default":
        if platform.system().lower() == "windows" and hasattr(os, "startfile"):
            os.startfile(url)  # type: ignore[attr-defined]
            method = "windows-shell-default-browser"
        else:
            if not webbrowser.open_new_tab(url):
                raise MouseMcpError("The default browser rejected the URL.")
            method = "webbrowser-default"
        return {"url": url, "browser": "default", "method": method}

    executable = _browser_executable(browser)
    try:
        subprocess.Popen(
            [executable, url],
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise MouseMcpError(f"Could not launch {browser}: {exc}") from exc
    return {"url": url, "browser": browser, "method": executable}


def _browser_executable(browser: str) -> str:
    names = {
        "edge": ("msedge", "msedge.exe"),
        "chrome": ("chrome", "chrome.exe"),
    }
    if browser not in names:
        raise MouseMcpError("browser must be 'default', 'edge', or 'chrome'.")
    for name in names[browser]:
        found = shutil.which(name)
        if found:
            return found
    candidates = {
        "edge": (
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        ),
        "chrome": (
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        ),
    }
    for candidate in candidates[browser]:
        if candidate.is_file():
            return str(candidate)
    raise MouseMcpError(f"{browser.title()} is not installed or could not be found.")
