"""Health check endpoint.

Used to verify the backend is running and to report configuration status.
"""

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Return application health and configuration status."""
    return {
        "status": "ok",
        "gemini_configured": settings.gemini_configured,
    }
