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

Both paths resolve to your Orchestra workspace; tools you can call are scoped to that workspace.

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

## Server configuration (hosting)

The hosted server is deployed to AWS Lambda and runs FastMCP's streamable-HTTP ASGI app via
[Mangum](https://github.com/jordaneremieff/mangum) behind API Gateway (handler:
`orchestramcp.lambda_handler.handler`). API Gateway must forward both the MCP path and
`/.well-known/*` to the Lambda with **no** gateway-level authorizer — authentication is enforced
inside the app.

Environment variables:

| Variable | Required | Purpose |
| --- | --- | --- |
| `ORCHESTRA_ENV` | yes (hosted) | Orchestra environment: `app` (default), `stage`, `dev`. |
| `MCP_PATH` | no | Path the MCP endpoint is mounted on. Defaults to the path of `MCP_PUBLIC_BASE_URL`, else `/orchestra`. Must match the route API Gateway forwards. |
| `MCP_PUBLIC_BASE_URL` | for OAuth | Public endpoint URL, e.g. `https://mcp.getorchestra.io/orchestra`. The origin is used as the resource-server base URL; the path supplies the resource identifier. |
| `MCP_OAUTH_ISSUER` | for OAuth | Authorization server issuer URL. |
| `MCP_OAUTH_JWKS_URI` | for OAuth | JWKS endpoint used to validate access-token signatures. |
| `MCP_OAUTH_AUDIENCE` | no | Token audience (RFC 8707). Defaults to the resource URL derived from `MCP_PUBLIC_BASE_URL` + `MCP_PATH`. |
| `ORCHESTRA_MCP_EXCHANGE_URL` | for OAuth | Orchestra endpoint that exchanges a validated OAuth identity for a workspace API key. |
| `ORCHESTRA_MCP_SERVICE_CREDENTIAL` | for OAuth | Confidential server-to-server credential for the exchange (store in a secret manager). |
| `ORCHESTRA_API_KEY` | local dev | Used only when running locally over stdio with no auth context. |

OAuth activates only when `MCP_OAUTH_ISSUER`, `MCP_OAUTH_JWKS_URI`, and `MCP_PUBLIC_BASE_URL` are
all set; otherwise the server runs in API-key-only mode.

## Development

- Run `uv run pytest` to run tests.
- Run `uv run ruff check .` and `uv run ruff format .` to check and format code.

PRs to main will trigger CI checks in GitHub, `main` branch merges release to the dev & stage environments, and Github releases relase to the production environment.
