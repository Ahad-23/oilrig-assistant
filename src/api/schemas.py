"""Pydantic schemas and data transfer objects for the FastAPI application layer.
Strict type hinting and validation conforming to OpenUI and domain rules.
"""

from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = Field(..., description="Overall service status (healthy/degraded)")
    database: str = Field(..., description="PostgreSQL connection status")
    vector_store: str = Field(..., description="Document vector index status")
    primary_model: str = Field(..., description="Configured primary LLM model")


class UserOut(BaseModel):
    """User profile for the frontend user switcher."""
    user_id: str
    name: str
    role: str
    team_id: str
    team_name: Optional[str] = None
    area_id: Optional[str] = None
    area_name: Optional[str] = None


class ChatRequest(BaseModel):
    """Incoming user chat query."""
    message: str = Field(..., description="User operational query", min_length=1)
    user_id: str = Field("U-201", description="ID of the user making the query (e.g. U-201 Michael Turner)")
    session_id: str = Field("default_session", description="Session identifier for multi-turn conversational isolation")
    stream: bool = Field(False, description="Whether to stream response via Server-Sent Events (SSE)")


class Citation(BaseModel):
    """Verifiable citation item grounding an operational response."""
    id: str
    source_type: str
    reference: Optional[str] = None


class ChatResponse(BaseModel):
    """Complete copilot answer with narrative, citations, and generative UI."""
    narrative: str = Field(..., description="Natural language response adhering to domain rules")
    citations: List[Union[Citation, Dict[str, Any], str]] = Field(default_factory=list)
    generative_ui: Optional[Dict[str, Any]] = Field(None, description="OpenUI component specification and props")
    user_id: str
    session_id: str
    trace_id: Optional[str] = Field(None, description="Langfuse distributed trace identifier")


class SessionHistoryTurn(BaseModel):
    """A single turn in the private session history."""
    user_query: str
    narrative_response: str
    timestamp: str
    discussed_assets: List[str] = Field(default_factory=list)
    citations: List[Union[Citation, Dict[str, Any], str]] = Field(default_factory=list)
    generative_ui: Optional[Dict[str, Any]] = None


class FeedbackOverrideRequest(BaseModel):
    """Human feedback or override submission."""
    author_user_id: str = Field("U-201", description="User ID of the submitter")
    scope: str = Field("inspection", description="Scope: inspection | asset | well_type | fleet")
    target_id: str = Field(..., description="Target ID (e.g. INS-0164-0205, T350)")
    override_type: str = Field(..., description="Type of override (e.g. raw_temp_correction, spill_volume_ai_override, rca_repair_threshold)")
    corrected_value: Any = Field(..., description="New corrected value or rule parameter")
    original_value: Optional[Any] = Field(None, description="Original raw or estimated value")
    reason: Optional[str] = Field(None, description="Reason for the correction")


class FeedbackOverrideResponse(BaseModel):
    """Feedback submission confirmation."""
    success: bool
    note_id: str
    message: str
    override_data: Optional[Dict[str, Any]] = None


class FeedbackScoreRequest(BaseModel):
    """User feedback score submission for Langfuse observability."""
    trace_id: str = Field(..., description="Target Langfuse trace ID to attach score to")
    name: str = Field("user-feedback", description="Score name, e.g. user-feedback, correctness, clarity")
    value: Union[float, int] = Field(..., description="Numeric score value, e.g. 1.0 (positive), 0.0 (negative)")
    comment: Optional[str] = Field(None, description="Qualitative feedback comment from operator")
    user_id: Optional[str] = Field(None, description="Optional user submitting the feedback")


class FeedbackScoreResponse(BaseModel):
    """Feedback score submission confirmation."""
    success: bool
    trace_id: str
    message: str
