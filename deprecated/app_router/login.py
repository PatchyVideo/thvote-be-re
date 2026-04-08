"""Legacy FastAPI route draft.

This module is kept only as a temporary reference while the real app skeleton
is being rebuilt under the future `app/` layout.
"""

from fastapi import APIRouter
from dao import LoginData, RegisterData

router = APIRouter(prefix="/user", tags=["user"])

@router.post("/login")
def login(user_data: LoginData):
    pass

@router.post("/register")
def register(register_data: RegisterData):
    pass
