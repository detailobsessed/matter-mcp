"""Tests for matter-mcp server and client."""

from __future__ import annotations

import contextlib
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from matter_mcp.client import _BASE_URL, _request, api_delete, get_token
from matter_mcp.server import _shape_item, mcp

# ---------------------------------------------------------------------------
# Shared raw-response fixtures and mock helper
# ---------------------------------------------------------------------------

_ITEM_RAW: dict = {
    "id": "itm_1",
    "title": "Test Article",
    "url": "https://example.com",
    "author": {"object": "author", "id": "aut_1", "name": "Author Name"},
    "site_name": "example.com",
    "status": "queue",
    "processing_status": "completed",
    "content_type": "article",
    "word_count": 500,
    "image_url": None,
    "excerpt": "A brief excerpt.",
    "tags": [{"id": "tag_1", "name": "tech"}],
    "is_favorite": False,
    "reading_progress": 0.0,
    "markdown": "# Hello",
    "updated_at": "2026-01-01T00:00:00Z",
    "library_position": 1,
    "inbox_position": None,
}
_ACCOUNT_RAW: dict = {
    "id": "act_1",
    "name": "Test User",
    "email": "test@example.com",
    "created_at": "2026-01-01T00:00:00Z",
    "rate_limit": {"read": 120, "write": 30, "save": 10, "markdown": 20, "search": 30, "burst": 5},
}
_ANNOTATION_RAW: dict = {
    "id": "ann_1",
    "item_id": "itm_1",
    "text": "Key quote",
    "note": None,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}
_TAG_RAW: dict = {"id": "tag_1", "name": "tech", "item_count": 5, "created_at": "2026-01-01T00:00:00Z"}
_LIST_ITEMS: dict = {"results": [_ITEM_RAW], "has_more": False, "next_cursor": None}
_LIST_ANNOTATIONS: dict = {"results": [_ANNOTATION_RAW], "has_more": False, "next_cursor": None}
_LIST_TAGS: dict = {"results": [_TAG_RAW], "has_more": False, "next_cursor": None}
_LIST_SESSIONS: dict = {
    "results": [{"id": "rs_1", "date": "2026-01-01T00:00:00Z", "seconds_read": 300}],
    "has_more": False,
    "next_cursor": None,
}
_SEARCH_RAW: dict = {"items": {"results": [_ITEM_RAW], "has_more": False, "next_cursor": None}}


