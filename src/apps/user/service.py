"""User service layer."""

from datetime import UTC, datetime

from src.apps.user.dao import UserDAO
from src.apps.user.schemas import (
    EmailLoginRequest,
    LoginRequest,
    LoginResponse,
    LoginResult,
    RegisterRequest,
    RegisterResponse,
    RegisterResult,
    UserResponse,
    generate_user_id,
)
from src.apps.user.utils.security import AuthProvider
from src.common.exceptions import NotFoundError, ValidationError


class UserService:
    """Service for user-related business logic.

    Manages user authentication including:
    - Email/password login with JWT token generation
    - User registration with password hashing
    - Session token creation and validation
    - Legacy password hash migration support
    """

    def __init__(self, user_dao: UserDAO):
        self.user_dao = user_dao
        self._provider = AuthProvider()

    async def login(self, request: LoginRequest) -> LoginResponse:
        """Authenticate user and return login result."""
        raise NotImplementedError("Use login_with_email_password instead")

    async def login_with_email_password(
        self,
        request: EmailLoginRequest,
    ) -> LoginResult:
        """Authenticate user with email and password.

        Args:
            request: Email login request containing email and password

        Returns:
            LoginResult with user_id and session_token on success

        Raises:
            ValidationError: If credentials are invalid
        """
        user = await self.user_dao.get_by_email(request.email)
        if not user:
            raise ValidationError("Invalid email or password")

        result = self._provider.verify_any_password(
            password=request.password,
            password_hashed=user.password_hash or "",
            legacy_salt=user.legacy_salt,
        )

        if not result.valid:
            raise ValidationError("Invalid email or password")

        if result.needs_rehash and result.upgraded_hash:
            user.password_hash = result.upgraded_hash
            user.legacy_salt = None
            await self.user_dao.update(user)

        session_token = self._provider.create_session_token(str(user.id))

        return LoginResult(
            user_id=str(user.id),
            session_token=session_token,
            email=user.email,
            phone_number=user.phone_number,
        )

    async def register(self, request: RegisterRequest) -> RegisterResponse:
        """Register a new user account."""
        return await self.register_user(request, "")

    async def register_user(
        self,
        request: RegisterRequest,
        register_ip_address: str,
    ) -> RegisterResult:
        """Register a new user account.

        Args:
            request: Registration request with username, password, and optional contact info
            register_ip_address: IP address of the registration request

        Returns:
            RegisterResult with the new user's ID

        Raises:
            ValidationError: If email or phone already exists
        """
        if request.email:
            existing_user = await self.user_dao.get_by_email(request.email)
            if existing_user:
                raise ValidationError("Email already registered")

        if request.phone_number:
            existing_user = await self.user_dao.get_by_phone(request.phone_number)
            if existing_user:
                raise ValidationError("Phone number already registered")

        password_hash = self._provider.hash_password(request.password)

        from src.apps.user.models import User
        user = User(
            id=generate_user_id(),
            email=request.email,
            phone_number=request.phone_number,
            password_hash=password_hash,
            register_date=datetime.now(UTC),
            register_ip_address=register_ip_address,
        )

        created_user = await self.user_dao.create(user)

        return RegisterResult(
            user_id=str(created_user.id),
            email=created_user.email,
            phone_number=created_user.phone_number,
        )

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
