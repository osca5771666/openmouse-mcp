from __future__ import annotations

import platform

import pytest

from mouse_mcp.desktop_observer import collect_desktop_context


@pytest.mark.skipif(platform.system().lower() != "windows", reason="Windows only")
def test_desktop_observer_reports_taskbar_and_coordinate_space() -> None:
    context = collect_desktop_context()

    assert context["available"] is True
    assert context["screen"]["width"] > 0
    assert context["screen"]["height"] > 0
    assert context["screen"]["coordinate_space"].startswith("physical desktop pixels")
    assert context["taskbars"]
    assert context["taskbars"][0]["rect"]["width"] > 0
    assert context["active_window"] is not None
