"""Graceful degradation: structured error responses, no raw stack traces. T-24."""

import uuid

import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def register_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(asyncpg.PostgresConnectionError)
    async def db_unavailable(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "SERVICE_UNAVAILABLE", "detail": "Database unreachable"},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": "VALIDATION_ERROR", "detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_ERROR", "trace_id": trace_id},
        )
