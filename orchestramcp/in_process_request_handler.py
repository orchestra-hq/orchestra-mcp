import json
import logging
from copy import deepcopy
from typing import Any

import anyio
import mcp.types as types
from fastmcp.client.transports import FastMCPTransport
from mcp.types import (
    INTERNAL_ERROR,
    ErrorData,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
)
from mcp_lambda.handlers.request_handler import RequestHandler

from orchestramcp.server import get_mcp

logger = logging.getLogger(__name__)

_INTERNAL_FAILURE_MESSAGE = "Internal failure, please check Lambda function logs"

# Lambda rejects response payloads over ~6MB (6,291,556 bytes) with an opaque 413 the
# handler never sees. The guard fires below that with headroom for the API Gateway
# proxy wrapping and JSON string escaping of the body.
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
RESPONSE_TOO_LARGE_MESSAGE = "Response exceeds the maximum MCP payload size"


def _request_target(request: JSONRPCRequest) -> str:
    if request.method == "tools/call" and isinstance(request.params, dict):
        name = request.params.get("name")
        if name:
            return f"tool '{name}'"
    return f"method '{request.method}'"


def _guard_response_size(
    request: JSONRPCRequest, response_dict: dict[str, Any]
) -> JSONRPCError | None:
    size = len(json.dumps(response_dict, separators=(",", ":")).encode("utf-8"))
    target = _request_target(request)
    if size <= MAX_RESPONSE_BYTES:
        return None
    logger.error(
        f"MCP response too large: {size} bytes from {target} "
        f"(limit {MAX_RESPONSE_BYTES}); returning error to client"
    )
    return JSONRPCError(
        jsonrpc="2.0",
        id=request.id,
        error=ErrorData(
            code=INTERNAL_ERROR,
            message=(
                f"{RESPONSE_TOO_LARGE_MESSAGE}: {target} returned {size} bytes "
                f"(limit {MAX_RESPONSE_BYTES}). Narrow the request: use pagination or "
                f"filter parameters, or for file downloads request a byte range with "
                f"range_header, e.g. 'bytes=0-1048575'."
            ),
        ),
    )


def _unwrap_exception_group(error: BaseException) -> BaseException:
    exceptions = getattr(error, "exceptions", None)
    if exceptions is None or len(exceptions) != 1:
        return error

    child = exceptions[0]
    if getattr(child, "exceptions", None) is not None:
        return _unwrap_exception_group(child)
    return child


def _internal_error_response(
    jsonrpc: str | None,
    req_id: Any,
    log_message: str,
    error: BaseException,
) -> dict[str, Any]:
    logger.error(f"{log_message}: {error}")
    return types.JSONRPCError(
        jsonrpc=jsonrpc,
        id=req_id,
        error=types.ErrorData(code=500, message=_INTERNAL_FAILURE_MESSAGE),
    ).model_dump(by_alias=True, mode="json", exclude_none=True)


async def _forward_request(event: dict[str, Any]) -> dict[str, Any]:
    request = deepcopy(event)
    jsonrpc = request.pop("jsonrpc", None)
    req_id = request.pop("id", None)

    try:
        transport = FastMCPTransport(get_mcp())
        async with transport.connect_session() as session:
            await session.initialize()
            result = await session.send_request(
                request=types.ClientRequest(request),
                result_type=types.Result,
            )
            return types.JSONRPCResponse(
                jsonrpc=jsonrpc,
                id=req_id,
                result=result.model_dump(by_alias=True, mode="json", exclude_none=True),
            ).model_dump(by_alias=True, mode="json", exclude_none=True)
    except BaseException as error:
        if getattr(error, "exceptions", None) is not None:
            error = _unwrap_exception_group(error)
        return _internal_error_response(
            jsonrpc,
            req_id,
            log_message="MCP request failed",
            error=error,
        )


class FastMCPInProcessRequestHandler(RequestHandler):
    def handle_request(self, request: JSONRPCRequest, context) -> JSONRPCResponse | JSONRPCError:
        del context
        request_dict = request.model_dump(by_alias=True, exclude_none=True)
        try:
            response_dict = anyio.run(_forward_request, request_dict)
        except BaseException as error:
            if getattr(error, "exceptions", None) is not None:
                error = _unwrap_exception_group(error)
            logger.error(f"In-process handler failed: {error}")
            return JSONRPCError(
                jsonrpc="2.0",
                id=request.id,
                error=ErrorData(code=INTERNAL_ERROR, message=_INTERNAL_FAILURE_MESSAGE),
            )

        if "error" in response_dict:
            return JSONRPCError.model_validate(response_dict)
        too_large = _guard_response_size(request, response_dict)
        if too_large is not None:
            return too_large
        return JSONRPCResponse.model_validate(response_dict)
