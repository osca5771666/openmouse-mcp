from __future__ import annotations

import hmac
import json
import logging
from typing import Any

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings


LOGGER = logging.getLogger(__name__)


class BearerAuthMiddleware:
    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == "/healthz":
            body = json.dumps({"ok": True}).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        authorization = headers.get("authorization", "")
        expected = f"Bearer {self.token}"
        if not hmac.compare_digest(authorization, expected):
            body = json.dumps({"error": "unauthorized"}).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"www-authenticate", b"Bearer"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def run_streamable_http(
    server: MCPServer,
    *,
    host: str,
    port: int,
    path: str,
    auth_token: str | None,
    allowed_hosts: tuple[str, ...],
) -> None:
    transport_security = None
    if allowed_hosts:
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(dict.fromkeys((*allowed_hosts, "127.0.0.1", "localhost"))),
        )
    app = server.streamable_http_app(
        streamable_http_path=path,
        stateless_http=True,
        host=host,
        transport_security=transport_security,
    )
    if auth_token:
        app = BearerAuthMiddleware(app, auth_token)
    else:
        LOGGER.warning(
            "Streamable HTTP is running without authentication. "
            "Set MOUSE_MCP_HTTP_TOKEN and use an authenticated TLS reverse proxy."
        )
    uvicorn.run(app, host=host, port=port, log_level="warning")
