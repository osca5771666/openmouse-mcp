from __future__ import annotations

import base64
import functools
import http.server
import json
import os
import tempfile
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from mouse_mcp.browser_bridge import BrowserBridge


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "browser-extension"
DEMO = ROOT / "demo"
CHROME_CANDIDATES = (
    *sorted(
        (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "ms-playwright"
        ).glob("chromium-*/chrome-win64/chrome.exe"),
        reverse=True,
    ),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
)


def start_demo_server() -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(DEMO),
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, int(server.server_address[1])


def wait_for_bridge(bridge: BrowserBridge, timeout: float = 12.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if bridge.is_fresh():
            return
        time.sleep(0.1)
    raise AssertionError(f"Browser companion did not connect: {json.dumps(bridge.status())}")


def wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for browser state.")


def main() -> None:
    chrome = next((path for path in CHROME_CANDIDATES if path.exists()), None)
    if chrome is None:
        raise SystemExit("Chrome or Edge is required for the browser E2E test.")

    bridge_port = 8765
    bridge = BrowserBridge("127.0.0.1", bridge_port, "local-dev-token", 5.0, 20.0)
    demo_server, demo_port = start_demo_server()
    bridge.start()
    user_data = tempfile.mkdtemp(prefix="openmouse-e2e-")
    headless = os.getenv("OPENMOUSE_E2E_HEADLESS", "0") == "1"

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data,
                executable_path=str(chrome),
                headless=headless,
                ignore_default_args=["--disable-extensions"],
                args=[
                    f"--disable-extensions-except={EXTENSION}",
                    f"--load-extension={EXTENSION}",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            context.on(
                "serviceworker",
                lambda worker: print(f"service worker: {worker.url}", flush=True),
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.wait_for_timeout(2000)
            print(
                "loaded service workers: "
                + json.dumps([worker.url for worker in context.service_workers]),
                flush=True,
            )
            page.goto(f"http://127.0.0.1:{demo_port}/browser-demo.html")
            page.bring_to_front()
            wait_for_bridge(bridge)

            position = bridge.command("position", {})
            assert isinstance(position["x"], int)
            assert position["width"] == 1280

            save_box = page.locator("#save-note").bounding_box()
            assert save_box is not None
            save_x = round(save_box["x"] + save_box["width"] / 2)
            save_y = round(save_box["y"] + save_box["height"] / 2)
            result = bridge.command(
                "click",
                {
                    "x": save_x,
                    "y": save_y,
                    "button": "left",
                    "clicks": 1,
                    "intent": "click Save note",
                    "target_description": "Save note",
                    "risk_approved": False,
                },
            )
            assert result["button"] == "left"
            wait_for(lambda: page.locator("#save-count").inner_text() == "1")

            bridge.command(
                "click",
                {
                    "x": save_x,
                    "y": save_y,
                    "button": "left",
                    "clicks": 2,
                    "intent": "double click Save note for a second save",
                    "target_description": "Save note",
                    "risk_approved": False,
                },
            )
            wait_for(lambda: page.locator("#save-count").inner_text() == "3")

            selection_rect = page.evaluate(
                """
                () => {
                  const note = document.getElementById("note");
                  const range = document.createRange();
                  range.selectNodeContents(note);
                  const rect = range.getBoundingClientRect();
                  return {
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                  };
                }
                """
            )
            bridge.command(
                "drag",
                {
                    "from_x": round(selection_rect["x"] + 4),
                    "from_y": round(selection_rect["y"] + 22),
                    "to_x": round(selection_rect["x"] + 300),
                    "to_y": round(selection_rect["y"] + 22),
                    "button": "left",
                    "intent": "select part of the note sentence",
                    "target_description": "note text",
                    "risk_approved": False,
                },
            )
            wait_for(
                lambda: page.evaluate(
                    "() => (window.getSelection()?.toString().length || 0) > 0"
                )
            )

            screenshot = bridge.command("screenshot", {}, timeout=20.0)
            assert screenshot["data_url"].startswith("data:image/png;base64,")
            assert screenshot["viewport_width"] == 1280
            artifact_dir = ROOT / ".runtime"
            artifact_dir.mkdir(exist_ok=True)
            (artifact_dir / "browser-e2e.png").write_bytes(
                base64.b64decode(screenshot["data_url"].split(",", 1)[1])
            )

            delete_box = page.locator("#delete-all").bounding_box()
            assert delete_box is not None
            blocked = bridge.command(
                "click",
                {
                    "x": round(delete_box["x"] + delete_box["width"] / 2),
                    "y": round(delete_box["y"] + delete_box["height"] / 2),
                    "button": "left",
                    "clicks": 1,
                    "intent": "delete all records",
                    "target_description": "Delete all records",
                    "risk_approved": False,
                },
            )
            assert blocked["blocked"] is True
            assert blocked["evidence"]

            scroll_box = page.locator("#scroll-region").bounding_box()
            assert scroll_box is not None
            bridge.command(
                "scroll",
                {
                    "direction": "down",
                    "clicks": 4,
                    "x": round(scroll_box["x"] + scroll_box["width"] / 2),
                    "y": round(scroll_box["y"] + scroll_box["height"] / 2),
                    "intent": "scroll the test panel",
                    "target_description": "scrollable panel",
                    "risk_approved": False,
                },
            )
            wait_for(
                lambda: page.eval_on_selector(
                    "#scroll-region",
                    "element => element.scrollTop > 0",
                )
            )

            print(
                json.dumps(
                    {
                        "browser_e2e": "ok",
                        "position": position,
                        "screenshot_bytes": len(screenshot["data_url"]),
                        "blocked_evidence": blocked["evidence"],
                    },
                    ensure_ascii=True,
                    indent=2,
                )
            )
            context.close()
    finally:
        bridge.close()
        demo_server.shutdown()
        demo_server.server_close()


if __name__ == "__main__":
    main()
