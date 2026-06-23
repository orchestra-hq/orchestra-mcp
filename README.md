# Orchestra MCP Server

A Model Context Protocol (MCP) server for the [Orchestra API](https://docs.getorchestra.io/docs/api/). End users can connect directly to Orchestra's hosted MCP endpoint and authenticate with their Orchestra API key.

## Quick Start

Use Orchestra's hosted MCP endpoint:

- URL: `https://mcp.getorchestra.io/orchestra`
- Required header: `Authorization: Bearer <YOUR_ORCHESTRA_API_KEY>`
- API key location: [Orchestra workspace settings](https://app.getorchestra.io/settings/workspace)

## Authentication

The hosted server accepts two kinds of bearer credential:

1. **Orchestra API key (header auth)** — pass `Authorization: Bearer <YOUR_ORCHESTRA_API_KEY>`
   as shown in the examples below. This is the simplest option for editors like Cursor and Claude
   Code and continues to work unchanged.
2. **OAuth 2.1** — supported clients (e.g. Claude connectors) run the browser login flow
   automatically; you do not paste an API key. The server advertises
   [RFC 9728 Protected Resource Metadata](https://datatracker.ietf.org/doc/html/rfc9728) at
   `https://mcp.getorchestra.io/.well-known/oauth-protected-resource/orchestra`, and returns a
   `WWW-Authenticate` challenge on `401` so clients can discover the authorization server.
   OAuth is inert until the `MCP_OAUTH_*` environment variables are configured on the server.

Both paths resolve to your Orchestra workspace; tools you can call are scoped to that workspace.

## Available Tools

| Tool | Auth required | Purpose | Category |
|------|---------------|---------|------|
| `validate_pipeline` | No | Check a pipeline definition (JSON object) against the Orchestra schema (`POST /pipelines/schema`). Does not persist anything. | Pipeline lifecycle |
| `list_pipelines` | Yes | List all pipelines for the workspace with latest run metadata (`GET /pipelines`). | Pipeline lifecycle |
| `get_pipeline` | Yes | Fetch a single pipeline by selector (`GET /pipeline`). | Pipeline lifecycle |
| `create_pipeline` | Yes | Create an Orchestra-backed pipeline from a definition object (`POST /pipelines`). | Pipeline lifecycle |
| `update_pipeline` | Yes | Update an Orchestra-backed pipeline by alias (`PUT /pipelines/{alias}`). Git-backed pipelines cannot be updated here. | Pipeline lifecycle |
| `migrate_pipeline` | Yes | Migrate an Orchestra-backed pipeline to git-backed storage (`PATCH /pipelines/storage-settings`). The YAML must already exist in the repo. | Pipeline lifecycle |
| `delete_pipeline` | Yes | **Disabled by default.** Delete a pipeline by selector (`DELETE /pipelines`). Set `ORCHESTRA_ENABLE_DELETE` to expose it. | Pipeline lifecycle |
| `import_pipeline` | Yes | Import a pipeline whose YAML lives in a Git repository (`POST /pipelines/import`). | Pipeline lifecycle |
| `start_pipeline` | Yes | Start a run by alias or pipeline ID (`POST /pipelines/{alias_or_id}/start`). Optionally target a `version_number`. | Pipeline running |
| `get_pipeline_run_status` | Yes | Poll a single pipeline run’s status. | Pipeline running |
| `cancel_pipeline_run` | Yes | Request cancellation of a pipeline run. | Pipeline running |
| `get_pipeline_run_lineage_url` | No | Return the UI URL for a pipeline run’s lineage graph (derived from `ORCHESTRA_ENV`). | Pipeline running |
| `list_pipeline_runs` | Yes | List runs with optional time range plus comma-separated status and ID filters. | Observability |
| `list_task_runs` | Yes | List task runs with optional comma-separated filters (including integration). | Observability |
| `list_operations` | Yes | List operations with optional comma-separated filters. | Observability |
| `list_assets` | Yes | List data assets with optional comma-separated type and integration filters. | Observability |
| `list_task_run_logs` | Yes | List log filenames for a task run. | Logs and artifacts |
| `download_task_run_log` | Yes | Download a log file (optional HTTP Range); content is base64-encoded in the result. | Logs and artifacts |
| `list_task_run_artifacts` | Yes | List artifact filenames for a task run. | Logs and artifacts |
| `download_task_run_artifact` | Yes | Download an artifact file; content is base64-encoded in the result. | Logs and artifacts |
| `list_integration_connections` | Yes | List integration connections with optional filter on integration and connection status | Integrations |


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

### (Optional) Enable destructive pipeline deletion

By default, the MCP `delete_pipeline` tool is not registered to avoid accidental destructive actions.
To expose it, set `ORCHESTRA_ENABLE_DELETE` before starting the server:

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

## Server configuration (hosting)

The hosted server is deployed to AWS Lambda and runs FastMCP's streamable-HTTP ASGI app via
[Mangum](https://github.com/Kludex/mangum) behind API Gateway (handler:
`orchestramcp.lambda_handler.handler`). API Gateway must forward both the MCP path and
`/.well-known/*` to the Lambda with **no** gateway-level authorizer — authentication is enforced
inside the app.

Environment variables:

| Variable | Required | Purpose |
| --- | --- | --- |
| `ORCHESTRA_ENV` | yes (hosted) | Orchestra environment: `app`, `stage`, `dev`. The Lambda refuses requests without it so a misconfigured deployment cannot silently hit production. |
| `MCP_PUBLIC_BASE_URL` | for OAuth | Full public URL of the MCP endpoint, e.g. `https://mcp.getorchestra.io/orchestra`. Defines the mount path and the RFC 9728 resource identifier. Without it the endpoint mounts at `/orchestra`. |
| `MCP_OAUTH_ISSUER` | for OAuth | Authorization server issuer URL (advertised in the protected-resource metadata). |
| `MCP_OAUTH_JWKS_URI` | for OAuth | JWKS endpoint used to validate OAuth access tokens. |
| `MCP_OAUTH_AUDIENCE` | no | Expected token audience. Defaults to `MCP_PUBLIC_BASE_URL`. |
| `ORCHESTRA_MCP_EXCHANGE_URL` | for OAuth | Orchestra server-to-server endpoint that exchanges a validated OAuth identity for a workspace API key. |
| `ORCHESTRA_MCP_SERVICE_CREDENTIAL` | for OAuth | Confidential credential the MCP server uses to call the exchange endpoint. |

OAuth only activates when `MCP_OAUTH_ISSUER`, `MCP_OAUTH_JWKS_URI` and `MCP_PUBLIC_BASE_URL` are
all set; otherwise the server runs in API-key-only mode.

## Development

- Run `uv run pytest` to run tests.
- Run `uv run ruff check .` and `uv run ruff format .` to check and format code.

PRs to main will trigger CI checks in GitHub, `main` branch merges release to the dev & stage environments, and Github releases relase to the production environment.
