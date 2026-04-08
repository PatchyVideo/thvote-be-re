"""Internal-only endpoints used during migration."""

from fastapi import APIRouter

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/meta")
async def meta() -> dict[str, str]:
    """Expose a tiny bit of runtime metadata for smoke checks."""
    return {"mode": "migration", "layout": "src/app"}
