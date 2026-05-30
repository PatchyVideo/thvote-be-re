"""Custom exceptions for the application."""

from typing import Any, Optional


class AppException(Exception):
    """Base exception for all application exceptions."""

    def __init__(
        self,
        message: str,
        details: Optional[Any] = None,
        error_message: Optional[str] = None,
        upstream_response_string: Optional[str] = None,
    ):
        self.message = message
        self.details = details
        self.error_message = error_message
        self.upstream_response_string = upstream_response_string
        super().__init__(self.message)


class ValidationError(AppException):
    """Raised when input validation fails."""

    pass


class NotFoundError(AppException):
    """Raised when a requested resource is not found."""

    pass


class UnauthorizedError(AppException):
    """Raised when authentication or authorization fails."""

    pass


class RateLimitError(AppException):
    """Raised when rate limit is exceeded."""

    pass


class ServiceUnavailableError(AppException):
    """Raised when an external service is unavailable."""

    pass


class DatabaseError(AppException):
    """Raised when a database operation fails."""

    pass


class ExternalAPIError(AppException):
    """Raised when an external API call fails."""

    pass


class VoteWindowError(AppException):
    """Raised when voting outside the allowed time window."""

    pass
