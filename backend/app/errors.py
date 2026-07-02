"""Standardized API error responses and global exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("app.errors")


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request: Request | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            request_id=_request_id(request) if request else None,
            details=details,
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


def _sanitize_for_json(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict):
            message = str(detail.get("message", detail))
            code = str(detail.get("code", f"http_{exc.status_code}"))
            extra = {k: v for k, v in detail.items() if k not in ("message", "code")}
            return error_response(
                status_code=exc.status_code,
                code=code,
                message=message,
                request=request,
                details=extra or None,
            )
        return error_response(
            status_code=exc.status_code,
            code=f"http_{exc.status_code}",
            message=str(detail),
            request=request,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            status_code=422,
            code="validation_error",
            message="Request validation failed",
            request=request,
            details={"errors": _sanitize_for_json(exc.errors())},
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Database error request_id=%s", _request_id(request))
        return error_response(
            status_code=500,
            code="database_error",
            message="Database operation failed",
            request=request,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error request_id=%s", _request_id(request))
        return error_response(
            status_code=500,
            code="internal_error",
            message="An unexpected error occurred",
            request=request,
        )
