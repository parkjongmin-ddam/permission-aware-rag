"""Health check endpoint."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from permission_aware_rag.db.session import get_connection

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health() -> JSONResponse:
    """Health check — returns status of API and DB components."""
    components: dict[str, str] = {"api": "ok"}
    overall_ok = True

    try:
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
        components["database"] = "ok"
    except Exception as exc:
        components["database"] = f"error: {type(exc).__name__}"
        overall_ok = False

    return JSONResponse(
        status_code=200 if overall_ok else 503,
        content={
            "status": "ok" if overall_ok else "degraded",
            "components": components,
        },
    )