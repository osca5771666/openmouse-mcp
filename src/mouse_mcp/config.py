from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TOKEN = "local-dev-token"


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _read_token_file(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    token = path.read_text(encoding="utf-8").strip()
    return token or None


@dataclass(frozen=True)
class Settings:
    bridge_host: str = "127.0.0.1"
    bridge_port: int = 8765
    browser_token: str = DEFAULT_TOKEN
    heartbeat_timeout: float = 4.0
    command_timeout: float = 20.0
    screen_poll_interval: float = 0.02
    environment_mode: str = "auto"
    cloud_browser_mode: str = "auto"
    cloud_browser_headless: bool = True
    cloud_browser_viewport_width: int = 1440
    cloud_browser_viewport_height: int = 900
    cloud_browser_user_data_dir: str | None = None
    cloud_browser_executable: str | None = None
    cloud_allow_private_urls: bool = False
    http_auth_token: str | None = None
    http_allowed_hosts: tuple[str, ...] = ()
    speed_profile: str = "balanced"
    confirm_high_risk: bool = True
    min_action_delay: float = 0.2
    max_action_delay: float = 1.3

    @classmethod
    def from_env(cls) -> "Settings":
        project_root = Path(__file__).resolve().parents[2]
        token_file = Path(
            os.getenv("MOUSE_MCP_TOKEN_FILE", str(project_root / ".runtime" / "browser-token.txt"))
        ).expanduser()
        token = (
            os.getenv("MOUSE_MCP_BROWSER_TOKEN")
            or _read_token_file(token_file)
            or DEFAULT_TOKEN
        )
        mode = os.getenv("MOUSE_MCP_ENV", "auto").strip().lower()
        if mode not in {"auto", "browser", "desktop", "cloud"}:
            mode = "auto"
        cloud_mode = os.getenv("MOUSE_MCP_CLOUD_BROWSER", "auto").strip().lower()
        if cloud_mode not in {"auto", "on", "off"}:
            cloud_mode = "auto"
        speed_profile = os.getenv("MOUSE_MCP_SPEED_PROFILE", "balanced").strip().lower()
        if speed_profile not in {"fast", "balanced", "human"}:
            speed_profile = "balanced"
        delay_defaults = {
            "fast": (0.04, 0.16),
            "balanced": (0.2, 1.3),
            "human": (0.3, 1.5),
        }
        default_min_delay, default_max_delay = delay_defaults[speed_profile]
        return cls(
            bridge_host=os.getenv("MOUSE_MCP_BRIDGE_HOST", "127.0.0.1"),
            bridge_port=int(os.getenv("MOUSE_MCP_BRIDGE_PORT", "8765")),
            browser_token=token,
            heartbeat_timeout=float(os.getenv("MOUSE_MCP_HEARTBEAT_TIMEOUT", "4.0")),
            command_timeout=float(os.getenv("MOUSE_MCP_COMMAND_TIMEOUT", "20.0")),
            screen_poll_interval=float(os.getenv("MOUSE_MCP_SCREEN_POLL_INTERVAL", "0.02")),
            environment_mode=mode,
            cloud_browser_mode=cloud_mode,
            cloud_browser_headless=_bool_env("MOUSE_MCP_CLOUD_HEADLESS", True),
            cloud_browser_viewport_width=int(
                os.getenv("MOUSE_MCP_CLOUD_VIEWPORT_WIDTH", "1440")
            ),
            cloud_browser_viewport_height=int(
                os.getenv("MOUSE_MCP_CLOUD_VIEWPORT_HEIGHT", "900")
            ),
            cloud_browser_user_data_dir=os.getenv("MOUSE_MCP_CLOUD_USER_DATA_DIR"),
            cloud_browser_executable=os.getenv("MOUSE_MCP_CLOUD_CHROMIUM_EXECUTABLE"),
            cloud_allow_private_urls=_bool_env("MOUSE_MCP_CLOUD_ALLOW_PRIVATE_URLS", False),
            http_auth_token=os.getenv("MOUSE_MCP_HTTP_TOKEN") or None,
            http_allowed_hosts=tuple(
                item.strip()
                for item in os.getenv("MOUSE_MCP_HTTP_ALLOWED_HOSTS", "").split(",")
                if item.strip()
            ),
            confirm_high_risk=_bool_env("MOUSE_MCP_CONFIRM_HIGH_RISK", True),
            min_action_delay=float(
                os.getenv("MOUSE_MCP_MIN_ACTION_DELAY", str(default_min_delay))
            ),
            max_action_delay=float(
                os.getenv("MOUSE_MCP_MAX_ACTION_DELAY", str(default_max_delay))
            ),
            speed_profile=speed_profile,
        )

    @staticmethod
    def new_browser_token() -> str:
        return secrets.token_hex(24)
