"""Production-grade Langfuse Observability Integration for Asset Intelligence Copilot.
Provides unified tracing for LangGraph agent workflows, LiteLLM generations,
domain analytical tools, vector retrievers, guardrails, and trace-level scoring.
"""

import contextlib
import logging
import os
import re
from typing import Dict, Any, List, Optional, Union, Generator, AsyncGenerator
from datetime import datetime

from src.config import settings

logger = logging.getLogger("asset_copilot.observability")

# Global client cache
_langfuse_client = None
_env_configured = False


def _setup_langfuse_environment() -> None:
    """Configures Langfuse credentials and host in os.environ for SDK and integrations."""
    global _env_configured
    if _env_configured:
        return

    if settings.LANGFUSE_PUBLIC_KEY:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY.strip()
    if settings.LANGFUSE_SECRET_KEY:
        os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY.strip()
    if settings.LANGFUSE_BASE_URL:
        base_url = settings.LANGFUSE_BASE_URL.strip().rstrip("/")
        os.environ["LANGFUSE_BASE_URL"] = base_url
        os.environ["LANGFUSE_HOST"] = base_url
    if settings.LANGFUSE_ENVIRONMENT:
        os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = settings.LANGFUSE_ENVIRONMENT.strip()

    _env_configured = True


def is_langfuse_active() -> bool:
    """
    Returns True if Langfuse observability is enabled in settings and API keys are present.
    Ensures safe, graceful degradation when running offline or in environments without Langfuse.
    """
    if not settings.LANGFUSE_ENABLED:
        return False
    _setup_langfuse_environment()
    has_public = bool(os.environ.get("LANGFUSE_PUBLIC_KEY") or settings.LANGFUSE_PUBLIC_KEY)
    has_secret = bool(os.environ.get("LANGFUSE_SECRET_KEY") or settings.LANGFUSE_SECRET_KEY)
    return has_public and has_secret


def get_langfuse_client():
    """Returns singleton Langfuse client if active, else None."""
    global _langfuse_client
    if not is_langfuse_active():
        return None
    if _langfuse_client is None:
        try:
            from langfuse import get_client
            _langfuse_client = get_client()
        except Exception as e:
            logger.warning(f"Failed to initialize Langfuse client: {e}")
            return None
    return _langfuse_client


def get_langfuse_callback_handler():
    """
    Returns a fresh Langfuse Langchain CallbackHandler for LangGraph / LangChain runs.
    Returns None if Langfuse is not active.
    """
    if not is_langfuse_active():
        return None
    try:
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    except Exception as e:
        logger.warning(f"Failed to create Langfuse CallbackHandler: {e}")
        return None


def mask_sensitive_data(payload: Any) -> Any:
    """
    Sanitizes dictionary or string payloads to prevent leaking credentials,
    passwords, or sensitive tokens in observability traces.
    """
    if isinstance(payload, dict):
        sanitized = {}
        for k, v in payload.items():
            lower_k = str(k).lower()
            if any(term in lower_k for term in ["password", "secret", "token", "api_key", "authorization"]):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = mask_sensitive_data(v)
        return sanitized
    elif isinstance(payload, list):
        return [mask_sensitive_data(item) for item in payload]
    elif isinstance(payload, str):
        # Redact Bearer tokens and connection strings if accidentally embedded
        cleaned = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]{15,}", r"\1[REDACTED]", payload)
        cleaned = re.sub(r"(postgresql(?:\+asyncpg)?://[^:]+:)([^@]+)(@)", r"\1[REDACTED]\3", cleaned)
        return cleaned
    return payload


# ---------------------------------------------------------------------------
# Dummy Fallback Observation Object
# ---------------------------------------------------------------------------

class _NoOpObservation:
    """Null-object pattern fallback when Langfuse is unconfigured or disabled."""
    def update(self, *args, **kwargs):
        pass

    def score_trace(self, *args, **kwargs):
        pass


