"""Backward-compatible MCP module entrypoint."""
from __future__ import annotations

from src.mcp.server import mcp


if __name__ == "__main__":
    import sys

    if "--sse" in sys.argv:
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")

