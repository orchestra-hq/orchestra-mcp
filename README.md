# Orchestra MCP Server

A Model Context Protocol (MCP) server for the [Orchestra API](https://docs.getorchestra.io/docs/api/). End users can connect directly to Orchestra's hosted MCP endpoint and authenticate with their Orchestra API key.

## Features

- **Pipeline lifecycle**: List pipelines, validate definitions, create/update/delete Orchestra-backed pipelines, and import Git-backed pipelines
- **Runs**: Start pipeline runs (with optional branch/commit), poll status, cancel runs, and open lineage URLs
- **Observability**: List pipeline runs, task runs, and operations with filters; list assets
- **Logs and artifacts**: List and download task run logs and artifacts (for example dbt manifests), returned as base64 for safe transport

## MCP tools

| Tool | Auth required | Purpose |
|------|---------------|---------|
| `validate_pipeline` | No | Check a pipeline definition (JSON object) against the Orchestra schema (`POST /pipelines/schema`). Does not persist anything. |
| `list_pipelines` | Yes | List all pipelines for the workspace with latest run metadata (`GET /pipelines`). |
| `create_pipeline` | Yes | Create an Orchestra-backed pipeline from a definition object (`POST /pipelines`). |
| `update_pipeline` | Yes | Update an Orchestra-backed pipeline by alias (`PUT /pipelines/{alias}`). Git-backed pipelines cannot be updated here. |
| `delete_pipeline` | Yes | Delete a pipeline by alias (`DELETE /pipelines/{alias}`). |
| `import_pipeline` | Yes | Import a pipeline whose YAML lives in a Git repository (`POST /pipelines/import`). |
| `start_pipeline` | Yes | Start a run by alias or pipeline ID (`POST /pipelines/{alias_or_id}/start`). |
| `get_pipeline_run_status` | Yes | Poll a single pipeline run’s status. |
| `cancel_pipeline_run` | Yes | Request cancellation of a pipeline run. |
| `list_pipeline_runs` | Yes | List runs with optional time range plus array-based status and ID filters. |
| `list_task_runs` | Yes | List task runs with optional array-based filters (including integration). |
| `list_operations` | Yes | List operations with optional array-based filters. |
| `list_assets` | Yes | List data assets with optional array-based type and integration filters. |
| `list_task_run_logs` | Yes | List log filenames for a task run. |
| `download_task_run_log` | Yes | Download a log file (optional HTTP Range); content is base64-encoded in the result. |
| `list_task_run_artifacts` | Yes | List artifact filenames for a task run. |
| `download_task_run_artifact` | Yes | Download an artifact file; content is base64-encoded in the result. |
| `get_pipeline_run_lineage_url` | No | Return the UI URL for a pipeline run’s lineage graph (derived from `ORCHESTRA_ENV`). |

Your MCP client typically lists each tool’s parameters in its UI or in the protocol manifest.

### Orchestra CLI parity

The [Orchestra CLI](https://docs.getorchestra.io/docs/git-control-and-ci-cd/orchestra-cli) (`orchestra` / `orchestra-cli`) wraps the same public API for many workflows. Rough mapping:

| CLI command | MCP tool | Notes |
|-------------|----------|--------|
| `validate` | `validate_pipeline` | Pass the pipeline as a **JSON object** (same content as YAML after parsing). The CLI reads a file and posts JSON to the schema endpoint. This MCP tool also works without `ORCHESTRA_API_KEY`. |
| `fetch-pipelines` | `list_pipelines` | |
| `create-pipeline` | `create_pipeline` | Optional `published` / `storage_provider` arguments. |
| `update-pipeline` | `update_pipeline` | Orchestra-stored pipelines only. |
| `delete-pipeline` | `delete_pipeline` | |
| `import` | `import_pipeline` | The CLI infers Git remote, default branch, and path from your repo; the MCP tool expects explicit `storage_provider`, `repository`, branches, and `yaml_path`. |
| `run` | `start_pipeline` | Use `get_pipeline_run_status` (and optionally your client’s polling) where the CLI would wait; `get_pipeline_run_lineage_url` matches the CLI’s run link pattern. |

For local validation with a YAML file on disk, installing and using the CLI is often simplest; this server focuses on API-equivalent operations from agents. Where the Orchestra API expects comma-separated query parameters, this MCP server exposes those filters as arrays so MCP clients and agents can pass structured values naturally.

## Example calls

Pass JSON arguments as shown in your MCP client tool UI. For list filters, use arrays.

### `list_pipeline_runs` (array filters)

```json
{
  "time_from": "2026-04-01T00:00:00Z",
  "time_to": "2026-04-07T00:00:00Z",
  "status": ["RUNNING", "FAILED"],
  "pipeline_run_ids": ["11111111-1111-1111-1111-111111111111"]
}
```

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

```
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

`ORCHESTRA_API_KEY` is required for every tool except `validate_pipeline`, which calls Orchestra's public schema validation endpoint and can be used anonymously.

### Environment selection

By default, the server connects to the production host (`app.getorchestra.io`). You can override the environment with `ORCHESTRA_ENV`:

```bash
export ORCHESTRA_ENV="dev"
```

The base URL is `https://{ORCHESTRA_ENV}.getorchestra.io/api/engine/public`. Allowed values:

- `app` (default)
- `stage`
- `dev`

The CLI uses `BASE_URL` for a custom host; this MCP server uses `ORCHESTRA_ENV` instead.

## Usage

### Running the server

```bash
python -m orchestramcp.server
```

Or with FastMCP CLI:

```bash
uv run fastmcp run orchestramcp/server.py
```

### Connecting from MCP clients

#### Cursor

The below config can be added directly to your Cursor settings. Or, run `fastmcp install cursor orchestramcp/server.py`.

```json
{
  "mcpServers": {
    "Orchestra MCP Server": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "fastmcp",
        "fastmcp",
        "run",
        "/absolute/path/to/orchestra-mcp/orchestramcp/server.py"
      ],
      "env": {
        "ORCHESTRA_API_KEY": "your-api-key-here"
      },
      "transport": "stdio"
    }
  }
}
```

#### Claude Desktop

```json
{
  "mcpServers": {
    "Orchestra MCP Server": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "fastmcp",
        "fastmcp",
        "run",
        "/absolute/path/to/orchestra-mcp/orchestramcp/server.py"
      ],
      "env": {
        "ORCHESTRA_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

#### Windows

On Windows, you may need to adjust the command. For example:

```json
{
  "mcpServers": {
    "orchestramcp": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--project",
        "C:/repos/orchestra-mcp",
        "--with",
        "fastmcp",
        "fastmcp",
        "run",
        "orchestramcp/server.py"
      ],
      "env": {
        "ORCHESTRA_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

An equivalent config can be generated with `fastmcp install` or your client’s MCP installer; point `--project` at the repository root that contains the `orchestramcp` package.

## Development

- Run `uv run pytest` to run tests.
- Run `uv run ruff check .` and `uv run ruff format .` to check and format code.

PRs to `main` run tests and Ruff in GitHub Actions.
## References

- [Orchestra API](https://docs.getorchestra.io/docs/api/)
- [Orchestra CLI](https://docs.getorchestra.io/docs/git-control-and-ci-cd/orchestra-cli)
- [Pipeline YAML validation (REST)](https://docs.getorchestra.io/docs/git-control-and-ci-cd/ci-cd/validation)
