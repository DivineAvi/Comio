from fastapi import Request
from fastapi.responses import JSONResponse

class ComioException(Exception):
    """Base exception for Comio API errors."""

    def __init__(self, message: str, status_code: int = 500, details: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class NotFoundException(ComioException):
    """Resource not found (404)."""

    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} with id '{resource_id}' not found",
            status_code=404,
            details={"resource": resource, "id": resource_id},
        )


class UnauthorizedException(ComioException):
    """Authentication required or failed (401)."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(message=message, status_code=401)


class ForbiddenException(ComioException):
    """User doesn't have permission (403)."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message=message, status_code=403)


async def comio_exception_handler(request: Request, exc: ComioException) -> JSONResponse:
    """Converts our custom exceptions into clean JSON error responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.message,
                "details": exc.details,
            }
        },
    )