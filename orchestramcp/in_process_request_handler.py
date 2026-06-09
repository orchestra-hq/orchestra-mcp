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


def _unwrap_exception_group(eg: BaseException) -> BaseException:
    exceptions = getattr(eg, "exceptions", None)
    if exceptions is None:
        return eg
    if len(exceptions) > 1 or len(exceptions) == 0:
        return eg

    child = exceptions[0]
    if getattr(child, "exceptions", None) is not None:
        return _unwrap_exception_group(child)
    return child


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
            result_data = result.model_dump(by_alias=True, mode="json", exclude_none=True)
            return types.JSONRPCResponse(
                jsonrpc=jsonrpc,
                id=req_id,
                result=result_data,
            ).model_dump(by_alias=True, mode="json", exclude_none=True)
    except BaseException as error:
        if getattr(error, "exceptions", None) is not None:
            error = _unwrap_exception_group(error)
            logger.error(f"Exception from exception group: {error}")
            return types.JSONRPCError(
                jsonrpc=jsonrpc,
                id=req_id,
                error=types.ErrorData(code=500, message=_INTERNAL_FAILURE_MESSAGE),
            ).model_dump(by_alias=True, mode="json", exclude_none=True)
        logger.error(f"General exception: {error}")
        return types.JSONRPCError(
            jsonrpc=jsonrpc,
            id=req_id,
            error=types.ErrorData(code=500, message=_INTERNAL_FAILURE_MESSAGE),
        ).model_dump(by_alias=True, mode="json", exclude_none=True)


class FastMCPInProcessRequestHandler(RequestHandler):
    def handle_request(
        self, request: JSONRPCRequest, context: LambdaContext
    ) -> JSONRPCResponse | JSONRPCError:
        request_dict = request.model_dump(by_alias=True, exclude_none=True)
        try:
            response_dict = anyio.run(_forward_request, request_dict)
            if "error" in response_dict:
                return JSONRPCError.model_validate(response_dict)
            return JSONRPCResponse.model_validate(response_dict)
        except BaseException as error:
            if getattr(error, "exceptions", None) is not None:
                error = _unwrap_exception_group(error)
                logger.error(f"Exception in in-process request handler: {error}")
                return JSONRPCError(
                    jsonrpc="2.0",
                    id=request.id,
                    error=ErrorData(
                        code=INTERNAL_ERROR,
                        message=_INTERNAL_FAILURE_MESSAGE,
                        data=str(error),
                    ),
                )
            logger.error(f"Exception in in-process request handler: {error}")
            return JSONRPCError(
                jsonrpc="2.0",
                id=request.id,
                error=ErrorData(
                    code=INTERNAL_ERROR,
                    message="Internal error",
                    data=str(error) if error else "Unknown error",
                ),
            )
