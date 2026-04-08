"""User API routes."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.user.schemas import (
    EmailLoginRequest,
    LoginRequest,
    LoginResponse,
    LoginResult,
    RegisterRequest,
    RegisterResponse,
    RegisterResult,
    UserResponse,
)
from src.apps.user.service import UserService
from src.common.database import get_db_session
from src.common.exceptions import ValidationError

router = APIRouter(prefix="/user", tags=["user"])


async def get_user_service(
    session: AsyncSession = Depends(get_db_session),
) -> UserService:
    """Dependency to get UserService instance."""
    from src.apps.user.dao import UserDAO
    dao = UserDAO(session)
    return UserService(dao)


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    service: UserService = Depends(get_user_service),
) -> LoginResponse:
    """Authenticate user."""
    return await service.login(request)


@router.post("/login/email", response_model=LoginResult)
async def login_with_email(
    request: EmailLoginRequest,
    service: UserService = Depends(get_user_service),
) -> LoginResult:
    """Authenticate user with email and password."""
    try:
        result = await service.login_with_email_password(request)
        return result
    except ValidationError as e:
        return LoginResult(
            user_id="",
            session_token="",
            email=None,
            phone_number=None,
        )


@router.post("/register", response_model=RegisterResponse)
async def register(
    request_body: RegisterRequest,
    request: Request,
    service: UserService = Depends(get_user_service),
) -> RegisterResponse:
    """Register a new user."""
    register_ip = request.client.host if request.client else ""
    try:
        result = await service.register_user(request_body, register_ip)
        return RegisterResponse(success=True, message="Registration successful")
    except ValidationError as e:
        return RegisterResponse(success=False, message=str(e))


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Get user by ID."""
    return await service.get_user_by_id(user_id)


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    service: UserService = Depends(get_user_service),
) -> dict:
    """Delete a user account."""
    success = await service.delete_user(user_id)
    return {"success": success}
