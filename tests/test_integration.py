"""Integration tests — require a live MATTER_API_TOKEN.

Run with:
    op run --env-file=.env -- uv run pytest -m integration -v

The conftest.py pytest_collection_modifyitems hook auto-skips all tests in this
file when MATTER_API_TOKEN is not present in the environment.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_get_account_returns_profile(client) -> None:
    """Verify authentication and account shape."""
    result = await client.call_tool("get_account", {})
    assert not result.is_error
    data = result.data
    assert "id" in data
    assert "email" in data
    assert "rate_limit" in data
    assert "read" in data["rate_limit"]


async def test_list_items_returns_paginated_response(client) -> None:
    result = await client.call_tool("list_items", {"limit": 3})
    assert not result.is_error
    data = result.data
    assert "results" in data
    assert isinstance(data["results"], list)
    assert "has_more" in data
    assert "next_steps" in data


async def test_list_items_filters_by_status(client) -> None:
    result = await client.call_tool("list_items", {"status": "queue", "limit": 5})
    assert not result.is_error
    data = result.data
    assert "results" in data
    for item in data["results"]:
        assert item["status"] == "queue"


async def test_search_returns_grouped_results(client) -> None:
    result = await client.call_tool("search", {"query": "the", "limit": 5})
    assert not result.is_error
    data = result.data
    assert "items" in data
    assert isinstance(data["items"]["results"], list)


async def test_list_tags_returns_tag_list(client) -> None:
    result = await client.call_tool("list_tags", {})
    assert not result.is_error
    data = result.data
    assert "results" in data
    assert isinstance(data["results"], list)


async def test_list_reading_sessions(client) -> None:
    result = await client.call_tool("list_reading_sessions", {"limit": 5})
    assert not result.is_error
    data = result.data
    assert "results" in data
    assert isinstance(data["results"], list)


async def test_search_tools_discovery_works(client) -> None:
    """BM25 search_tools synthetic tool surfaces hidden tools by query."""
    result = await client.call_tool("search_tools", {"query": "annotation"})
    assert not result.is_error
    data = result.data
    assert data is not None
