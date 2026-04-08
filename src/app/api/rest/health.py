"""Operational health endpoints."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    """Return a minimal health response."""
    return {"status": "ok", "service": "thvote-be-re"}
