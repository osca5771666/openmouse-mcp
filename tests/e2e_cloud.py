from __future__ import annotations

import functools
import http.server
import json
import threading
from pathlib import Path

from mouse_mcp.config import Settings
from mouse_mcp.runtime import MouseRuntime


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"


def start_demo_server() -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(DEMO),
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, int(server.server_address[1])


def main() -> None:
    server, port = start_demo_server()
    runtime = MouseRuntime(
        Settings(
            environment_mode="cloud",
            cloud_browser_mode="on",
            cloud_browser_headless=True,
            cloud_browser_viewport_width=1280,
            cloud_browser_viewport_height=800,
            cloud_allow_private_urls=True,
            min_action_delay=0.0,
            max_action_delay=0.0,
        )
    )
    try:
        opened = runtime.open_browser_url(
            f"http://127.0.0.1:{port}/browser-demo.html"
        )
        assert opened["environment"] == "cloud"

        box = runtime.runner.submit(
            lambda _cancel: runtime.cloud._page.locator("#save-note").bounding_box()
        )
        assert box is not None
        clicked = runtime.act(
            "click",
            {
                "x": round(box["x"] + box["width"] / 2),
                "y": round(box["y"] + box["height"] / 2),
                "button": "left",
                "clicks": 1,
                "intent": "click Save note in the cloud browser",
                "target_description": "Save note",
                "risk_approved": False,
            },
        )
        assert clicked["environment"] == "cloud"
        assert clicked["trusted_events"] is True

        save_count = runtime.runner.submit(
            lambda _cancel: runtime.cloud._page.locator("#save-count").inner_text()
        )
        assert save_count == "1"

        observation = runtime.observe()
        metadata = observation.metadata
        assert metadata["environment"] == "cloud"
        assert metadata["viewport_width"] == 1280
        assert metadata["viewport_height"] == 800
        assert len(observation.data_base64) > 1000
        print(
            json.dumps(
                {
                    "cloud_e2e": "ok",
                    "url": opened["url"],
                    "save_count": save_count,
                    "trusted_events": clicked["trusted_events"],
                    "screenshot_base64_chars": len(observation.data_base64),
                },
                ensure_ascii=True,
                indent=2,
            )
        )
    finally:
        runtime.close()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
