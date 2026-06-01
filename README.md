# Orchestra MCP Server

A Model Context Protocol (MCP) server for the [Orchestra API](https://docs.getorchestra.io/docs/api/). End users can connect directly to Orchestra's hosted MCP endpoint and authenticate with their Orchestra API key.

## Features

- **Pipeline Management**: List pipeline runs, start pipelines, check status, and cancel runs
- **Task & Operation Monitoring**: Query task runs and operations with flexible filtering, including integration filters
- **Asset Discovery**: List and filter data assets across integrations
- **Pipeline Import**: Import pipelines from Git repositories
- **Logs & Artifacts**: Download task run logs and artifacts (e.g., dbt manifest files)

## Quick Start

Use Orchestra's hosted MCP endpoint:

- URL: `https://mcp.getorchestra.io/orchestra`
- Required header: `x-api-key: <your-orchestra-api-key>`
- API key location: [Orchestra workspace settings](https://app.getorchestra.io/settings/workspace)

### Cursor

Add this to `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "orchestra": {
      "url": "https://mcp.getorchestra.io/orchestra",
      "headers": {
        "x-api-key": "YOUR_ORCHESTRA_API_KEY"
      }
    }
  }
}
```

### Claude Code

Add the hosted server with:

```bash
claude mcp add --transport http --header "x-api-key: YOUR_ORCHESTRA_API_KEY" orchestra https://mcp.getorchestra.io/orchestra
```

### Other MCP clients

Any MCP client that supports remote HTTP/SSE servers can connect with this shape:

```json
{
  "mcpServers": {
    "orchestra": {
      "url": "https://mcp.getorchestra.io/orchestra",
      "headers": {
        "x-api-key": "YOUR_ORCHESTRA_API_KEY"
      }
    }
  }
}
```



## Managing Multiple Workspaces

If you need to connect to multiple Orchestra workspaces, you can set up separate MCP server connections with workspace-specific API keys:

```
{
  "mcpServers": {
    "orchestra-data-quality-tests": {
      "url": "https://mcp.getorchestra.io/orchestra",
      "headers": {
        "x-api-key": "DATA_QUALITY_WORKSPACE_API_KEY"
      }
    },
    "orchestra-sales-integrations": {
      "url": "https://mcp.getorchestra.io/orchestra",
      "headers": {
        "x-api-key": "SALES_WORKSPACE_API_KEY"
      }
    }
  }
}
```

## Run Locally

This section discusses how to run the MCP server locally, and is mainly intended for contributors.

### Prerequisites

- Python 3.10 or higher
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

### Run the server

```bash
python -m orchestramcp.server
```

Or with FastMCP CLI:

```bash
uv run fastmcp run orchestramcp/server.py
```

## Development

- Run `uv run pytest` to run tests.
- Run `uv run ruff check .` and `uv run ruff format .` to check and format code.

PRs to main will trigger CI checks in GitHub, `main` branch merges release to the dev & stage environments, and Github releases relase to the production environment.