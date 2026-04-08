"""Service layer for the auth module."""

from ...models.dto.auth import EmailLoginRequest, LoginResult
from .provider import AuthProvider
from .repository import AuthRepository


class AuthService:
    """Service entrypoint for authentication use cases."""

    def __init__(
        self,
        repository: AuthRepository | None = None,
        provider: AuthProvider | None = None,
    ) -> None:
        self.repository = repository or AuthRepository()
        self.provider = provider or AuthProvider()

    async def login_with_email_password(
        self,
        request: EmailLoginRequest,
    ) -> LoginResult:
        """Placeholder login flow until the real auth migration lands."""
        return LoginResult(user_id=request.email, session_token="pending")
