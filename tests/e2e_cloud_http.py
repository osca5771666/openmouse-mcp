from __future__ import annotations

import asyncio
import functools
import http.server
import json
import os
import socket
import sys
import threading
from pathlib import Path

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_demo_server() -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(ROOT / "demo"),
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, int(server.server_address[1])


async def wait_for_port(port: int, timeout: float = 15.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            _reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.15)
    raise TimeoutError(f"MCP HTTP server did not listen on port {port}.")


async def main() -> None:
    demo_server, demo_port = start_demo_server()
    mcp_port = free_port()
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "MOUSE_MCP_ENV": "cloud",
        "MOUSE_MCP_CLOUD_BROWSER": "on",
        "MOUSE_MCP_CLOUD_HEADLESS": "1",
        "MOUSE_MCP_HTTP_TOKEN": "test-http-token",
        "MOUSE_MCP_CLOUD_ALLOW_PRIVATE_URLS": "1",
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "mouse_mcp",
        "--transport",
        "streamable-http",
        "--host",
        "127.0.0.1",
        "--port",
        str(mcp_port),
        "--http-path",
        "/mcp",
        "--cloud-browser",
        cwd=ROOT,
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await wait_for_port(mcp_port)
        endpoint = f"http://127.0.0.1:{mcp_port}/mcp"
        async with httpx2.AsyncClient() as probe:
            health = await probe.get(f"http://127.0.0.1:{mcp_port}/healthz")
            assert health.status_code == 200
            unauthorized = await probe.post(endpoint, json={})
            assert unauthorized.status_code == 401
        async with httpx2.AsyncClient(
            headers={"Authorization": "Bearer test-http-token"}
        ) as authenticated:
            async with streamable_http_client(
                endpoint, http_client=authenticated
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    initialized = await session.initialize()
                    assert initialized.server_info.name == "openmouse-mcp"
                    status = await session.call_tool("mouse_status", {})
                    status_payload = json.loads(status.content[0].text)
                    assert status_payload["route"]["environment"] == "cloud"

                    opened = await session.call_tool(
                        "browser_open",
                        {"url": f"http://127.0.0.1:{demo_port}/browser-demo.html"},
                    )
                    opened_payload = json.loads(opened.content[0].text)
                    assert opened_payload["environment"] == "cloud"

                    observation = await session.call_tool("computer_observe", {})
                    assert len(observation.content) == 2
                    observation_payload = json.loads(observation.content[0].text)
                    assert observation_payload["environment"] == "cloud"
                    assert observation_payload["viewport_width"] == 1440
                    assert observation.content[1].type == "image"

                    print(
                        json.dumps(
                            {
                                "cloud_http_e2e": "ok",
                                "endpoint": endpoint,
                                "auth": "bearer",
                                "route": status_payload["route"],
                                "opened_url": opened_payload["url"],
                                "screenshot_base64_chars": len(observation.content[1].data),
                            },
                            ensure_ascii=True,
                            indent=2,
                        )
                    )
    finally:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
        demo_server.shutdown()
        demo_server.server_close()


if __name__ == "__main__":
    asyncio.run(main())
