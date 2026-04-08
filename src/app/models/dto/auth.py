"""DTOs for authentication flows."""

from pydantic import BaseModel


class EmailLoginRequest(BaseModel):
    """Email/password login request."""

    email: str
    password: str


class LoginResult(BaseModel):
    """Minimal placeholder login response."""

    user_id: str
    session_token: str
