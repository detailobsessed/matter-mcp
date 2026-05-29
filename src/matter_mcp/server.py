"""Matter MCP server — full read/write access to your Matter reading library."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from matter_mcp.client import api_delete, api_get, api_patch, api_post

mcp = FastMCP(
    name="Matter",
    instructions=(
        "This server gives you full access to your Matter reading library. "
        "All endpoints require MATTER_API_TOKEN to be set in the environment. "
        "Call get_account() first to verify authentication and check your rate limits. "
        "Use list_items() to browse your library, save_item() to add new content, "
        "and search() to find specific articles. "
        "Rate limits: 120 read/min, 30 write/min, 10 save/min, 30 search/min."
    ),
)


# ---------------------------------------------------------------------------
# Response shapers
# ---------------------------------------------------------------------------


def _shape_item(raw: dict[str, Any], *, include_markdown: bool = False) -> dict[str, Any]:
    author_obj = raw.get("author") or {}
    tags = raw.get("tags") or []
    result: dict[str, Any] = {
        "id": raw["id"],
        "title": raw.get("title"),
        "url": raw["url"],
        "author": author_obj.get("name"),
        "site_name": raw.get("site_name"),
        "status": raw.get("status"),
        "processing_status": raw.get("processing_status"),
        "content_type": raw.get("content_type"),
        "word_count": raw.get("word_count"),
        "reading_progress": raw.get("reading_progress", 0.0),
        "is_favorite": raw.get("is_favorite", False),
        "excerpt": raw.get("excerpt"),
        "tags": [t.get("name") for t in tags if t.get("name")],
        "library_position": raw.get("library_position"),
        "updated_at": raw.get("updated_at"),
    }
    if include_markdown:
        result["markdown"] = raw.get("markdown")
    return result


def _shape_annotation(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "item_id": raw["item_id"],
        "text": raw["text"],
        "note": raw.get("note"),
        "created_at": raw["created_at"],
        "updated_at": raw["updated_at"],
    }


def _shape_tag(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "name": raw["name"],
        "item_count": raw.get("item_count"),
        "created_at": raw.get("created_at"),
    }


def _paginated(
    results: list[dict[str, Any]],
    raw: dict[str, Any],
    *,
    next_steps: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "count": len(results),
        "has_more": raw.get("has_more", False),
        "next_cursor": raw.get("next_cursor"),
        "results": results,
    }
    if next_steps:
        out["next_steps"] = next_steps
    elif raw.get("has_more") and raw.get("next_cursor"):
        cursor = raw["next_cursor"]
        out["next_steps"] = [f"Pass cursor='{cursor}' to get the next page."]
    return out


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


@mcp.tool(tags={"account"}, annotations={"readOnlyHint": True})
async def get_account(ctx: Context) -> dict[str, Any]:
    """Get the authenticated account profile and API rate limit quotas.

    Returns your name, email, account ID, and per-minute rate limits:
    - read (GET requests), write (POST/PATCH/DELETE), save (POST /items),
      search, markdown (GET with ?include=markdown), burst (per-second ceiling).

    Call this first to verify authentication and understand your quota.
    After this, use list_items() to browse your library or search() to find content.
    """
    await ctx.info("Fetching account info")
    raw = await api_get("/me")
    rate = raw.get("rate_limit", {})
    return {
        "id": raw["id"],
        "name": raw["name"],
        "email": raw["email"],
        "rate_limit": rate,
        "created_at": raw.get("created_at"),
        "next_steps": [
            "Call list_items() to browse your reading library.",
            "Call search(query='...', search_type='items') to find specific content.",
        ],
    }


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


@mcp.tool(tags={"items"}, annotations={"readOnlyHint": True})
async def list_items(  # noqa: PLR0913,PLR0917
    ctx: Context,
    status: Annotated[
        Literal["inbox", "queue", "archive"] | None,
        Field(description="Filter by status. Omit to return all statuses."),
    ] = None,
    content_types: Annotated[
        list[Literal["article", "video", "podcast", "pdf", "tweet", "newsletter"]] | None,
        Field(description="Filter by content type(s). Pass multiple for OR matching."),
    ] = None,
    tag_ids: Annotated[
        list[str] | None,
        Field(description="Filter by tag ID(s) (e.g. ['tag_n5j2x']). OR matching. Use list_tags() to discover IDs."),
    ] = None,
    is_favorite: Annotated[
        bool | None,
        Field(description="Filter to favorited items only when True."),
    ] = None,
    updated_since: Annotated[
        str | None,
        Field(description="ISO 8601 timestamp. Return only items updated after this time. Ideal for incremental sync."),
    ] = None,
    order: Annotated[
        Literal["updated", "library_position", "inbox_position"],
        Field(description="Sort order. 'updated' = newest first. 'library_position' = queue order. 'inbox_position' = inbox order."),
    ] = "updated",
    limit: Annotated[int, Field(description="Items per page (1-100).", ge=1, le=100)] = 25,
    cursor: Annotated[
        str | None,
        Field(description="Pagination cursor from a previous response's next_cursor field."),
    ] = None,
) -> dict[str, Any]:
    """List items in your Matter library with optional filtering and pagination.

    Items include articles, podcasts, videos, PDFs, tweets, and newsletters.
    Statuses: inbox (unread feed), queue (reading list), archive (finished/saved).

    For incremental sync, pass updated_since with a previous response timestamp.
    Default order is most-recently-changed first (best for sync workflows).

    Prerequisites: none (token must be set).
    Follow-up: call get_item(item_id, include_markdown=True) to fetch article body.
    """
    await ctx.info(f"Listing items (status={status}, order={order}, limit={limit})")
    params: dict[str, Any] = {"order": order, "limit": limit}
    if status:
        params["status"] = status
    if content_types:
        params["content_type"] = ",".join(content_types)
    if tag_ids:
        params["tag"] = ",".join(tag_ids)
    if is_favorite is not None:
        params["is_favorite"] = is_favorite
    if updated_since:
        params["updated_since"] = updated_since
    if cursor:
        params["cursor"] = cursor

    raw = await api_get("/items", params=params)
    shaped = [_shape_item(i) for i in raw.get("results", [])]
    return _paginated(shaped, raw)


@mcp.tool(tags={"items"}, annotations={"readOnlyHint": True})
async def get_item(
    ctx: Context,
    item_id: Annotated[str, Field(description="The item ID (e.g. 'itm_r9f3a'). Use list_items() to discover IDs.")],
    include_markdown: Annotated[
        bool,
        Field(description="Include full article body as markdown. Counts against markdown rate limit (20/min). Only set True when needed."),
    ] = False,
) -> dict[str, Any]:
    """Get a single item from your library with full metadata.

    Optionally include the parsed article body as markdown (include_markdown=True).
    Check processing_status: 'completed' means all fields are populated;
    'processing' means extraction is still in progress (poll again in 20-60s).

    Prerequisites: call list_items() or save_item() to get an item_id.
    Follow-up: call list_annotations(item_id=...) to see highlights for this item.
    """
    await ctx.info(f"Fetching item {item_id} (markdown={include_markdown})")
    params: dict[str, Any] = {}
    if include_markdown:
        params["include"] = "markdown"

    raw = await api_get(f"/items/{item_id}", params=params or None)
    result = _shape_item(raw, include_markdown=include_markdown)

    if raw.get("processing_status") == "processing":
        result["note"] = "Content extraction is still in progress. Call get_item() again in 20-60 seconds."
        result["next_steps"] = [f"Call get_item(item_id='{item_id}') to check when processing completes."]
    else:
        steps: list[str] = [
            f"Call list_annotations(item_id='{item_id}') to see highlights.",
        ]
        if not include_markdown:
            steps.append(f"Call get_item(item_id='{item_id}', include_markdown=True) to read the full article.")
        result["next_steps"] = steps

    return result


@mcp.tool(tags={"items"}, annotations={"openWorldHint": True})
async def save_item(
    ctx: Context,
    url: Annotated[str, Field(description="The URL to save. Must start with http:// or https://.")],
    status: Annotated[
        Literal["queue", "archive"],
        Field(description="Where to place the item. 'queue' (default) = reading list. 'archive' = already read."),
    ] = "queue",
) -> dict[str, Any]:
    """Save a new item to your Matter library by URL.

    Triggers content extraction in the background. About 40% of saves complete
    instantly (cached content); the rest take 20-60 seconds. Check
    processing_status in the response: 'completed' means ready, 'processing'
    means poll get_item() to wait for metadata.

    If the URL is already in your library, the existing item is returned (status 200).

    Rate limit: 10 saves/min (each triggers extraction).
    Follow-up: call get_item(item_id=...) to check processing status.
    """
    await ctx.info(f"Saving item: {url}")
    raw = await api_post("/items", body={"url": url, "status": status})
    result = _shape_item(raw)

    if raw.get("processing_status") == "processing":
        result["note"] = (
            "Content extraction is in progress. Full metadata (title, author, word_count) will be available once processing completes."
        )
        result["next_steps"] = [f"Call get_item(item_id='{raw['id']}') in 20-60 seconds to get the full content."]
    else:
        result["next_steps"] = [
            f"Call get_item(item_id='{raw['id']}', include_markdown=True) to read the article.",
            f"Call add_tag_to_item(item_id='{raw['id']}', tag_name='...') to organize it.",
        ]

    return result


@mcp.tool(tags={"items"}, annotations={"idempotentHint": True})
async def update_item(
    ctx: Context,
    item_id: Annotated[str, Field(description="The item ID (e.g. 'itm_r9f3a').")],
    status: Annotated[
        Literal["queue", "archive"] | None,
        Field(description="Move the item to a new status. Inbox items can be moved to queue or archive, but not back to inbox."),
    ] = None,
    is_favorite: Annotated[
        bool | None,
        Field(description="Mark or unmark as favorite. Omit to leave unchanged."),
    ] = None,
    reading_progress: Annotated[
        float | None,
        Field(description="Reading progress as a float from 0.0 to 1.0.", ge=0.0, le=1.0),
    ] = None,
) -> dict[str, Any]:
    """Update an item's status, favorite flag, or reading progress.

    Common workflows:
    - Archive after reading: status='archive'
    - Add to reading queue: status='queue'
    - Star for later reference: is_favorite=True
    - Sync reading position: reading_progress=0.75

    Prerequisites: call list_items() or get_item() to get an item_id.
    Follow-up: call list_items(status='queue') to verify the change.
    """
    await ctx.info(f"Updating item {item_id}")
    body: dict[str, Any] = {}
    if status is not None:
        body["status"] = status
    if is_favorite is not None:
        body["is_favorite"] = is_favorite
    if reading_progress is not None:
        body["reading_progress"] = reading_progress
    if not body:
        msg = "Provide at least one field to update: status, is_favorite, or reading_progress."
        raise ToolError(msg)

    raw = await api_patch(f"/items/{item_id}", body=body)
    return _shape_item(raw)


@mcp.tool(tags={"items"}, annotations={"destructiveHint": True})
async def delete_item(
    ctx: Context,
    item_id: Annotated[str, Field(description="The item ID (e.g. 'itm_r9f3a'). This action is IRREVERSIBLE.")],
) -> dict[str, Any]:
    """Permanently remove an item and all its annotations from your library.

    WARNING: This is irreversible. All associated annotations and tag associations
    are permanently deleted. To keep the item, use update_item(status='archive') instead.

    Prerequisites: call list_items() or get_item() to confirm the item_id.
    """
    await ctx.warning(f"Deleting item {item_id} — irreversible action")
    await api_delete(f"/items/{item_id}")
    return {
        "deleted": True,
        "item_id": item_id,
        "note": "Item and all its annotations have been permanently deleted.",
    }


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------


@mcp.tool(tags={"annotations"}, annotations={"readOnlyHint": True})
async def list_annotations(
    ctx: Context,
    item_id: Annotated[str, Field(description="The item ID (e.g. 'itm_r9f3a'). Use list_items() to discover IDs.")],
    limit: Annotated[int, Field(description="Annotations per page (1-100).", ge=1, le=100)] = 100,
    cursor: Annotated[str | None, Field(description="Pagination cursor from a previous response.")] = None,
) -> dict[str, Any]:
    """List all text highlights and notes for a specific item.

    Annotations include the highlighted text and optional user notes.
    Useful for reviewing what you found important while reading.

    Prerequisites: call list_items() or get_item() to get an item_id.
    Follow-up: call update_annotation(annotation_id=..., note='...') to add notes.
    """
    await ctx.info(f"Listing annotations for item {item_id}")
    params: dict[str, Any] = {"limit": limit}
    if cursor:
        params["cursor"] = cursor

    raw = await api_get(f"/items/{item_id}/annotations", params=params)
    shaped = [_shape_annotation(a) for a in raw.get("results", [])]
    return _paginated(shaped, raw)


@mcp.tool(tags={"annotations"}, annotations={"readOnlyHint": True})
async def get_annotation(
    ctx: Context,
    annotation_id: Annotated[str, Field(description="The annotation ID (e.g. 'ann_m2k8v'). Use list_annotations() to discover IDs.")],
) -> dict[str, Any]:
    """Get a single annotation (highlight + note) by ID.

    Prerequisites: call list_annotations(item_id=...) to discover annotation IDs.
    Follow-up: call update_annotation() to add or change the note.
    """
    await ctx.info(f"Fetching annotation {annotation_id}")
    raw = await api_get(f"/annotations/{annotation_id}")
    result = _shape_annotation(raw)
    result["next_steps"] = [
        f"Call update_annotation(annotation_id='{annotation_id}', note='...') to add a note.",
        f"Call list_annotations(item_id='{raw['item_id']}') to see all annotations for this item.",
    ]
    return result


@mcp.tool(tags={"annotations"}, annotations={"idempotentHint": True})
async def update_annotation(
    ctx: Context,
    annotation_id: Annotated[str, Field(description="The annotation ID (e.g. 'ann_m2k8v').")],
    note: Annotated[
        str | None,
        Field(description="Your note on this highlight. Pass null/None to remove an existing note."),
    ] = None,
) -> dict[str, Any]:
    """Set or remove the user note on an annotation (highlight).

    The note is your personal commentary on the highlighted text.
    Pass note=None to remove an existing note.

    Prerequisites: call list_annotations(item_id=...) to get an annotation_id.
    """
    await ctx.info(f"Updating annotation {annotation_id}")
    raw = await api_patch(f"/annotations/{annotation_id}", body={"note": note})
    return _shape_annotation(raw)


@mcp.tool(tags={"annotations"}, annotations={"destructiveHint": True})
async def delete_annotation(
    ctx: Context,
    annotation_id: Annotated[str, Field(description="The annotation ID (e.g. 'ann_m2k8v'). This is IRREVERSIBLE.")],
) -> dict[str, Any]:
    """Permanently delete an annotation (highlight + note).

    WARNING: This action is irreversible. The highlight and any associated note
    will be permanently removed.

    Prerequisites: call list_annotations(item_id=...) to confirm the annotation_id.
    """
    await ctx.warning(f"Deleting annotation {annotation_id}")
    await api_delete(f"/annotations/{annotation_id}")
    return {
        "deleted": True,
        "annotation_id": annotation_id,
        "note": "Annotation permanently deleted.",
    }


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


@mcp.tool(tags={"tags"}, annotations={"readOnlyHint": True})
async def list_tags(
    ctx: Context,
    limit: Annotated[int, Field(description="Tags per page (1-100).", ge=1, le=100)] = 100,
    cursor: Annotated[str | None, Field(description="Pagination cursor from a previous response.")] = None,
) -> dict[str, Any]:
    """List all tags in your library with their item counts.

    Returns tag IDs, names, and how many items each tag is applied to.
    Use tag IDs from this response to filter list_items(tag_ids=[...]).

    Follow-up: call add_tag_to_item(item_id=..., tag_name=...) to tag an item.
    """
    await ctx.info("Listing tags")
    params: dict[str, Any] = {"limit": limit}
    if cursor:
        params["cursor"] = cursor

    raw = await api_get("/tags", params=params)
    shaped = [_shape_tag(t) for t in raw.get("results", [])]
    return _paginated(shaped, raw)


@mcp.tool(tags={"tags"}, annotations={"idempotentHint": True})
async def add_tag_to_item(
    ctx: Context,
    item_id: Annotated[str, Field(description="The item ID (e.g. 'itm_r9f3a').")],
    tag_name: Annotated[
        str,
        Field(description="Tag name (case-insensitive). Creates the tag if it doesn't exist. Reuses existing tag if name matches."),
    ],
) -> dict[str, Any]:
    """Add a tag to an item by name. Creates the tag if it doesn't exist.

    Tags are case-insensitive. If a tag named 'Essays' already exists, passing
    'essays' will reuse it. Returns the tag with its current item_count.

    Prerequisites: call list_items() or save_item() to get an item_id.
    Follow-up: call list_items(tag_ids=['tag_xxx']) to find all items with this tag.
    """
    await ctx.info(f"Adding tag '{tag_name}' to item {item_id}")
    raw = await api_post(f"/items/{item_id}/tags", body={"name": tag_name})
    result = _shape_tag(raw)
    result["item_id"] = item_id
    result["next_steps"] = [
        f"Call list_items(tag_ids=['{raw['id']}']) to browse all items with this tag.",
        f"Call remove_tag_from_item(item_id='{item_id}', tag_id='{raw['id']}') to undo.",
    ]
    return result


@mcp.tool(tags={"tags"}, annotations={"idempotentHint": True})
async def remove_tag_from_item(
    ctx: Context,
    item_id: Annotated[str, Field(description="The item ID.")],
    tag_id: Annotated[str, Field(description="The tag ID (e.g. 'tag_n5j2x'). Use list_tags() to discover IDs.")],
) -> dict[str, Any]:
    """Remove a tag from a specific item (does not delete the tag itself).

    Only removes the tag-item association. The tag still exists and remains
    on other items. Use delete_tag() to permanently remove a tag everywhere.

    Prerequisites: call list_tags() to get the tag_id, list_items() to get item_id.
    """
    await ctx.info(f"Removing tag {tag_id} from item {item_id}")
    await api_delete(f"/items/{item_id}/tags/{tag_id}")
    return {
        "removed": True,
        "item_id": item_id,
        "tag_id": tag_id,
        "note": "Tag removed from this item. The tag still exists and is on other items.",
    }


@mcp.tool(tags={"tags"}, annotations={"idempotentHint": True})
async def rename_tag(
    ctx: Context,
    tag_id: Annotated[str, Field(description="The tag ID (e.g. 'tag_n5j2x'). Use list_tags() to discover IDs.")],
    new_name: Annotated[str, Field(description="The new tag name. Applied globally to all items with this tag.")],
) -> dict[str, Any]:
    """Rename a tag globally. The new name applies to all items that have this tag.

    Prerequisites: call list_tags() to get the tag_id.
    Follow-up: call list_items(tag_ids=['tag_xxx']) to see affected items.
    """
    await ctx.info(f"Renaming tag {tag_id} to '{new_name}'")
    raw = await api_patch(f"/tags/{tag_id}", body={"name": new_name})
    return _shape_tag(raw)


@mcp.tool(tags={"tags"}, annotations={"destructiveHint": True})
async def delete_tag(
    ctx: Context,
    tag_id: Annotated[str, Field(description="The tag ID (e.g. 'tag_n5j2x'). This is IRREVERSIBLE.")],
) -> dict[str, Any]:
    """Permanently delete a tag and remove it from ALL items.

    WARNING: This is irreversible. The tag is removed from every item it was
    applied to and cannot be recovered. To remove a tag from one item only,
    use remove_tag_from_item() instead.

    Prerequisites: call list_tags() to confirm the tag_id and its item_count.
    """
    await ctx.warning(f"Deleting tag {tag_id} — irreversible, affects all items with this tag")
    await api_delete(f"/tags/{tag_id}")
    return {
        "deleted": True,
        "tag_id": tag_id,
        "note": "Tag permanently deleted and removed from all items.",
    }


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@mcp.tool(tags={"search"}, annotations={"readOnlyHint": True})
async def search(  # noqa: PLR0913,PLR0917
    ctx: Context,
    query: Annotated[
        str,
        Field(
            description=(
                "Search query (min 2 chars). Supports operators: "
                '"exact phrase" for phrase match, -excluded to exclude terms, '
                "by:author to filter by author, site:domain to filter by domain, "
                "title:word to match title only. "
                'Examples: "deep work", machine learning, by:graham site:paulgraham.com'
            ),
            min_length=2,
        ),
    ],
    search_type: Annotated[
        Literal["items"],
        Field(description="Result type to search. Currently only 'items' is supported."),
    ] = "items",
    status: Annotated[
        Literal["queue", "archive", "queue,archive"] | None,
        Field(description="Filter item results by status. Omit to search all content."),
    ] = None,
    limit: Annotated[int, Field(description="Max results per type (1-100).", ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Field(description="Pagination cursor from a previous response.")] = None,
) -> dict[str, Any]:
    """Full-text search across your Matter library, grouped by content type.

    Supports advanced operators: exact phrases, author filters, domain filters,
    title-only matches, and term exclusions. Results are ranked by relevance.

    Rate limit: 30 searches/min (separate from general read limit).
    Follow-up: call get_item(item_id=...) to read the full content.
    """
    await ctx.info(f"Searching for '{query}' (type={search_type})")
    params: dict[str, Any] = {"query": query, "type": search_type, "limit": limit}
    if status:
        params["status"] = status
    if cursor:
        params["cursor"] = cursor

    raw = await api_get("/search", params=params)
    items_raw = raw.get("items", {})
    shaped = [_shape_item(i) for i in items_raw.get("results", [])]

    return {
        "query": query,
        "items": {
            "count": len(shaped),
            "has_more": items_raw.get("has_more", False),
            "next_cursor": items_raw.get("next_cursor"),
            "results": shaped,
        },
        "next_steps": (
            [f"Call get_item(item_id='{shaped[0]['id']}') to read the top result."]
            if shaped
            else ["No results found. Try a broader query or remove status filters."]
        ),
    }


# ---------------------------------------------------------------------------
# Reading sessions
# ---------------------------------------------------------------------------


@mcp.tool(tags={"reading"}, annotations={"readOnlyHint": True})
async def list_reading_sessions(
    ctx: Context,
    since: Annotated[
        str | None,
        Field(description="ISO 8601 datetime. Return only sessions on or after this time. Example: '2026-04-01T00:00:00Z'."),
    ] = None,
    limit: Annotated[int, Field(description="Sessions per page (1-100).", ge=1, le=100)] = 100,
    cursor: Annotated[str | None, Field(description="Pagination cursor from a previous response.")] = None,
) -> dict[str, Any]:
    """List reading sessions with timestamps and durations.

    Each session records a single reading period (date + seconds_read).
    Use these to compute reading streaks, daily totals, or reading statistics.
    Sessions are ordered by date descending (newest first).

    For a specific date range, pass since with an ISO 8601 timestamp.
    Follow-up: aggregate seconds_read by date to compute daily reading totals.
    """
    await ctx.info(f"Listing reading sessions (since={since})")
    params: dict[str, Any] = {"limit": limit}
    if since:
        params["since"] = since
    if cursor:
        params["cursor"] = cursor

    raw = await api_get("/reading_sessions", params=params)
    sessions = [
        {
            "id": s["id"],
            "date": s["date"],
            "seconds_read": s["seconds_read"],
            "minutes_read": round(s["seconds_read"] / 60, 1),
        }
        for s in raw.get("results", [])
    ]
    result = _paginated(sessions, raw)
    if sessions:
        total_seconds = sum(s["seconds_read"] for s in sessions)
        result["total_minutes_read"] = round(total_seconds / 60, 1)
    return result


# ---------------------------------------------------------------------------
# Progressive discovery via BM25 search transform
# ---------------------------------------------------------------------------

try:
    from fastmcp.server.transforms.search import BM25SearchTransform  # type: ignore[import]

    mcp.add_transform(
        BM25SearchTransform(
            max_results=8,
            always_visible=["get_account", "list_items", "search", "save_item"],
        )
    )
except ImportError, AttributeError:
    pass
