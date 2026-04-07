"""User service layer."""

from apps.user.dao import UserDAO
from apps.user.schemas import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    UserResponse,
)
from common.exceptions import NotFoundError, ValidationError


class UserService:
    """Service for user-related business logic."""

    def __init__(self, user_dao: UserDAO):
        self.user_dao = user_dao

    async def login(self, request: LoginRequest) -> LoginResponse:
        """Authenticate user and return login result."""
        # TODO: Implement actual authentication logic
        # This is a placeholder - integrate with user-manager Rust service
        raise NotImplementedError("Login functionality not yet implemented")

    async def register(self, request: RegisterRequest) -> RegisterResponse:
        """Register a new user account."""
        # Check if email already exists
        if request.email:
            existing_user = await self.user_dao.get_by_email(request.email)
            if existing_user:
                raise ValidationError("Email already registered")

        # Check if phone already exists
        if request.phone_number:
            existing_user = await self.user_dao.get_by_phone(request.phone_number)
            if existing_user:
                raise ValidationError("Phone number already registered")

        # TODO: Implement actual registration logic
        # This is a placeholder - integrate with user-manager Rust service
        raise NotImplementedError("Registration functionality not yet implemented")

    async def get_user_by_id(self, user_id: str) -> UserResponse:
        """Get user by ID."""
        user = await self.user_dao.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User with id {user_id} not found")
        return UserResponse.model_validate(user)

    async def update_user(self, user_id: str, **kwargs) -> UserResponse:
        """Update user information."""
        user = await self.user_dao.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User with id {user_id} not found")

        for key, value in kwargs.items():
            if hasattr(user, key) and value is not None:
                setattr(user, key, value)

        await self.user_dao.update(user)
        return UserResponse.model_validate(user)

    async def delete_user(self, user_id: str) -> bool:
        """Delete a user account."""
        return await self.user_dao.delete(user_id)
