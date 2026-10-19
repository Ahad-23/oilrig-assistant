"""Unit and integration test suite for Langfuse Agent Observability.
Verifies trace context propagation, sensitive data redaction, semantic observation types,
generation tracking, tool execution tracing, and user feedback scoring.
"""

import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

from src.config import settings
from src.observability.langfuse_tracer import (
    is_langfuse_active,
    get_langfuse_client,
    get_langfuse_callback_handler,
    mask_sensitive_data,
    propagate_agent_trace,
    record_llm_generation,
    record_tool_execution,
    score_agent_trace,
    flush_langfuse,
)
from src.api.schemas import ChatResponse, FeedbackScoreRequest, FeedbackScoreResponse


def test_mask_sensitive_data():
    """Verifies that credentials, connection strings, and tokens are redacted."""
    raw_payload = {
        "user_id": "U-201",
        "password": "secret_password_123",
        "api_key": "sk-1234567890abcdef",
        "nested": {
            "token": "Bearer xyz1234567890abcdefghij",
            "safe_metric": 42.5
        },
        "query": "SELECT * FROM db WHERE url = 'postgresql://admin:super_secret@localhost:5432/db'"
    }

    sanitized = mask_sensitive_data(raw_payload)
    assert sanitized["user_id"] == "U-201"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["token"] == "[REDACTED]"
    assert sanitized["nested"]["safe_metric"] == 42.5
    assert "super_secret" not in sanitized["query"]
    assert "[REDACTED]" in sanitized["query"]


def test_langfuse_inactive_by_default_without_keys():
    """Verifies safe fallback when keys are absent."""
    with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""}, clear=False):
        with patch.object(settings, "LANGFUSE_PUBLIC_KEY", None):
            with patch.object(settings, "LANGFUSE_SECRET_KEY", None):
                assert is_langfuse_active() is False
                assert get_langfuse_callback_handler() is None


def test_propagate_agent_trace_inactive_fallback():
    """Verifies that propagate_agent_trace yields cleanly without error when Langfuse is inactive."""
    with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""}, clear=False):
        with patch.object(settings, "LANGFUSE_PUBLIC_KEY", None):
            with patch.object(settings, "LANGFUSE_SECRET_KEY", None):
                with propagate_agent_trace(
                    trace_name="Test Inactive Trace",
                    user_id="U-201",
                    session_id="sess-01"
                ) as client:
                    assert client is None


@pytest.mark.asyncio
async def test_record_llm_generation_active():
    """Verifies that record_llm_generation updates generation observation with usage details."""
    mock_gen = MagicMock()
    mock_client = MagicMock()
    mock_client.start_as_current_observation.return_value.__enter__.return_value = mock_gen

    with patch("src.observability.langfuse_tracer.get_langfuse_client", return_value=mock_client):
        async with record_llm_generation(
            name="llm:test-model",
            model="openrouter/google/gemma-4-26b-a4b-it",
            messages=[{"role": "user", "content": "What is status of WELL-0042?"}],
            model_parameters={"temperature": 0.0, "max_tokens": 4096}
        ) as gen:
            gen.update(
                output={"content": "WELL-0042 is producing", "tool_calls": []},
                usage_details={"input": 150, "output": 45, "total": 195}
            )

        mock_client.start_as_current_observation.assert_called_once()
        call_kwargs = mock_client.start_as_current_observation.call_args[1]
        assert call_kwargs["as_type"] == "generation"
        assert call_kwargs["model"] == "openrouter/google/gemma-4-26b-a4b-it"
        mock_gen.update.assert_called_once_with(
            output={"content": "WELL-0042 is producing", "tool_calls": []},
            usage_details={"input": 150, "output": 45, "total": 195}
        )


@pytest.mark.asyncio
async def test_record_tool_execution_observation_types():
    """Verifies that tools are tagged with correct semantic observation types conforming to Langfuse specs."""
    mock_obs = MagicMock()
    mock_client = MagicMock()
    mock_client.start_as_current_observation.return_value.__enter__.return_value = mock_obs

    with patch("src.observability.langfuse_tracer.get_langfuse_client", return_value=mock_client):
        # 1. Knowledge base search -> retriever
        async with record_tool_execution("search_knowledge_base", {"query": "SOP pipeline"}) as obs:
            obs.update(output={"results": []})
        call_kwargs = mock_client.start_as_current_observation.call_args[1]
        assert call_kwargs["as_type"] == "retriever"

        # 2. Conflict check -> guardrail
        async with record_tool_execution("check_claim_conflicts", {"well_id": "WELL-0042", "claimed_status": "Producing"}) as obs:
            obs.update(output={"conflict_detected": False})
        call_kwargs = mock_client.start_as_current_observation.call_args[1]
        assert call_kwargs["as_type"] == "guardrail"

        # 3. SQL / analytical tool -> tool
        async with record_tool_execution("get_well_current_status", {"asset_id": "WELL-0042"}) as obs:
            obs.update(output={"is_producing": True})
        call_kwargs = mock_client.start_as_current_observation.call_args[1]
        assert call_kwargs["as_type"] == "tool"


