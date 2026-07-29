from fastapi import APIRouter, Depends, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness — the process is up. No dependency checks."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(response: Response, db: AsyncIOMotorDatabase = Depends(get_db)) -> dict:
    """Readiness — can this instance actually serve traffic (is Mongo reachable)? Goes through
    the get_db dependency, not request.app.state.db directly — consistent with every other
    router, and what makes this endpoint's db reachability overridable in tests at all."""
    try:
        await db.command("ping")
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready"}
    return {"status": "ready"}
