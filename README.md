# matter-mcp

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

An [MCP](https://modelcontextprotocol.io) server that gives AI assistants full access to your [Matter](https://getmatter.com) reading library — save articles, browse your queue, search highlights, track reading sessions, and more.

## What you can do

Ask your AI assistant things like:

- *"Save this article to my reading queue"*
- *"What articles have I saved about distributed systems?"*
- *"Summarise everything I've tagged 'AI' that I haven't finished"*
- *"Show me my highlights from last week"*
- *"Archive everything in my inbox older than a month"*

## Prerequisites

- [Matter Pro](https://web.getmatter.com/settings) subscription (required for API access)
- Python 3.14+
- A Matter API token — generate one at **Matter → Settings → Integrations → API**

## Installation

`matter-mcp` isn't published to PyPI — `uvx` installs it straight from this GitHub repo via `--from git+…`. To pin a version, append a tag or branch, e.g. `git+https://github.com/detailobsessed/matter-mcp.git@v0.1.0`.

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "matter": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/detailobsessed/matter-mcp.git", "matter-mcp"],
      "env": {
        "MATTER_API_TOKEN": "mat_your_token_here"
      }
    }
  }
}
```

### Cursor / VS Code (via MCP settings)

```json
{
  "matter": {
    "command": "uvx",
    "args": ["--from", "git+https://github.com/detailobsessed/matter-mcp.git", "matter-mcp"],
    "env": {
      "MATTER_API_TOKEN": "mat_your_token_here"
    }
  }
}
```

### Manual / other clients

```bash
MATTER_API_TOKEN=mat_your_token_here uvx --from git+https://github.com/detailobsessed/matter-mcp.git matter-mcp
```

## Tools

| Tool | Description |
| --- | --- |
| `get_account` | Your profile and current API quota |
| `list_items` | Browse your library with filters: status, content type, tag, favorites, date |
| `get_item` | Full item metadata; pass `include_markdown=True` to fetch article body |
| `save_item` | Save a URL to your library |
| `update_item` | Change status, favorite flag, or reading progress |
| `delete_item` | Permanently remove an item |
| `list_annotations` | All highlights and notes for an item |
| `get_annotation` | Single annotation by ID |
| `update_annotation` | Add or edit the note on a highlight |
| `delete_annotation` | Remove an annotation |
| `list_tags` | All tags with item counts |
| `add_tag_to_item` | Tag an item (creates the tag if it doesn't exist) |
| `remove_tag_from_item` | Remove a tag from an item |
| `rename_tag` | Rename a tag across all items |
| `delete_tag` | Delete a tag and remove it from all items |
| `search` | Full-text search across your library |
| `list_reading_sessions` | Reading history with duration per session |

## Development

```bash
git clone https://github.com/detailobsessed/matter-mcp
cd matter-mcp
uv sync
```

Run tests:

```bash
uv run pytest              # unit tests only
poe test-cov               # with coverage (term + lcov)
```

Run integration tests against the live API (requires a token):

```bash
op run --env-file=.env -- uv run pytest -m integration
```

Copy `.env.example` to `.env` and fill in your token (supports [1Password CLI](https://developer.1password.com/docs/cli/) `op://` references).
