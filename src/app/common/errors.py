"""Application error types and handlers."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Raised for controlled application-level failures."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class NotFoundError(AppError):
    """Raised when a requested resource cannot be found."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404)


class ValidationError(AppError):
    """Raised when input validation fails at the service layer."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register shared exception handlers."""
    app.add_exception_handler(AppError, _handle_app_error)
