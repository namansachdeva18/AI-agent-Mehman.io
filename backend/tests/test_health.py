"""Tests for the health endpoint."""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_health_returns_ok():
    """GET /health should return status ok."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "gemini_configured" in data


@pytest.mark.anyio
async def test_chat_placeholder():
    """POST /api/chat should return an active agent response in Phase 4."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={"session_id": "test-session-1", "message": "Hello"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-session-1"
    assert data["agent_implemented"] is True
    assert len(data["reply"]) > 0
