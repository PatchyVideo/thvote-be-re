"""REST router assembly."""

from fastapi import APIRouter

from .health import router as health_router
from .internal import router as internal_router

router = APIRouter()
router.include_router(health_router)
router.include_router(internal_router)
