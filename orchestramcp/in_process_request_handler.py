import logging
from copy import deepcopy
from typing import Any

import anyio
import mcp.types as types
from aws_lambda_powertools.utilities.typing import LambdaContext
from fastmcp.client.transports import FastMCPTransport
from mcp.types import (
    INTERNAL_ERROR,
    ErrorData,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
)
from mcp_lambda.handlers.request_handler import RequestHandler

from orchestramcp.server import mcp

logger = logging.getLogger(__name__)

_INTERNAL_FAILURE_MESSAGE = "Internal failure, please check Lambda function logs"


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
        transport = FastMCPTransport(mcp)
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
    def handle_request(
        self, request: JSONRPCRequest, context: LambdaContext
    ) -> JSONRPCResponse | JSONRPCError:
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
        return JSONRPCResponse.model_validate(response_dict)
