"""Pytest test suite for FastAPI application layer (Phase 4 Stage 1).
Validates REST health, user switcher data, chat execution, streaming SSE,
session memory endpoints, and feedback override propagation.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import json

from src.api.main import app
from src.memory.session_store import SessionStore


@pytest_asyncio.fixture
async def api_client():
    """Async test client for the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_health_endpoint(api_client: AsyncClient):
    """Verifies system health check returns 200 and indicates database readiness."""
    response = await api_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "200 wells" in data["database"]
    assert "document sections" in data["vector_store"]
    assert "gemma" in data["primary_model"].lower()


@pytest.mark.asyncio
async def test_users_endpoint(api_client: AsyncClient):
    """Verifies fleet users list includes critical challenge personas with team and area mapping."""
    response = await api_client.get("/api/users")
    assert response.status_code == 200
    users = response.json()
    assert len(users) >= 15

    user_map = {u["user_id"]: u for u in users}
    
    # Check Michael Turner (U-201, production supervisor, Northeast)
    assert "U-201" in user_map
    assert user_map["U-201"]["name"] == "Michael Turner"
    assert user_map["U-201"]["role"] == "production_supervisor"
    assert user_map["U-201"]["team_id"] == "TEAM-NE"

    # Check Jessica Reed (U-202, field inspector, Northeast)
    assert "U-202" in user_map
    assert user_map["U-202"]["name"] == "Jessica Reed"

    # Check Laura Simmons (U-401, HSE officer)
    assert "U-401" in user_map
    assert user_map["U-401"]["role"] == "hse_officer"


@pytest.mark.asyncio
async def test_areas_endpoint(api_client: AsyncClient):
    """Verifies all 4 geographic areas are returned with coordinates and 50 wells each."""
    response = await api_client.get("/api/areas")
    assert response.status_code == 200
    areas = response.json()
    assert len(areas) == 4
    
    area_ids = {a["area_id"] for a in areas}
    assert area_ids == {"SW-23", "SW-24", "NE-07", "NE-08"}
    
    for a in areas:
        assert a["well_count"] == 50
        assert "center_lat" in a
        assert "center_lon" in a


@pytest.mark.asyncio
async def test_chat_synchronous_endpoint(api_client: AsyncClient):
    """Verifies POST /api/chat returns structured narrative, citations, and generative UI."""
    payload = {
        "message": "Is WELL-0001 producing oil right now? Show me its status card.",
        "user_id": "U-201",
        "session_id": "api_test_sync_01"
    }
    response = await api_client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    narrative = data["narrative"].lower()
    assert "not producing" in narrative or "idle" in narrative or "shut-in" in narrative or "shut in" in narrative
    assert "INS-0001-0203" in data["narrative"] or any("0001" in str(c) for c in data["citations"])
    assert data["user_id"] == "U-201"
    assert data["session_id"] == "api_test_sync_01"
    
    # Verify generative UI component was generated
    assert data["generative_ui"] is not None


@pytest.mark.asyncio
async def test_session_history_isolation_endpoint(api_client: AsyncClient):
    """Verifies GET /api/history returns conversational turns strictly isolated to user_id:session_id."""
    store = SessionStore.get_instance()
    test_user_a = "U-201"
    test_user_b = "U-202"
    session_id = "test_iso_session_99"

    store.record_turn(
        user_id=test_user_a,
        session_id=session_id,
        user_query="What are the top downtime wells?",
        narrative_response="WELL-0121, WELL-0138, and WELL-0107 had the highest downtime.",
        discussed_assets=["WELL-0121", "WELL-0138", "WELL-0107"]
    )

    # Query User A history
    res_a = await api_client.get(f"/api/history/{test_user_a}/{session_id}")
    assert res_a.status_code == 200
    turns_a = res_a.json()
    assert len(turns_a) == 1
    assert "WELL-0121" in turns_a[0]["narrative_response"]

    # Query User B history for same session_id - must be empty
    res_b = await api_client.get(f"/api/history/{test_user_b}/{session_id}")
    assert res_b.status_code == 200
    turns_b = res_b.json()
    assert len(turns_b) == 0


@pytest.mark.asyncio
async def test_feedback_override_endpoint(api_client: AsyncClient):
    """Verifies POST /api/feedback/override and GET /api/overrides propagate operational corrections."""
    override_payload = {
        "author_user_id": "U-201",
        "scope": "inspection",
        "target_id": "INS-0164-0205",
        "override_type": "raw_temp_correction",
        "corrected_value": 44.5,
        "original_value": 24.0,
        "reason": "Calibration recalibration on pyrometer"
    }
    try:
        post_res = await api_client.post("/api/feedback/override", json=override_payload)
        assert post_res.status_code == 200
        res_data = post_res.json()
        assert res_data["success"] is True

        # Check that it appears in GET /api/overrides
        list_res = await api_client.get("/api/overrides")
        assert list_res.status_code == 200
        overrides = list_res.json()
        targets = [o["target_id"] for o in overrides]
        assert "INS-0164-0205" in targets
    finally:
        # Restore baseline inspection data so other test suites remain isolated
        import asyncpg
        from src.config import settings
        conn = await asyncpg.connect(
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT
        )
        await conn.execute("UPDATE inspections SET wellhead_temp_c = 24.0, delta_temp_c = 4.1, is_producing = FALSE WHERE inspection_id = 'INS-0164-0205';")
        await conn.execute("DELETE FROM shared_context WHERE target_id = 'INS-0164-0205' AND text LIKE '%recalibration%';")
        await conn.close()


@pytest.mark.asyncio
async def test_chat_streaming_sse_endpoint(api_client: AsyncClient):
    """Verifies POST /api/chat/stream yields SSE events (status, token, done)."""
    payload = {
        "message": "Which area had the most downtime?",
        "user_id": "U-201",
        "session_id": "api_test_stream_01"
    }
    
    received_events = []
    async with api_client.stream("POST", "/api/chat/stream", json=payload) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event_type = line.split(":", 1)[1].strip()
                received_events.append(event_type)

    assert "status" in received_events
    assert "done" in received_events