def test_score_agent_trace():
    """Verifies creating scores against a trace ID."""
    mock_client = MagicMock()
    with patch("src.observability.langfuse_tracer.get_langfuse_client", return_value=mock_client):
        success = score_agent_trace(
            trace_id="trace-abc-123",
            name="user-feedback",
            value=1.0,
            comment="Accurate resolution",
            metadata={"operator": "Michael Turner"}
        )
        assert success is True
        mock_client.create_score.assert_called_once_with(
            trace_id="trace-abc-123",
            name="user-feedback",
            value=1.0,
            data_type="NUMERIC",
            comment="Accurate resolution",
            metadata={"operator": "Michael Turner"}
        )


def test_flush_langfuse_safe():
    """Verifies that flush_langfuse handles errors gracefully."""
    mock_client = MagicMock()
    mock_client.flush.side_effect = Exception("Network timeout")
    with patch("src.observability.langfuse_tracer.get_langfuse_client", return_value=mock_client):
        # Must not raise
        flush_langfuse()
        mock_client.flush.assert_called_once()


def test_chat_response_schema_trace_id():
    """Verifies that ChatResponse includes trace_id serialization."""
    resp = ChatResponse(
        narrative="Operational summary for South Field",
        citations=[],
        user_id="U-201",
        session_id="session-42",
        trace_id="trace-xyz-789"
    )
    assert resp.trace_id == "trace-xyz-789"
    dump = resp.model_dump()
    assert dump["trace_id"] == "trace-xyz-789"


def test_feedback_score_endpoint_schema():
    """Verifies request and response DTO validation for the feedback score endpoint."""
    req = FeedbackScoreRequest(
        trace_id="tr-100",
        name="correctness",
        value=1.0,
        comment="Exact match with manual inspection note",
        user_id="U-201"
    )
    assert req.trace_id == "tr-100"
    assert req.value == 1.0

    resp = FeedbackScoreResponse(
        success=True,
        trace_id="tr-100",
        message="Score successfully recorded in Langfuse."
    )
    assert resp.success is True


@pytest.mark.asyncio
async def test_invoke_copilot_trace_integration():
    """Verifies that invoke_copilot executes and returns trace_id alongside narrative and citations."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {
        "user_id": "U-201",
        "name": "Michael Turner",
        "role": "Production Engineer",
        "team_id": "T-NORTH",
        "area_id": "AREA-NORTH"
    }
    mock_conn.fetch.return_value = []
    mock_conn.close = AsyncMock()

    mock_llm_response = {
        "model_used": "openrouter/google/gemma-4-26b-a4b-it",
        "content": '{"narrative": "Well WELL-0042 is operating nominally with 3.2 bar pressure.", "citations": [], "generative_ui": null}',
        "tool_calls": []
    }

    mock_handler = MagicMock()
    mock_handler.last_trace_id = "trace-e2e-12345"

    with patch("src.db.connection.get_raw_asyncpg_connection", return_value=mock_conn):
        with patch("src.agent.graph.get_raw_asyncpg_connection", return_value=mock_conn):
            with patch("src.agent.llm.call_llm", return_value=mock_llm_response):
                with patch("src.agent.graph.call_llm", return_value=mock_llm_response):
                    with patch("src.observability.langfuse_tracer.get_langfuse_callback_handler", return_value=mock_handler):
                        from src.agent.graph import invoke_copilot
                        result = await invoke_copilot(
                            user_query="Status of WELL-0042",
                            user_id="U-201",
                            session_id="session-trace-test"
                        )

                        assert "WELL-0042" in result["narrative"]
                        assert result["user_id"] == "U-201"
                        assert result["session_id"] == "session-trace-test"
                        assert result["trace_id"] == "trace-e2e-12345"
