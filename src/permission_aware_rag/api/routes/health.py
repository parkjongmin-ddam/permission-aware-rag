"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])

@router.get("")
async def health() -> dict[str,str]:
    """Health Check - return 200 if the service is Running"""
    return {"status": "ok"}