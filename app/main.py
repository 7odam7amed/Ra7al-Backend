import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import health_router
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.middleware import SecurityHeadersMiddleware
from app.exceptions.handlers import register_exception_handlers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("Starting %s [%s]", settings.APP_NAME, settings.APP_ENV)
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()

    app = FastAPI(
        title=settings.APP_NAME,
        description="Backend API for the University Bus Management System.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    cors_origins = list(settings.CORS_ORIGINS)
    if not settings.is_production:
        for dev_origin in (
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
        ):
            if dev_origin not in cors_origins:
                cors_origins.append(dev_origin)

    app.add_middleware(SecurityHeadersMiddleware)

    # NOTE: Starlette applies middleware in reverse registration order, so the
    # LAST middleware added wraps everything outside it. CORSMiddleware must be
    # the OUTERMOST layer so that CORS headers are present on every response,
    # including 500 errors produced by inner exception handlers/middleware.
    # Without this, an unexpected server error (e.g. a database fault) reaches
    # the browser without Access-Control-Allow-Origin and is misreported by the
    # frontend as a CORS/network failure, hiding the real backend error.
    # This changes ONLY response header behavior - origin policy is unchanged:
    # allow_origins stays an explicit allow-list (never "*") enforced below.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
