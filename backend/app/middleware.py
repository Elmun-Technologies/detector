"""HTTP middleware: request correlation ids and structured access logging."""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .logging_setup import get_logger, new_request_id, set_request_id

REQUEST_ID_HEADER = 'X-Request-ID'
logger = get_logger('app.http')


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id to the context, response headers and access log."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER) or request.headers.get('x-correlation-id')
        # Only accept a client supplied id when it looks like an id, never echo arbitrary input.
        if incoming and (len(incoming) > 64 or not incoming.replace('-', '').isalnum()):
            incoming = None
        request_id = set_request_id(incoming or new_request_id())
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                'request failed',
                extra={
                    'http_method': request.method,
                    'http_path': request.url.path,
                    'duration_ms': duration_ms,
                    'status_code': 500,
                },
            )
            response = JSONResponse(status_code=500, content={'detail': 'Internal server error', 'request_id': request_id})
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            'request',
            extra={
                'http_method': request.method,
                'http_path': request.url.path,
                'status_code': response.status_code,
                'duration_ms': duration_ms,
            },
        )
        return response
