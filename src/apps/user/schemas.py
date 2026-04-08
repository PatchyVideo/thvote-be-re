"""User schemas for request/response validation."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Request schema for user login."""

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """Request schema for user registration."""

    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6)
    phone_number: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None


class EmailLoginRequest(BaseModel):
    """Email/password login request."""

    email: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class LoginResult(BaseModel):
    """Login response containing user info and session token."""

    user_id: str
    session_token: str
    email: Optional[str] = None
    phone_number: Optional[str] = None


class RegisterResult(BaseModel):
    """Registration response."""

    user_id: str
    email: Optional[str] = None
    phone_number: Optional[str] = None


class TokenRefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


class TokenRefreshResult(BaseModel):
    """Token refresh response."""

    session_token: str


class UserResponse(BaseModel):
    """Response schema for user data."""

    id: str
    phone_number: Optional[str] = None
    email: Optional[str] = None
    register_date: datetime
    register_ip_address: str

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Response schema for login result."""

    success: bool
    token: Optional[str] = None
    user: Optional[UserResponse] = None
    message: Optional[str] = None


class RegisterResponse(BaseModel):
    """Response schema for registration result."""

    success: bool
    user_id: Optional[str] = None
    message: Optional[str] = None


def generate_user_id() -> str:
    """Generate a unique user ID."""
    return str(uuid.uuid4())
