"""Shared test fixtures and pytest configuration."""

from __future__ import annotations

import os

import pytest
from fastmcp.client import Client

from matter_mcp.server import mcp


@pytest.fixture
async def client():
    """In-process FastMCP Client — tests the full MCP protocol layer without HTTP."""
    async with Client(mcp) as c:
        yield c


def pytest_collection_modifyitems(items: list) -> None:
    """Auto-skip @pytest.mark.integration tests when MATTER_API_TOKEN is absent."""
    if not os.environ.get("MATTER_API_TOKEN"):
        skip = pytest.mark.skip(reason=("MATTER_API_TOKEN not set. Run with: op run --env-file=.env -- uv run pytest -m integration"))
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip)
