from __future__ import annotations

import os
import platform

import pytest

from mouse_mcp import local_browser
from mouse_mcp.errors import MouseMcpError


def test_local_browser_rejects_non_http_urls() -> None:
    with pytest.raises(MouseMcpError, match="absolute http"):
        local_browser.validate_http_url("file:///C:/Windows/System32/calc.exe")


def test_windows_default_browser_uses_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(os, "startfile", lambda url: opened.append(url), raising=False)

    result = local_browser.open_local_url("https://example.com/")

    assert opened == ["https://example.com/"]
    assert result["method"] == "windows-shell-default-browser"


def test_named_browser_must_be_supported() -> None:
    with pytest.raises(MouseMcpError, match="default.*edge.*chrome"):
        local_browser.open_local_url("https://example.com/", "firefox")
