from __future__ import annotations

import os
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PLUGIN_ROOT / "src"
TOKEN_FILE = PLUGIN_ROOT / ".runtime" / "browser-token.txt"

sys.path.insert(0, str(SOURCE_ROOT))
os.environ.setdefault("MOUSE_MCP_TOKEN_FILE", str(TOKEN_FILE))

from mouse_mcp.__main__ import main  # noqa: E402


if __name__ == "__main__":
    main()
