from __future__ import annotations

import pytest

from mouse_mcp.cloud_browser import CloudBrowserDriver
from mouse_mcp.errors import MouseMcpError


def test_cloud_browser_blocks_loopback_and_private_addresses() -> None:
    driver = CloudBrowserDriver()

    with pytest.raises(MouseMcpError, match="private or special"):
        driver._validate_public_url("127.0.0.1", 8080)
    with pytest.raises(MouseMcpError, match="private or special"):
        driver._validate_public_url("10.0.0.8", 80)


def test_cloud_browser_private_access_requires_explicit_opt_in() -> None:
    driver = CloudBrowserDriver(allow_private_urls=True)

    driver._validate_public_url("127.0.0.1", 8080)
