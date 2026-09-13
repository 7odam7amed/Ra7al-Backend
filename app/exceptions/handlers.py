import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.exceptions.base import AppException

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI application."""

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        logger.warning(
            "Application exception on %s %s: %s",
            request.method,
            request.url.path,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        # Never log client-supplied payloads or secrets here: log only the
        # exception type plus traceback via the standard logger (Vercel logs).
        logger.exception(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
        )
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

        # Re-attach CORS headers on the unhandled-error path.
        #
        # This handler runs in ServerErrorMiddleware, which sits OUTSIDE every
        # user middleware (including CORSMiddleware), so a plain JSONResponse
        # here would reach the browser without Access-Control-Allow-Origin.
        # The browser would then report the failure as a CORS/network error and
        # hide the real HTTP 500 (observed in production when a database fault
        # occurred). Origin policy is UNCHANGED: the header is only echoed for
        # origins already present in the app's explicit allow-list. Wildcards
        # are forbidden in production by Settings validation.
        origin = request.headers.get("origin")
        cors_config = next(
            (m.kwargs for m in app.user_middleware if m.cls is CORSMiddleware), None
        )
        if origin and cors_config:
            allow_origins = cors_config.get("allow_origins") or []
            allow_all = "*" in allow_origins and not cors_config.get(
                "allow_credentials"
            )
            if allow_all or origin in allow_origins:
                response.headers["Access-Control-Allow-Origin"] = origin
                if cors_config.get("allow_credentials"):
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                vary = response.headers.get("vary")
                response.headers["vary"] = "Origin" if not vary else f"{vary}, Origin"

        return response
