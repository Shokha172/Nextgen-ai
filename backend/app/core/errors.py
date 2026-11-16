"""Consistent error envelope: every failure looks the same to a client."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import log, request_id_ctx


class AppError(Exception):
    """Domain error with a stable machine-readable code."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None,
                 status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class Forbidden(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class Unauthorized(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class RateLimited(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class ValidationFailed(AppError):
    status_code = 422  # Unprocessable Content
    code = "validation_failed"


def _envelope(code: str, message: str, request: Request, details: Any = None) -> dict:
    body: dict[str, Any] = {
        "error": {"code": code, "message": message, "request_id": request_id_ctx.get()},
    }
    if details is not None:
        body["error"]["details"] = details
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        if exc.status_code >= 500:
            log.error(exc.message, extra={"path": request.url.path}, exc_info=True)
        return JSONResponse(_envelope(exc.code, exc.message, request, exc.details),
                            status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        # Pydantic embeds Decimal/ValueError objects in `ctx`; normalise before JSON.
        details = jsonable_encoder(exc.errors(), custom_encoder={Decimal: str, Exception: str})
        return JSONResponse(
            _envelope("validation_failed", "Request validation failed", request, details),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found",
                405: "method_not_allowed", 429: "rate_limited"}.get(exc.status_code, "http_error")
        return JSONResponse(_envelope(code, str(exc.detail), request), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.error("unhandled: %s", exc, extra={"path": request.url.path}, exc_info=True)
        # Never leak internals to the client.
        return JSONResponse(_envelope("internal_error", "Internal server error", request), status_code=500)