# ---------------------------------------------------------------------------
# Trace Context Managers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def propagate_agent_trace(
    trace_name: str = "Asset Copilot Agent",
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Context manager that establishes trace-level attributes (user, session, tags, metadata)
    and propagates them across all child nodes, tools, and LLM generations in LangGraph.
    """
    if not is_langfuse_active():
        yield None
        return

    try:
        from langfuse import propagate_attributes
        default_tags = ["asset-copilot", "langgraph", "onshore-oilfield"]
        merged_tags = list(set((tags or []) + default_tags))
        clean_metadata = mask_sensitive_data(metadata or {})

        with propagate_attributes(
            trace_name=trace_name,
            user_id=user_id,
            session_id=session_id,
            tags=merged_tags,
            metadata=clean_metadata,
        ):
            yield get_langfuse_client()
    except Exception as e:
        logger.warning(f"Error propagating Langfuse attributes: {e}")
        yield None


@contextlib.asynccontextmanager
async def record_llm_generation(
    name: str,
    model: str,
    messages: List[Dict[str, Any]],
    model_parameters: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[Any, None]:
    """
    Records an LLM generation observation in Langfuse.
    Captures input prompt messages, model name, inference parameters,
    token usage details, and generation outputs.
    """
    client = get_langfuse_client()
    if client is None:
        yield _NoOpObservation()
        return

    clean_messages = mask_sensitive_data(messages)
    clean_params = model_parameters or {}

    try:
        with client.start_as_current_observation(
            name=name,
            as_type="generation",
            model=model,
            input=clean_messages,
            model_parameters=clean_params,
        ) as gen:
            yield gen
    except Exception as e:
        logger.debug(f"Langfuse generation observation error: {e}")
        yield _NoOpObservation()


@contextlib.asynccontextmanager
async def record_tool_execution(
    tool_name: str,
    args: Dict[str, Any],
) -> AsyncGenerator[Any, None]:
    """
    Records a tool execution observation in Langfuse with appropriate semantic observation type:
    - 'retriever' for vector document retrieval (e.g. search_knowledge_base)
    - 'guardrail' for safety/conflict validation (e.g. check_claim_conflicts)
    - 'tool' for all analytical queries, SQL statements, and operational adjustments
    """
    client = get_langfuse_client()
    if client is None:
        yield _NoOpObservation()
        return

    # Assign most specific observation type conforming to Langfuse best practices
    if tool_name == "search_knowledge_base":
        obs_type = "retriever"
    elif tool_name in ("check_claim_conflicts", "validate_sensor_thresholds"):
        obs_type = "guardrail"
    else:
        obs_type = "tool"

    clean_args = mask_sensitive_data(args)
    try:
        with client.start_as_current_observation(
            name=f"tool:{tool_name}",
            as_type=obs_type,
            input=clean_args,
            metadata={"tool_name": tool_name, "observation_type": obs_type}
        ) as tool_obs:
            yield tool_obs
    except Exception as e:
        logger.debug(f"Langfuse tool observation error: {e}")
        yield _NoOpObservation()


def score_agent_trace(
    trace_id: str,
    name: str = "user-feedback",
    value: Union[float, int, str] = 1.0,
    comment: Optional[str] = None,
    data_type: str = "NUMERIC",
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Attaches a quantitative or qualitative score/evaluation to an existing Langfuse trace.
    Used for operator feedback ratings, human corrections, and DeepEval evaluation runs.
    """
    client = get_langfuse_client()
    if client is None or not trace_id:
        return False

    try:
        client.create_score(
            trace_id=trace_id,
            name=name,
            value=value,
            data_type=data_type,
            comment=comment,
            metadata=mask_sensitive_data(metadata or {}),
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to create Langfuse score for trace {trace_id}: {e}")
        return False


def flush_langfuse() -> None:
    """Flushes queued observability events to Langfuse. Safe to call during shutdown or request teardown."""
    client = get_langfuse_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as e:
        logger.debug(f"Error during Langfuse flush: {e}")
