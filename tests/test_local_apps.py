from __future__ import annotations

import pytest

from mouse_mcp import local_apps
from mouse_mcp.errors import MouseMcpError


def test_app_open_focuses_existing_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_apps, "_focus_existing", lambda candidates: "Feishu")

    result = local_apps.open_local_app("feishu")

    assert result["method"] == "focused-existing-window"
    assert result["window"] == "Feishu"


def test_app_open_reports_missing_application(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_apps, "_focus_existing", lambda candidates: None)
    monkeypatch.setattr(local_apps, "_find_executable", lambda candidates: None)
    monkeypatch.setattr(local_apps, "_find_start_menu_shortcut", lambda candidates: None)

    with pytest.raises(MouseMcpError, match="Could not find"):
        local_apps.open_local_app("missing-app")


def test_app_open_reactivates_running_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: list[str] = []
    monkeypatch.setattr(local_apps, "_focus_existing", lambda candidates: None)
    monkeypatch.setattr(local_apps, "_find_executable", lambda candidates: None)
    monkeypatch.setattr(
        local_apps,
        "_find_running_executable",
        lambda candidates: r"C:\Apps\Feishu.exe",
    )
    monkeypatch.setattr(
        local_apps.os,
        "startfile",
        lambda path: launched.append(path),
        raising=False,
    )

    result = local_apps.open_local_app("feishu")

    assert launched == [r"C:\Apps\Feishu.exe"]
    assert result["method"] == "activated-running-executable"
