from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import replace

from .config import Settings
from .runtime import MouseRuntime
from .server import build_server


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenMouse MCP server")
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Start the bridge, print status, wait briefly, and exit.",
    )
    parser.add_argument(
        "--diagnose-wait",
        type=float,
        default=2.0,
        help="Seconds to wait for a browser heartbeat in diagnose mode.",
    )
    parser.add_argument(
        "--print-token",
        action="store_true",
        help="Print the configured browser companion token and exit.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport. Use streamable-http for a cloud-hosted endpoint.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Streamable HTTP bind host.")
    parser.add_argument("--port", type=int, default=8766, help="Streamable HTTP port.")
    parser.add_argument(
        "--http-path",
        default="/mcp",
        help="Streamable HTTP endpoint path.",
    )
    parser.add_argument(
        "--cloud-browser",
        action="store_true",
        help="Enable the embedded Playwright Chromium fallback.",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    settings = Settings.from_env()
    if args.cloud_browser:
        settings = replace(settings, cloud_browser_mode="on")
    if args.print_token:
        print(settings.browser_token)
        return

    runtime = MouseRuntime(settings)
    try:
        runtime.start()
        if args.diagnose:
            if args.diagnose_wait > 0:
                time.sleep(args.diagnose_wait)
            print(json.dumps(runtime.status(), ensure_ascii=False, indent=2))
            return
        server = build_server(runtime, settings)
        if args.transport == "streamable-http":
            from .http_server import run_streamable_http

            if args.host not in {"127.0.0.1", "localhost", "::1"}:
                logging.warning(
                    "Streamable HTTP is bound to %s without built-in authentication. "
                    "Place it behind an authenticated TLS reverse proxy.",
                    args.host,
                )
            run_streamable_http(
                server,
                host=args.host,
                port=args.port,
                path=args.http_path,
                auth_token=settings.http_auth_token,
                allowed_hosts=settings.http_allowed_hosts,
            )
        else:
            server.run(transport="stdio")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