@contextlib.contextmanager
def _mock_http(json_data, *, status: int = 200):
    """Patch httpx.AsyncClient + set MATTER_API_TOKEN for a single test call."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json.return_value = json_data
    mock_http = MagicMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.request = AsyncMock(return_value=mock_resp)
    with patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test"}), patch("matter_mcp.client.httpx.AsyncClient", return_value=mock_http):
        yield mock_http


# ---------------------------------------------------------------------------
# get_token
# ---------------------------------------------------------------------------


def test_get_token_returns_value_when_set() -> None:
    with patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test123"}):
        assert get_token() == "mat_test123"


def test_get_token_raises_tool_error_when_missing() -> None:
    env = {k: v for k, v in os.environ.items() if k != "MATTER_API_TOKEN"}
    with patch.dict(os.environ, env, clear=True), pytest.raises(ToolError, match="MATTER_API_TOKEN is not set"):
        get_token()


# ---------------------------------------------------------------------------
# _request — 429 retry and error codes
# ---------------------------------------------------------------------------


async def test_request_raises_tool_error_on_401() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"error": {"code": "unauthorized", "message": "Invalid token."}}

    with patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test"}), patch("matter_mcp.client.httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_http
        mock_client_cls.return_value.__aexit__.return_value = None

        with pytest.raises(ToolError, match="Authentication failed"):
            await _request("GET", "/me")


async def test_request_raises_tool_error_on_404() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.json.return_value = {"error": {"code": "not_found", "message": "No item found."}}

    with patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test"}), patch("matter_mcp.client.httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_http
        mock_client_cls.return_value.__aexit__.return_value = None

        with pytest.raises(ToolError, match="No item found"):
            await _request("GET", "/items/itm_bad")


async def test_request_returns_none_on_204() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 204

    with patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test"}), patch("matter_mcp.client.httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.request.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_http
        mock_client_cls.return_value.__aexit__.return_value = None

        result = await _request("DELETE", "/items/itm_test")
        assert result is None


async def test_request_retries_on_429_then_succeeds() -> None:
    rate_limited = MagicMock()
    rate_limited.status_code = 429
    rate_limited.headers = {"Retry-After": "0"}

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.json.return_value = {"object": "account", "id": "act_1"}

    with patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test"}), patch("matter_mcp.client.httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.request.side_effect = [rate_limited, ok_response]
        mock_client_cls.return_value.__aenter__.return_value = mock_http
        mock_client_cls.return_value.__aexit__.return_value = None

        with patch("matter_mcp.client.asyncio.sleep", new_callable=AsyncMock):
            result = await _request("GET", "/me")
            assert result == {"object": "account", "id": "act_1"}


# ---------------------------------------------------------------------------
# Server — tool registration
# ---------------------------------------------------------------------------


def test_server_name() -> None:
    assert mcp.name == "Matter"


async def test_expected_tools_registered() -> None:
    expected = {
        "get_account",
        "list_items",
        "get_item",
        "save_item",
        "update_item",
        "delete_item",
        "list_annotations",
        "get_annotation",
        "update_annotation",
        "delete_annotation",
        "list_tags",
        "add_tag_to_item",
        "remove_tag_from_item",
        "rename_tag",
        "delete_tag",
        "search",
        "list_reading_sessions",
    }
    tools = await mcp._list_tools()
    registered = {t.name for t in tools}
    assert expected <= registered


# ---------------------------------------------------------------------------
# Response shaper helpers
# ---------------------------------------------------------------------------


def test_shape_item_flattens_author_and_tags() -> None:
    raw = {
        "id": "itm_test",
        "title": "Test Article",
        "url": "https://example.com",
        "author": {"object": "author", "id": "aut_1", "name": "Jane Doe"},
        "site_name": "example.com",
        "status": "queue",
        "processing_status": "completed",
        "is_favorite": False,
        "content_type": "article",
        "word_count": 1000,
        "reading_progress": 0.5,
        "tags": [{"object": "tag", "id": "tag_1", "name": "tech"}],
        "updated_at": "2026-04-01T00:00:00Z",
    }
    result = _shape_item(raw)
    assert result["author"] == "Jane Doe"
    assert result["tags"] == ["tech"]
    assert "markdown" not in result


def test_shape_item_includes_markdown_when_requested() -> None:
    raw = {
        "id": "itm_test",
        "url": "https://example.com",
        "markdown": "# Hello",
        "author": None,
        "tags": [],
        "status": "queue",
        "processing_status": "completed",
        "is_favorite": False,
        "reading_progress": 0.0,
        "updated_at": "2026-04-01T00:00:00Z",
    }
    result = _shape_item(raw, include_markdown=True)
    assert result["markdown"] == "# Hello"


def test_base_url_is_correct() -> None:
    assert _BASE_URL == "https://api.getmatter.com/public/v1"


# ---------------------------------------------------------------------------
# FastMCP Client — protocol-level tests (in-process, no real HTTP)
# ---------------------------------------------------------------------------


async def test_bm25_always_visible_tools_in_list_tools(client) -> None:
    """list_tools() via Client returns the BM25 always_visible set."""
    always_visible = {"get_account", "list_items", "search", "save_item"}
    tools = await client.list_tools()
    names = {t.name for t in tools}
    assert always_visible <= names
    assert "search_tools" in names


async def test_tool_annotations_on_destructive_tool() -> None:
    """delete_item should carry destructiveHint=True annotation."""
    all_tools = await mcp._list_tools()
    delete_item = next(t for t in all_tools if t.name == "delete_item")
    assert delete_item.annotations is not None
    assert delete_item.annotations.destructiveHint is True


# ---------------------------------------------------------------------------
# Client error-path tests
# ---------------------------------------------------------------------------


async def test_request_raises_tool_error_on_403() -> None:
    with pytest.raises(ToolError, match="Access denied"), _mock_http({"error": {"message": "Pro required"}}, status=403):
        await _request("GET", "/me")


async def test_request_raises_tool_error_on_422_with_field() -> None:
    with pytest.raises(ToolError, match='on field "url"'), _mock_http({"error": {"message": "Bad value", "field": "url"}}, status=422):
        await _request("POST", "/items")


async def test_request_raises_tool_error_on_5xx() -> None:
    with pytest.raises(ToolError, match="API error 500"), _mock_http({"error": {"message": "Server exploded"}}, status=500):
        await _request("GET", "/me")


async def test_request_retry_after_date_format_falls_back_to_default() -> None:
    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.headers = {"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}
    mock_ok = MagicMock()
    mock_ok.status_code = 200
    mock_ok.json.return_value = {"id": "act_1"}
    mock_http = MagicMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.request = AsyncMock(side_effect=[mock_429, mock_ok])
    with (
        patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test"}),
        patch("matter_mcp.client.httpx.AsyncClient", return_value=mock_http),
        patch("matter_mcp.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        result = await _request("GET", "/me")
    assert result == {"id": "act_1"}
    mock_sleep.assert_called_once_with(10)


async def test_request_exhausts_all_retries_on_429() -> None:
    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.headers = {"Retry-After": "1"}
    mock_http = MagicMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.request = AsyncMock(return_value=mock_429)
    with (
        patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test"}),
        patch("matter_mcp.client.httpx.AsyncClient", return_value=mock_http),
        patch("matter_mcp.client.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(ToolError, match="Rate limit exceeded"),
    ):
        await _request("GET", "/me")


async def test_api_delete_sends_delete_request() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_http = MagicMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.request = AsyncMock(return_value=mock_resp)
    with patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test"}), patch("matter_mcp.client.httpx.AsyncClient", return_value=mock_http):
        await api_delete("/items/itm_1")
    mock_http.request.assert_called_once()
    assert mock_http.request.call_args[0][0] == "DELETE"


# ---------------------------------------------------------------------------
# Tool-level unit tests — mock httpx, call via FastMCP Client
# ---------------------------------------------------------------------------


async def test_get_account_tool(client) -> None:
    with _mock_http(_ACCOUNT_RAW):
        result = await client.call_tool("get_account", {})
    assert not result.is_error
    assert result.data["id"] == "act_1"
    assert result.data["rate_limit"]["read"] == 120
    assert "next_steps" in result.data


async def test_list_items_tool(client) -> None:
    with _mock_http(_LIST_ITEMS):
        result = await client.call_tool("list_items", {"limit": 1})
    assert not result.is_error
    data = result.data
    assert data["count"] == 1
    assert data["results"][0]["author"] == "Author Name"
    assert data["results"][0]["tags"] == ["tech"]


async def test_get_item_tool_without_markdown(client) -> None:
    with _mock_http(_ITEM_RAW):
        result = await client.call_tool("get_item", {"item_id": "itm_1"})
    assert not result.is_error
    assert "markdown" not in result.data
    assert "next_steps" in result.data


async def test_get_item_tool_with_markdown(client) -> None:
    with _mock_http(_ITEM_RAW):
        result = await client.call_tool("get_item", {"item_id": "itm_1", "include_markdown": True})
    assert not result.is_error
    assert result.data["markdown"] == "# Hello"


async def test_save_item_tool_processing(client) -> None:
    processing = {**_ITEM_RAW, "processing_status": "processing"}
    with _mock_http(processing, status=201):
        result = await client.call_tool("save_item", {"url": "https://example.com"})
    assert not result.is_error
    assert "in 20-60 seconds" in result.data["next_steps"][0]


async def test_save_item_tool_completed(client) -> None:
    with _mock_http(_ITEM_RAW, status=201):
        result = await client.call_tool("save_item", {"url": "https://example.com"})
    assert not result.is_error
    steps = result.data["next_steps"]
    assert any("include_markdown=True" in s for s in steps)


async def test_update_item_tool(client) -> None:
    updated = {**_ITEM_RAW, "status": "archive"}
    with _mock_http(updated):
        result = await client.call_tool("update_item", {"item_id": "itm_1", "status": "archive"})
    assert not result.is_error
    assert result.data["status"] == "archive"


async def test_update_item_tool_no_fields_raises(client) -> None:
    with pytest.raises(ToolError, match="at least one field"), _mock_http(_ITEM_RAW):
        await client.call_tool("update_item", {"item_id": "itm_1"})


async def test_delete_item_tool(client) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_http = MagicMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.request = AsyncMock(return_value=mock_resp)
    with patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test"}), patch("matter_mcp.client.httpx.AsyncClient", return_value=mock_http):
        result = await client.call_tool("delete_item", {"item_id": "itm_1"})
    assert not result.is_error
    assert result.data["deleted"] is True


async def test_list_annotations_tool(client) -> None:
    with _mock_http(_LIST_ANNOTATIONS):
        result = await client.call_tool("list_annotations", {"item_id": "itm_1"})
    assert not result.is_error
    assert result.data["results"][0]["text"] == "Key quote"


async def test_get_annotation_tool(client) -> None:
    with _mock_http(_ANNOTATION_RAW):
        result = await client.call_tool("get_annotation", {"annotation_id": "ann_1"})
    assert not result.is_error
    assert result.data["id"] == "ann_1"
    assert "next_steps" in result.data


async def test_update_annotation_tool(client) -> None:
    updated = {**_ANNOTATION_RAW, "note": "My note"}
    with _mock_http(updated):
        result = await client.call_tool("update_annotation", {"annotation_id": "ann_1", "note": "My note"})
    assert not result.is_error
    assert result.data["note"] == "My note"


async def test_delete_annotation_tool(client) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_http = MagicMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.request = AsyncMock(return_value=mock_resp)
    with patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test"}), patch("matter_mcp.client.httpx.AsyncClient", return_value=mock_http):
        result = await client.call_tool("delete_annotation", {"annotation_id": "ann_1"})
    assert not result.is_error
    assert result.data["deleted"] is True


async def test_list_tags_tool(client) -> None:
    with _mock_http(_LIST_TAGS):
        result = await client.call_tool("list_tags", {})
    assert not result.is_error
    assert result.data["results"][0]["name"] == "tech"
    assert result.data["results"][0]["item_count"] == 5


async def test_add_tag_to_item_tool(client) -> None:
    with _mock_http(_TAG_RAW, status=201):
        result = await client.call_tool("add_tag_to_item", {"item_id": "itm_1", "tag_name": "tech"})
    assert not result.is_error
    assert result.data["name"] == "tech"
    assert result.data["item_id"] == "itm_1"


async def test_remove_tag_from_item_tool(client) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_http = MagicMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.request = AsyncMock(return_value=mock_resp)
    with patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test"}), patch("matter_mcp.client.httpx.AsyncClient", return_value=mock_http):
        result = await client.call_tool("remove_tag_from_item", {"item_id": "itm_1", "tag_id": "tag_1"})
    assert not result.is_error
    assert result.data["removed"] is True


async def test_rename_tag_tool(client) -> None:
    renamed = {**_TAG_RAW, "name": "python"}
    with _mock_http(renamed):
        result = await client.call_tool("rename_tag", {"tag_id": "tag_1", "new_name": "python"})
    assert not result.is_error
    assert result.data["name"] == "python"


async def test_delete_tag_tool(client) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_http = MagicMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.request = AsyncMock(return_value=mock_resp)
    with patch.dict(os.environ, {"MATTER_API_TOKEN": "mat_test"}), patch("matter_mcp.client.httpx.AsyncClient", return_value=mock_http):
        result = await client.call_tool("delete_tag", {"tag_id": "tag_1"})
    assert not result.is_error
    assert result.data["deleted"] is True


async def test_search_tool(client) -> None:
    with _mock_http(_SEARCH_RAW):
        result = await client.call_tool("search", {"query": "ai"})
    assert not result.is_error
    assert result.data["query"] == "ai"
    assert result.data["items"]["results"][0]["author"] == "Author Name"


async def test_list_reading_sessions_tool(client) -> None:
    with _mock_http(_LIST_SESSIONS):
        result = await client.call_tool("list_reading_sessions", {})
    assert not result.is_error
    assert result.data["results"][0]["minutes_read"] == pytest.approx(5.0)
    assert result.data["total_minutes_read"] == pytest.approx(5.0)


async def test_tool_annotations_on_readonly_tool() -> None:
    """get_account should carry readOnlyHint=True annotation."""
    all_tools = await mcp._list_tools()
    get_account = next(t for t in all_tools if t.name == "get_account")
    assert get_account.annotations is not None
    assert get_account.annotations.readOnlyHint is True
