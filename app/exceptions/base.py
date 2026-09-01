class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppException):
    """Raised when a requested resource does not exist."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404)


class ConflictError(AppException):
    """Raised when an operation conflicts with existing state."""

    def __init__(self, message: str = "Resource conflict") -> None:
        super().__init__(message, status_code=409)


class ValidationError(AppException):
    """Raised when business validation fails."""

    def __init__(self, message: str = "Validation failed") -> None:
        super().__init__(message, status_code=422)


class UnauthorizedError(AppException):
    """Raised when authentication is required or invalid."""

    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(message, status_code=401)


class ForbiddenError(AppException):
    """Raised when the caller lacks permission."""

    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message, status_code=403)
