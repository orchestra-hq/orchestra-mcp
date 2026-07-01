# Orchestra MCP Server

A Model Context Protocol (MCP) server for the [Orchestra API](https://docs.getorchestra.io/docs/api/). End users can connect directly to Orchestra's hosted MCP endpoint and authenticate with their Orchestra API key.

## Quick Start

Use Orchestra's hosted MCP endpoint:

- URL: `https://mcp.getorchestra.io/orchestra`
- Required header: `Authorization: Bearer <YOUR_ORCHESTRA_API_KEY>`
- API key location: [Orchestra workspace settings](https://app.getorchestra.io/settings/workspace)

### Cursor

Add this to `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "orchestra": {
      "url": "https://mcp.getorchestra.io/orchestra",
      "headers": {
        "Authorization": "Bearer <YOUR_ORCHESTRA_API_KEY>"
      }
    }
  }
}
```

### Claude Code

Add the hosted server with:

```bash
claude mcp add --transport http --header "Authorization: Bearer <YOUR_ORCHESTRA_API_KEY>" orchestra https://mcp.getorchestra.io/orchestra
```

### Other MCP clients

Any MCP client that supports remote HTTP/SSE servers can connect with this shape:

```json
{
  "mcpServers": {
    "orchestra": {
      "url": "https://mcp.getorchestra.io/orchestra",
      "headers": {
        "Authorization": "Bearer <YOUR_ORCHESTRA_API_KEY>"
      }
    }
  }
}
```

## Managing Multiple Workspaces

If you need to connect to multiple Orchestra workspaces, you can set up separate MCP server connections with workspace-specific API keys:

```json
{
  "mcpServers": {
    "orchestra-data-quality-tests": {
      "url": "https://mcp.getorchestra.io/orchestra",
      "headers": {
        "Authorization": "Bearer <DATA_QUALITY_WORKSPACE_API_KEY>"
      }
    },
    "orchestra-sales-integrations": {
      "url": "https://mcp.getorchestra.io/orchestra",
      "headers": {
        "Authorization": "Bearer <SALES_WORKSPACE_API_KEY>"
      }
    }
  }
}
```

## Run Locally

This section discusses how to run the MCP server locally, and is mainly intended for contributors.

### Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Orchestra API key

### Install dependencies

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv sync
```

### Set API key

```bash
export ORCHESTRA_API_KEY="your-orchestra-api-key"
```

### (Optional) Select environment for local runs

For local development, the server defaults to `app`. You can override it with `ORCHESTRA_ENV`:

```bash
export ORCHESTRA_ENV="dev"
```

Valid values:

- `app` (default)
- `stage`
- `dev`

### (Optional) Enable destructive deletion

By default, the destructive `delete_pipeline` and `delete_environment` tools are not registered to avoid accidental destructive actions.
To expose them, set `ORCHESTRA_ENABLE_DELETE` before starting the server:

```bash
export ORCHESTRA_ENABLE_DELETE="true"
```

Only the following values are recognized:

- `"true"`
- `"TRUE"`
- `"1"`

### Run the server

```bash
python -m orchestramcp.server
```

Or with FastMCP CLI:

```bash
uv run fastmcp run orchestramcp/server.py
```

## Staying in sync with the Orchestra API

This MCP is a **curated** surface over the Orchestra API — hand-written tools with tuned
descriptions, selective exposure, and custom logic (base64 log/artifact handling, the
lineage URL, selector validation, delete-gating). It is deliberately *not* generated from
OpenAPI, because that curation is the value.

To keep the curated surface from silently drifting away from the API, a lightweight
conformance system links each tool to the operation it wraps and checks that link against
the live spec:

- **[`orchestramcp/api_contract.py`](orchestramcp/api_contract.py)** — the single source of
  truth mapping each MCP tool to its `(method, path, query params)` plus the model enums
  that mirror API enums. Update it whenever you add or change a tool.
- **[`scripts/check_api_conformance.py`](scripts/check_api_conformance.py)** — pulls the live
  OpenAPI spec and reports drift: renamed/removed paths or params, and enum values the API
  added or dropped. Exits non-zero on actionable drift, so it doubles as a check.
- **[`API_CONFORMANCE.md`](API_CONFORMANCE.md)** — auto-generated status report (do not edit).
- **`.github/workflows/api_conformance.yml`** — runs daily, auto-applies additive enum
  changes to `models.py`, refreshes the report, and opens a `[chore]` PR when the surface
  drifts. It does **not** run on pull requests, so live-API changes never block merges.

```bash
# Check against the live API
uv run python scripts/check_api_conformance.py

# Check a local spec, and auto-apply newly added enum values to models.py
uv run python scripts/check_api_conformance.py --spec openapi.json --apply-enums
```

### Adding a new tool

Scaffold starting-point stubs from a spec operation, then hand-finish them (naming,
docstring, response model, annotations):

```bash
uv run python scripts/scaffold_tool.py --path /assets/{asset_id} --method get
```

This prints a client method, a `@mcp.tool` function, and an `api_contract` entry to paste
in. Fill in the `TODO`s, then run the conformance check to confirm the contract matches.

## Development

- Run `uv run pytest` to run tests.
- Run `uv run ruff check .` and `uv run ruff format .` to check and format code.

PRs to main will trigger CI checks in GitHub, `main` branch merges release to the dev & stage environments, and Github releases relase to the production environment.
