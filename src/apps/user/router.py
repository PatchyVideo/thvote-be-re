"""User API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.user.schemas import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    UserResponse,
)
from src.apps.user.service import UserService
from src.common.database import get_db_session

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


@router.post("/register", response_model=RegisterResponse)
async def register(
    request: RegisterRequest,
    service: UserService = Depends(get_user_service),
) -> RegisterResponse:
    """Register a new user."""
    return await service.register(request)


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
