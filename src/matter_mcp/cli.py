"""CLI entrypoint for the Matter MCP server."""

from __future__ import annotations

from matter_mcp.server import mcp


def main() -> None:
    """Run the Matter MCP server over stdio (default MCP transport)."""
    mcp.run()
