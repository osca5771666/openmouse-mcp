from __future__ import annotations

import hmac
import json
import logging
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable

from websockets.exceptions import ConnectionClosed
from websockets.sync.connection import Connection
from websockets.sync.server import Server, serve

from .errors import MouseMcpError, RouteUnavailable


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrowserSession:
    client_id: str = ""
    connected_at: float = 0.0
    last_seen: float = 0.0
    focused: bool = False
    window_id: int | None = None
    tab_id: int | None = None
    url: str = ""
    title: str = ""
    viewport_width: int = 0
    viewport_height: int = 0
    device_pixel_ratio: float = 1.0
    scroll_x: float = 0.0
    scroll_y: float = 0.0


@dataclass
class _Pending:
    future: Future[dict[str, Any]] = field(default_factory=Future)


class BrowserBridge:
    """Loopback WebSocket bridge used by the bundled browser extension."""

    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        heartbeat_timeout: float,
        command_timeout: float,
    ) -> None:
        self.host = host
        self.port = port
        self._token = token
        self._heartbeat_timeout = heartbeat_timeout
        self._command_timeout = command_timeout
        self._server: Server | None = None
        self._thread: threading.Thread | None = None
        self._connection: Connection | None = None
        self._session = BrowserSession()
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.RLock()
        self._emergency_callback: Callable[[str], None] | None = None
        self._startup_error: str | None = None

    def set_emergency_callback(self, callback: Callable[[str], None]) -> None:
        self._emergency_callback = callback

    def start(self) -> None:
        if self._server is not None:
            return
        try:
            self._server = serve(
                self._handle_connection,
                self.host,
                self.port,
                max_size=64 * 1024 * 1024,
                ping_interval=20,
                ping_timeout=20,
            )
        except OSError as exc:
            self._startup_error = str(exc)
            raise MouseMcpError(
                f"Cannot start browser bridge on {self.host}:{self.port}: {exc}"
            ) from exc
        self._startup_error = None
        self._thread = threading.Thread(
            target=self._serve,
            name="openmouse-browser-bridge",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info("Browser bridge listening on ws://%s:%s", self.host, self.port)

    def _serve(self) -> None:
        assert self._server is not None
        try:
            self._server.serve_forever()
        except Exception:
            LOGGER.exception("Browser bridge stopped unexpectedly")

    def close(self) -> None:
        with self._lock:
            connection = self._connection
            self._connection = None
            self._fail_all_pending("Browser bridge closed.")
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def snapshot(self) -> BrowserSession:
        with self._lock:
            return self._session

    def is_fresh(self) -> bool:
        session = self.snapshot()
        return bool(
            self.is_connected()
            and session.last_seen
            and time.monotonic() - session.last_seen <= self._heartbeat_timeout
        )

    def is_connected(self) -> bool:
        with self._lock:
            return self._connection is not None

    def status(self) -> dict[str, Any]:
        with self._lock:
            session = self._session
            connected = self._connection is not None
        age = time.monotonic() - session.last_seen if session.last_seen else None
        return {
            "connected": connected,
            "fresh": self.is_fresh(),
            "heartbeat_age_seconds": round(age, 2) if age is not None else None,
            "focused": session.focused,
            "tab_id": session.tab_id,
            "url": session.url,
            "title": session.title,
            "viewport": {
                "width": session.viewport_width,
                "height": session.viewport_height,
                "device_pixel_ratio": session.device_pixel_ratio,
            },
            "startup_error": self._startup_error,
        }

    def command(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        pending = _Pending()
        with self._lock:
            connection = self._connection
            if connection is None:
                raise RouteUnavailable(
                    "The browser companion is not connected. Load the included extension."
                )
            self._pending[request_id] = pending

        payload = {
            "type": "command",
            "id": request_id,
            "action": action,
            "params": params or {},
        }
        try:
            connection.send(json.dumps(payload, ensure_ascii=True))
            return pending.future.result(timeout=timeout or self._command_timeout)
        except TimeoutError as exc:
            raise MouseMcpError(f"Browser action '{action}' timed out.") from exc
        except Exception as exc:
            if isinstance(exc, MouseMcpError):
                raise
            raise MouseMcpError(f"Browser action '{action}' failed: {exc}") from exc
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def emergency_stop(self, reason: str = "emergency_stop") -> None:
        with self._lock:
            connection = self._connection
        if connection is None:
            return
        try:
            connection.send(
                json.dumps(
                    {"type": "stop", "reason": reason, "id": uuid.uuid4().hex},
                    ensure_ascii=True,
                )
            )
        except Exception:
            LOGGER.debug("Could not send browser emergency stop", exc_info=True)

    def _handle_connection(self, connection: Connection) -> None:
        hello: dict[str, Any] | None = None
        try:
            raw = connection.recv(timeout=5)
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            hello = json.loads(raw)
            if hello.get("type") != "hello" or not hmac.compare_digest(
                str(hello.get("token", "")), self._token
            ):
                connection.send(
                    json.dumps(
                        {
                            "type": "hello_error",
                            "error": "Invalid browser companion token.",
                        }
                    )
                )
                connection.close(1008, "invalid token")
                return

            now = time.monotonic()
            initial = self._session_from_message(
                hello,
                client_id=str(hello.get("client_id", "browser")),
                connected_at=now,
                last_seen=now,
            )
            with self._lock:
                previous = self._connection
                self._connection = connection
                self._session = initial
            if previous is not None and previous is not connection:
                try:
                    previous.close()
                except Exception:
                    pass
            connection.send(
                json.dumps(
                    {
                        "type": "hello_ack",
                        "server": "openmouse-mcp",
                        "version": "1.0.1",
                        "heartbeat_seconds": 1.0,
                    }
                )
            )
            LOGGER.info("Browser companion connected: %s", initial.client_id)

            for raw_message in connection:
                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode("utf-8")
                self._handle_message(connection, json.loads(raw_message))
        except (ConnectionClosed, TimeoutError, json.JSONDecodeError):
            pass
        except Exception:
            LOGGER.exception("Browser bridge connection failed")
        finally:
            if hello is not None:
                LOGGER.info("Browser companion disconnected")
            with self._lock:
                if self._connection is connection:
                    self._connection = None
                    self._session = BrowserSession()
                    self._fail_all_pending("Browser companion disconnected.")

    def _handle_message(self, connection: Connection, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "heartbeat":
            now = time.monotonic()
            with self._lock:
                if self._connection is not connection:
                    return
                self._session = self._session_from_message(
                    message,
                    client_id=self._session.client_id,
                    connected_at=self._session.connected_at,
                    last_seen=now,
                )
            return

        if message_type == "response":
            request_id = str(message.get("id", ""))
            with self._lock:
                pending = self._pending.get(request_id)
            if pending is None or pending.future.done():
                return
            if message.get("ok"):
                result = message.get("result")
                pending.future.set_result(result if isinstance(result, dict) else {"value": result})
            else:
                error = message.get("error") or "Unknown browser companion error."
                pending.future.set_exception(MouseMcpError(str(error)))
            return

        if message_type == "emergency_stop":
            reason = str(message.get("reason", "browser_escape"))
            with self._lock:
                self._fail_all_pending(f"Browser action cancelled: {reason}.")
            if self._emergency_callback is not None:
                self._emergency_callback(reason)

    def _session_from_message(
        self,
        message: dict[str, Any],
        client_id: str,
        connected_at: float,
        last_seen: float,
    ) -> BrowserSession:
        viewport = message.get("viewport") or {}
        return BrowserSession(
            client_id=client_id,
            connected_at=connected_at,
            last_seen=last_seen,
            focused=bool(message.get("focused", False)),
            window_id=_optional_int(message.get("window_id")),
            tab_id=_optional_int(message.get("tab_id")),
            url=str(message.get("url", "")),
            title=str(message.get("title", "")),
            viewport_width=int(viewport.get("width", 0) or 0),
            viewport_height=int(viewport.get("height", 0) or 0),
            device_pixel_ratio=float(viewport.get("device_pixel_ratio", 1.0) or 1.0),
            scroll_x=float(viewport.get("scroll_x", 0.0) or 0.0),
            scroll_y=float(viewport.get("scroll_y", 0.0) or 0.0),
        )

    def _fail_all_pending(self, message: str) -> None:
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.set_exception(RouteUnavailable(message))
        self._pending.clear()


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
