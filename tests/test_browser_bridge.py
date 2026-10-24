from __future__ import annotations

import json
import socket
import threading
import time

import pytest
from websockets.sync.client import connect

from mouse_mcp.browser_bridge import BrowserBridge


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_bridge_handshake_heartbeat_and_command_round_trip() -> None:
    port = _free_port()
    bridge = BrowserBridge("127.0.0.1", port, "test-token", 4.0, 3.0)
    bridge.start()
    try:
        with connect(f"ws://127.0.0.1:{port}") as websocket:
            websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "token": "test-token",
                        "client_id": "test-browser",
                        "focused": True,
                        "viewport": {"width": 1200, "height": 800},
                    }
                )
            )
            ack = json.loads(websocket.recv(timeout=2))
            assert ack["type"] == "hello_ack"
            websocket.send(
                json.dumps(
                    {
                        "type": "heartbeat",
                        "focused": True,
                        "tab_id": 42,
                        "url": "https://example.test/",
                        "viewport": {
                            "width": 1200,
                            "height": 800,
                            "device_pixel_ratio": 1.5,
                        },
                    }
                )
            )
            time.sleep(0.05)
            assert bridge.snapshot().tab_id == 42
            assert bridge.is_fresh()

            result_holder: list[dict[str, object]] = []

            def issue_command() -> None:
                result_holder.append(bridge.command("position", {}))

            thread = threading.Thread(target=issue_command)
            thread.start()
            command = json.loads(websocket.recv(timeout=2))
            assert command["action"] == "position"
            websocket.send(
                json.dumps(
                    {
                        "type": "response",
                        "id": command["id"],
                        "ok": True,
                        "result": {"x": 33, "y": 44},
                    }
                )
            )
            thread.join(2)
            assert result_holder == [{"x": 33, "y": 44}]
    finally:
        bridge.close()


def test_bridge_rejects_invalid_token() -> None:
    port = _free_port()
    bridge = BrowserBridge("127.0.0.1", port, "correct-token", 4.0, 3.0)
    bridge.start()
    try:
        with connect(f"ws://127.0.0.1:{port}") as websocket:
            websocket.send(
                json.dumps(
                    {
                        "type": "hello",
                        "token": "wrong-token",
                        "client_id": "bad-client",
                    }
                )
            )
            response = json.loads(websocket.recv(timeout=2))
            assert response["type"] == "hello_error"
            with pytest.raises(Exception):
                websocket.recv(timeout=1)
    finally:
        bridge.close()
