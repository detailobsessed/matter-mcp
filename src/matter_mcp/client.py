"""HTTP client for the Matter API with retry and structured error handling."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from fastmcp.exceptions import ToolError

_BASE_URL = "https://api.getmatter.com/public/v1"
_MAX_RETRIES = 3
_HTTP_OK = 200
_HTTP_CREATED = 201
_HTTP_NO_CONTENT = 204
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def get_token() -> str:
    """Read the API token from the environment, raising ToolError if absent."""
    token = os.environ.get("MATTER_API_TOKEN")
    if not token:
        msg = (
            "MATTER_API_TOKEN is not set. "
            "Generate your token at https://web.getmatter.com/settings "
            "under 'API Access', then: export MATTER_API_TOKEN=mat_your_token_here"
        )
        raise ToolError(msg)
    return token


async def api_get(path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make an authenticated GET request."""
    result = await _request("GET", path, params=params)
    if result is None:
        msg = f"Unexpected empty response from GET {path}"
        raise ToolError(msg)
    return result


async def api_post(path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make an authenticated POST request."""
    result = await _request("POST", path, body=body)
    if result is None:
        msg = f"Unexpected empty response from POST {path}"
        raise ToolError(msg)
    return result


async def api_patch(path: str, *, body: dict[str, Any]) -> dict[str, Any]:
    """Make an authenticated PATCH request."""
    result = await _request("PATCH", path, body=body)
    if result is None:
        msg = f"Unexpected empty response from PATCH {path}"
        raise ToolError(msg)
    return result


async def api_delete(path: str) -> None:
    """Make an authenticated DELETE request (expects 204)."""
    await _request("DELETE", path)


def _raise_for_status(status: int, data: dict[str, Any]) -> None:
    """Translate HTTP error status codes into ToolError with actionable messages."""
    if status == _HTTP_UNAUTHORIZED:
        msg = (
            "Authentication failed: invalid or expired API token. "
            "Generate a new token at https://web.getmatter.com/settings "
            "and update MATTER_API_TOKEN."
        )
        raise ToolError(msg)
    if status == _HTTP_FORBIDDEN:
        details = data.get("error", {}).get("message", "Active Pro subscription required.")
        msg = f"Access denied: {details}. Upgrade at https://web.getmatter.com/settings."
        raise ToolError(msg)
    if status == _HTTP_NOT_FOUND:
        details = data.get("error", {}).get("message", "Resource not found.")
        msg = f"{details} Use list_items(), list_tags(), or list_annotations(item_id=...) to discover valid IDs."
        raise ToolError(msg)
    if status == _HTTP_UNPROCESSABLE:
        error = data.get("error", {})
        details = error.get("message", "Invalid request.")
        field = error.get("field")
        field_note = f' on field "{field}"' if field else ""
        msg = f"Validation error{field_note}: {details}"
        raise ToolError(msg)
    details = data.get("error", {}).get("message", "Unknown error.")
    msg = f"API error {status}: {details}"
    raise ToolError(msg)


async def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    last: httpx.Response | None = None
    async with httpx.AsyncClient(base_url=_BASE_URL, headers=headers, timeout=30.0) as http:
        for attempt in range(_MAX_RETRIES):
            last = await http.request(method, path, params=params, json=body)
            if last.status_code != _HTTP_TOO_MANY_REQUESTS:
                break
            try:
                wait = int(last.headers.get("Retry-After", 10))
            except ValueError:
                wait = 10
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(wait)
            else:
                msg = (
                    f"Rate limit exceeded. Retry after {wait} seconds. "
                    "Use updated_since for incremental sync or limit=100 to reduce requests."
                )
                raise ToolError(msg)

    if last is None:
        msg = "Request failed: no response received."
        raise ToolError(msg)

    if last.status_code == _HTTP_NO_CONTENT:
        return None

    data: dict[str, Any] = last.json()

    if last.status_code in {_HTTP_OK, _HTTP_CREATED}:
        return data
    _raise_for_status(last.status_code, data)
    return None  # unreachable, satisfies type checker
