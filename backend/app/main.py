"""FastAPI application entry point.

Sets up the app, CORS middleware, request correlation tracking,
standardized error handlers, and route registration.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes.chat import router as chat_router
from app.api.routes.conversations import router as conversations_router
from app.api.routes.health import router as health_router
from app.config import settings
from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Assigns or propagates X-Request-ID correlation headers on all requests."""

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:12]}"
        request.state.request_id = req_id

        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        response.headers["X-Request-ID"] = req_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
        return response


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Lifespan context manager: ensures SQLite database is initialized and seeded on startup."""
    try:
        from app.database.connection import Database
        from app.database.seed import seed_database
        db = Database()
        db.connect()
        row = db.execute("SELECT count(*) as cnt FROM sqlite_master WHERE type='table' AND name='properties'").fetchone()
        cnt = 0
        if row and row["cnt"] > 0:
            cnt_row = db.execute("SELECT count(*) as cnt FROM properties").fetchone()
            cnt = cnt_row["cnt"] if cnt_row else 0
        if cnt == 0:
            logger.info("Initializing and seeding database on startup...")
            seed_database(db)
        db.close()
    except Exception as e:
        logger.warning(f"Database auto-seed check on startup encountered: {e}")
    yield


def create_app() -> FastAPI:
    """Application factory."""
    application = FastAPI(
        title=settings.app_name,
        description="AI-powered hotel booking agent for the Mehman.io case study.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- Correlation Tracking Middleware ---
    application.add_middleware(RequestCorrelationMiddleware)

    # --- CORS (Environment-driven allowed origins + Vercel / localhost regex) ---
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins if "*" not in settings.cors_origins else ["*"],
        allow_origin_regex=r"https://.*\.vercel\.app|http://localhost:\d+|http://127\.0\.0\.1:\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Standardized Error Handlers ---
    @application.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code.value,
                    "message": exc.message,
                    "retryable": exc.retryable,
                    "details": exc.details,
                    "request_id": req_id,
                },
                # Backward compatibility keys
                "error_code": exc.code.value,
                "message": exc.message,
            },
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": ErrorCode.INVALID_REQUEST.value,
                    "message": "Invalid request payload format or parameters.",
                    "retryable": False,
                    "details": {"validation_errors": exc.errors()},
                    "request_id": req_id,
                },
                "error_code": ErrorCode.INVALID_REQUEST.value,
                "message": "Invalid request payload format or parameters.",
            },
        )

    @application.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        logger.error(f"Unhandled server exception (Request {req_id}): {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": ErrorCode.INTERNAL_ERROR.value,
                    "message": "An unexpected internal server error occurred.",
                    "retryable": True,
                    "details": {},
                    "request_id": req_id,
                },
                "error_code": ErrorCode.INTERNAL_ERROR.value,
                "message": "An unexpected internal server error occurred.",
            },
        )

    # --- Routes ---
    application.include_router(health_router)
    application.include_router(chat_router, prefix="/api")
    application.include_router(conversations_router)

    return application


app = create_app()
