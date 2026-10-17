"""State definition for LangGraph Autonomous Agent.
Strictly adheres to typed schemas, OpenUI specification, and multi-user isolation.
"""

from typing import TypedDict, List, Dict, Any, Optional, Sequence, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class CitationItem(TypedDict, total=False):
    """Verifiable source citation item."""
    id: str
    source_type: str  # 'inspection' | 'maintenance' | 'sop' | 'manual' | 'report' | 'shared_context'
    reference: str
    snippet: Optional[str]


class OpenUIWidget(TypedDict, total=False):
    """Specification for generative UI component conforming to OpenUI standards."""
    type: str  # 'metric_card' | 'table' | 'alert_banner' | 'diff_view' | 'timeline'
    title: str
    data: Any
    actions: Optional[List[Dict[str, Any]]]


class AgentState(TypedDict, total=False):
    """State passed through the LangGraph execution DAG."""
    # Identification and session context
    user_id: str
    session_id: str
    user_query: str
    user_profile: Optional[Dict[str, Any]]

    # Conversation history and LangGraph message sequence
    chat_history: List[Dict[str, Any]]
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Retrieval and execution context
    retrieved_docs: List[Dict[str, Any]]
    sql_results: Optional[Dict[str, Any]]
    detected_conflicts: List[Dict[str, Any]]

    # Final synthesized output conforming to OpenUI contract
    citations: List[CitationItem]
    narrative_response: str
    generative_ui: Optional[Dict[str, Any]]

    # Execution metadata
    iteration_count: int
    error: Optional[str]
