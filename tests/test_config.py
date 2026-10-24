from __future__ import annotations

from mouse_mcp.config import Settings


def test_fast_profile_uses_short_default_action_delays(monkeypatch) -> None:
    monkeypatch.setenv("MOUSE_MCP_SPEED_PROFILE", "fast")
    monkeypatch.delenv("MOUSE_MCP_MIN_ACTION_DELAY", raising=False)
    monkeypatch.delenv("MOUSE_MCP_MAX_ACTION_DELAY", raising=False)

    settings = Settings.from_env()

    assert settings.speed_profile == "fast"
    assert settings.min_action_delay == 0.04
    assert settings.max_action_delay == 0.16
