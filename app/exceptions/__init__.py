"""Application exception hierarchy."""

from app.exceptions.base import (
    AppException,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.exceptions.handlers import register_exception_handlers

__all__ = [
    "AppException",
    "ConflictError",
    "ForbiddenError",
    "NotFoundError",
    "UnauthorizedError",
    "ValidationError",
    "register_exception_handlers",
]
