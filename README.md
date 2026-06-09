# Orchestra MCP Server

A Model Context Protocol (MCP) server for the [Orchestra API](https://docs.getorchestra.io/docs/api/). End users can connect directly to Orchestra's hosted MCP endpoint and authenticate with their Orchestra API key.

## Features

- **Pipeline lifecycle**: List pipelines, validate definitions, create/update Orchestra-backed pipelines, import Git-backed pipelines, migrate to git-backed storage, and optionally delete (opt-in)
- **Runs**: Start pipeline runs (with optional branch/commit/version), poll status, cancel runs, and open lineage URLs
- **Observability**: List pipeline runs, task runs, and operations with filters and pagination; list assets
- **Logs and artifacts**: List and download task run logs and artifacts (for example dbt manifests), returned as base64 for safe transport

## MCP tools

| Tool | Auth required | Purpose |
|------|---------------|---------|
| `validate_pipeline` | No | Check a pipeline definition (JSON object) against the Orchestra schema (`POST /pipelines/schema`). Does not persist anything. |
| `list_pipelines` | Yes | List all pipelines for the workspace with latest run metadata (`GET /pipelines`). |
| `get_pipeline` | Yes | Fetch a single pipeline by selector (`GET /pipeline`). |
| `create_pipeline` | Yes | Create an Orchestra-backed pipeline from a definition object (`POST /pipelines`). |
| `update_pipeline` | Yes | Update an Orchestra-backed pipeline by alias (`PUT /pipelines/{alias}`). Git-backed pipelines cannot be updated here. |
| `migrate_pipeline` | Yes | Migrate an Orchestra-backed pipeline to git-backed storage (`PATCH /pipelines/storage-settings`). The YAML must already exist in the repo. |
| `delete_pipeline` | Yes | **Disabled by default.** Delete a pipeline by selector (`DELETE /pipelines`). Set `ORCHESTRA_ENABLE_DELETE` to expose it. |
| `import_pipeline` | Yes | Import a pipeline whose YAML lives in a Git repository (`POST /pipelines/import`). |
| `start_pipeline` | Yes | Start a run by alias or pipeline ID (`POST /pipelines/{alias_or_id}/start`). Optionally target a `version_number`. |
| `get_pipeline_run_status` | Yes | Poll a single pipeline run’s status. |
| `cancel_pipeline_run` | Yes | Request cancellation of a pipeline run. |
| `list_pipeline_runs` | Yes | List runs with optional time range plus comma-separated status and ID filters. |
| `list_task_runs` | Yes | List task runs with optional comma-separated filters (including integration). |
| `list_operations` | Yes | List operations with optional comma-separated filters. |
| `list_assets` | Yes | List data assets with optional comma-separated type and integration filters. |
| `list_task_run_logs` | Yes | List log filenames for a task run. |
| `download_task_run_log` | Yes | Download a log file (optional HTTP Range); content is base64-encoded in the result. |
| `list_task_run_artifacts` | Yes | List artifact filenames for a task run. |
| `download_task_run_artifact` | Yes | Download an artifact file; content is base64-encoded in the result. |
| `get_pipeline_run_lineage_url` | No | Return the UI URL for a pipeline run’s lineage graph (derived from `ORCHESTRA_ENV`). |

Your MCP client also lists each tool’s parameters in its UI or in the protocol manifest. The full parameter reference is below.

## Tool parameters

Optional parameters show their default in parentheses where one applies. For multi-value list filters, pass a single comma-separated string (for example `"RUNNING,FAILED"`).

### Pipeline lifecycle

| Tool | Required | Optional |
|------|----------|----------|
| `validate_pipeline` | `pipeline_definition` (object) | — |
| `list_pipelines` | — | — |
| `get_pipeline` | — (provide one selector) | `pipeline_id`, `alias`, `repository` + `yaml_path`, `version`, `branch`, `commit` |
| `create_pipeline` | `alias`, `data` (object) | `published` (`false`), `storage_provider` (`ORCHESTRA`) |
| `update_pipeline` | `alias`, `data` (object) | `published` (`false`), `storage_provider` (`ORCHESTRA`) |
| `migrate_pipeline` | `path`, `repository`, `storage_provider`, `default_branch` | `working_branch`, and one selector: `alias` or `pipeline_id` |
| `delete_pipeline` | — (provide one selector) | `pipeline_id`, `alias`, `repository` + `yaml_path` |
| `import_pipeline` | `storage_provider`, `repository`, `default_branch`, `yaml_path` | `alias`, `working_branch` |

### Runs

| Tool | Required | Optional |
|------|----------|----------|
| `start_pipeline` | `alias_or_pipeline_id` | `branch`, `commit`, `environment`, `run_inputs` (object), `version_number` (int) |
| `get_pipeline_run_status` | `pipeline_run_id` | — |
| `cancel_pipeline_run` | `pipeline_run_id` | — |
| `get_pipeline_run_lineage_url` | `pipeline_run_id` | — |

### Observability

All four list tools accept `page` (1-based, default `1`) and `page_size` (default `50`, max `100`) for pagination.

| Tool | Required | Optional |
|------|----------|----------|
| `list_pipeline_runs` | — | `time_from`, `time_to`, `status`, `pipeline_run_ids`, `page`, `page_size` |
| `list_task_runs` | — | `time_from`, `time_to`, `status`, `pipeline_ids`, `integration`, `task_run_ids`, `page`, `page_size` |
| `list_operations` | — | `time_from`, `time_to`, `operation_type`, `integration`, `external_id`, `task_run_id`, `status`, `page`, `page_size` |
| `list_assets` | — | `asset_type`, `integration`, `page`, `page_size` |

### Logs and artifacts

| Tool | Required | Optional |
|------|----------|----------|
| `list_task_run_logs` | `pipeline_run_id`, `task_run_id` | — |
| `download_task_run_log` | `pipeline_run_id`, `task_run_id`, `filename` | `range_header` (HTTP `Range`, e.g. `bytes=-262144`) |
| `list_task_run_artifacts` | `pipeline_run_id`, `task_run_id` | — |
| `download_task_run_artifact` | `pipeline_run_id`, `task_run_id`, `filename` | — |

Times are ISO 8601 (for example `2026-04-01T00:00:00Z`). Downloaded log and artifact content is returned base64-encoded under a `content` key with `"encoding": "base64"`.

## Example calls

Pass JSON arguments as shown in your MCP client tool UI.

### `list_pipeline_runs` (filters + pagination)

```json
{
  "time_from": "2026-04-01T00:00:00Z",
  "time_to": "2026-04-07T00:00:00Z",
  "status": "RUNNING,FAILED",
  "pipeline_run_ids": "11111111-1111-1111-1111-111111111111",
  "page": 1,
  "page_size": 50
}
```

### `validate_pipeline` (no auth required)

```json
{
  "pipeline_definition": { "version": "v1", "name": "my_pipeline", "pipelines": {} }
}
```

### `create_pipeline`

```json
{
  "alias": "my_pipeline",
  "data": { "version": "v1", "name": "my_pipeline", "pipelines": {} },
  "published": true
}
```

### `start_pipeline`

```json
{
  "alias_or_pipeline_id": "my_pipeline",
  "branch": "main",
  "run_inputs": { "my_input": "value" },
  "version_number": 3
}
```

### `migrate_pipeline` (Orchestra-backed → git-backed)

The YAML must already be committed in the repository at `path`; this tool only repoints Orchestra at it.

```json
{
  "alias": "my_pipeline",
  "path": "pipelines/my_pipeline.yaml",
  "repository": "my-org/my-repo",
  "storage_provider": "GITHUB",
  "default_branch": "main"
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

### Configuration

The server is configured entirely through environment variables:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `ORCHESTRA_API_KEY` | Yes (most tools) | — | Workspace API key, sent as `Authorization: Bearer <key>`. Not needed for `validate_pipeline` or `get_pipeline_run_lineage_url`. |
| `ORCHESTRA_ENV` | No | `app` | Target environment / host. One of `app`, `stage`, `dev`. |
| `ORCHESTRA_ENABLE_DELETE` | No | unset (disabled) | Set to a truthy value (`1`, `true`, `yes`, `on`) to register the destructive `delete_pipeline` tool. |

### Set API key

```bash
export ORCHESTRA_API_KEY="your-orchestra-api-key"
```

`ORCHESTRA_API_KEY` is required for every tool except `validate_pipeline` (which calls Orchestra's public schema validation endpoint and can be used anonymously) and `get_pipeline_run_lineage_url` (which only builds a URL and makes no API call).

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

### Enabling pipeline deletion

The destructive `delete_pipeline` tool is **not registered by default**. To expose it, set `ORCHESTRA_ENABLE_DELETE` to a truthy value (`1`, `true`, `yes`, or `on`) before starting the server:

```bash
export ORCHESTRA_ENABLE_DELETE="true"
```

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
