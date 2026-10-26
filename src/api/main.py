"""FastAPI application for the Asset Intelligence Copilot.
Provides REST and SSE endpoints for multi-user chat, generative UI delivery,
verifiable citations, session memory isolation, and dynamic human overrides.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional, AsyncGenerator

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from src.config import settings
from src.db.connection import get_raw_asyncpg_connection
from src.agent.graph import get_agent_app, invoke_copilot
from src.agent.state import AgentState
from src.memory.session_store import SessionStore
from src.memory.shared_context import (
    apply_raw_data_correction,
    apply_ai_estimate_correction,
    apply_policy_override,
)
from src.api.schemas import (
    HealthResponse,
    UserOut,
    ChatRequest,
    ChatResponse,
    SessionHistoryTurn,
    FeedbackOverrideRequest,
    FeedbackOverrideResponse,
    FeedbackScoreRequest,
    FeedbackScoreResponse,
)
from src.observability.langfuse_tracer import (
    is_langfuse_active,
    score_agent_trace,
    flush_langfuse,
    propagate_agent_trace,
    get_langfuse_callback_handler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verifies database connectivity, pre-compiles agent, and manages telemetry lifecycle."""
    conn = await get_raw_asyncpg_connection()
    try:
        await conn.fetchval("SELECT 1;")
    finally:
        await conn.close()
    
    # Pre-warm LangGraph singleton runnable
    get_agent_app()
    try:
        yield
    finally:
        flush_langfuse()


app = FastAPI(
    title="Asset Intelligence Copilot API",
    description="Autonomous Agentic AI Copilot for Onshore Oilfield Operations",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS to permit local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Verifies database connectivity, vector index health, and model configuration."""
    conn = await get_raw_asyncpg_connection()
    try:
        well_count = await conn.fetchval("SELECT count(*) FROM wells;")
        doc_count = await conn.fetchval("SELECT count(*) FROM document_sections;")
        
        return HealthResponse(
            status="healthy",
            database=f"connected ({well_count} wells loaded)",
            vector_store=f"ready ({doc_count} document sections indexed)",
            primary_model=settings.PRIMARY_MODEL
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database or system service unavailable: {str(e)}"
        )
    finally:
        await conn.close()


@app.get("/api/users", response_model=List[UserOut])
async def list_fleet_users() -> List[UserOut]:
    """
    Returns all fleet users with their operational team and assigned area.
    Powers the frontend multi-user role switcher.
    """
    conn = await get_raw_asyncpg_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (u.user_id)
                u.user_id,
                u.name,
                u.role,
                u.team_id,
                t.name AS team_name,
                a.area_id,
                a.name AS area_name
            FROM fleet_users u
            LEFT JOIN fleet_teams t ON u.team_id = t.team_id
            LEFT JOIN fleet_areas a ON t.team_id = a.team_id
            ORDER BY u.user_id, a.area_id;
            """
        )
        return [
            UserOut(
                user_id=r["user_id"],
                name=r["name"],
                role=r["role"],
                team_id=r["team_id"],
                team_name=r["team_name"],
                area_id=r["area_id"],
                area_name=r["area_name"]
            )
            for r in rows
        ]
    finally:
        await conn.close()


@app.get("/api/areas")
async def list_fleet_areas() -> List[Dict[str, Any]]:
    """Returns geographic areas with coordinates and active well counts."""
    conn = await get_raw_asyncpg_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT 
                a.area_id,
                a.name,
                a.team_id,
                a.center_lat,
                a.center_lon,
                COUNT(w.asset_id) AS well_count
            FROM fleet_areas a
            LEFT JOIN wells w ON a.area_id = w.area_id
            GROUP BY a.area_id, a.name, a.team_id, a.center_lat, a.center_lon
            ORDER BY a.area_id;
            """
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@app.get("/api/map-data")
async def get_map_data() -> Dict[str, Any]:
    """Returns all wells with their latest telemetry, coordinates, and real spill events."""
    conn = await get_raw_asyncpg_connection()
    try:
        # 1. Fetch wells with their latest inspection telemetry
        well_rows = await conn.fetch(
            """
            SELECT DISTINCT ON (w.asset_id)
                w.asset_id,
                w.name,
                w.well_type,
                w.area_id,
                a.name AS area_name,
                w.lat,
                w.lon,
                w.recorded_status,
                i.wellhead_temp_c,
                i.ambient_temp_c,
                i.delta_temp_c,
                i.is_producing,
                (COALESCE(i.spill_detected, FALSE) AND (i.is_false_positive_spill IS FALSE OR i.is_false_positive_spill IS NULL)) AS has_active_spill,
                i.spill_est_volume_bbl,
                i.notes AS latest_notes,
                i.inspected_at
            FROM wells w
            JOIN fleet_areas a ON w.area_id = a.area_id
            LEFT JOIN inspections i ON w.asset_id = i.asset_id
            ORDER BY w.asset_id, i.inspected_at DESC NULLS LAST;
            """
        )

        # 2. Fetch areas
        area_rows = await conn.fetch(
            """
            SELECT a.area_id, a.name, a.center_lat, a.center_lon, COUNT(w.asset_id) as well_count
            FROM fleet_areas a
            LEFT JOIN wells w ON a.area_id = w.area_id
            GROUP BY a.area_id, a.name, a.center_lat, a.center_lon
            ORDER BY a.area_id;
            """
        )

        return {
            "wells": [
                {
                    "asset_id": r["asset_id"],
                    "name": r["name"],
                    "well_type": r["well_type"],
                    "area_id": r["area_id"],
                    "area_name": r["area_name"],
                    "lat": float(r["lat"]),
                    "lon": float(r["lon"]),
                    "recorded_status": r["recorded_status"],
                    "wellhead_temp_c": round(float(r["wellhead_temp_c"]), 1) if r["wellhead_temp_c"] is not None else None,
                    "ambient_temp_c": round(float(r["ambient_temp_c"]), 1) if r["ambient_temp_c"] is not None else None,
                    "delta_temp_c": round(float(r["delta_temp_c"]), 1) if r["delta_temp_c"] is not None else None,
                    "is_producing": bool(r["is_producing"]) if r["is_producing"] is not None else True,
                    "has_active_spill": bool(r["has_active_spill"]),
                    "spill_est_volume_bbl": round(float(r["spill_est_volume_bbl"]), 1) if r["spill_est_volume_bbl"] is not None else None,
                    "latest_notes": r["latest_notes"],
                    "inspected_at": r["inspected_at"].isoformat() if r["inspected_at"] else None
                }
                for r in well_rows
            ],
            "areas": [
                {
                    "area_id": r["area_id"],
                    "name": r["name"],
                    "center_lat": float(r["center_lat"]),
                    "center_lon": float(r["center_lon"]),
                    "well_count": int(r["well_count"])
                }
                for r in area_rows
            ]
        }
    finally:
        await conn.close()


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """
    Standard synchronous chat invocation.
    Executes LangGraph agent and returns narrative, citations, OpenUI payload, and Langfuse trace ID.
    """
    try:
        result = await invoke_copilot(
            user_query=request.message,
            user_id=request.user_id,
            session_id=request.session_id
        )
        return ChatResponse(
            narrative=result.get("narrative", ""),
            citations=result.get("citations", []),
            generative_ui=result.get("generative_ui"),
            user_id=request.user_id,
            session_id=request.session_id,
            trace_id=result.get("trace_id")
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution encountered an error: {str(e)}"
        )


@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    Server-Sent Events (SSE) streaming chat endpoint.
    Emits progress status, token stream, citations, generative UI payloads, and Langfuse trace ID.
    """
    async def event_generator() -> AsyncGenerator[Dict[str, str], None]:
        app_graph = get_agent_app()
        initial_state: AgentState = {
            "user_id": request.user_id,
            "session_id": request.session_id,
            "user_query": request.message,
            "chat_history": [],
            "messages": [],
            "retrieved_docs": [],
            "sql_results": None,
            "detected_conflicts": [],
            "citations": [],
            "narrative_response": "",
            "generative_ui": None,
            "iteration_count": 0,
            "error": None
        }

        yield {
            "event": "status",
            "data": json.dumps({"step": "init", "message": "Initializing agent and loading context..."})
        }

        final_narrative = ""
        final_citations = []
        final_ui = None
        handler = get_langfuse_callback_handler()
        config: Dict[str, Any] = {
            "run_name": "asset-copilot-stream-run",
            "metadata": {
                "langfuse_user_id": request.user_id,
                "langfuse_session_id": request.session_id,
                "stream": True,
            }
        }
        if handler:
            config["callbacks"] = [handler]

        try:
            with propagate_agent_trace(
                trace_name="Asset Copilot Streaming Agent",
                user_id=request.user_id,
                session_id=request.session_id,
                tags=["asset-copilot", "langgraph", "streaming"],
                metadata={"user_id": request.user_id, "session_id": request.session_id}
            ) as client:
                async for output in app_graph.astream(initial_state, stream_mode="updates", config=config):
                    for node_name, node_output in output.items():
                        if node_name == "load_context":
                            yield {
                                "event": "status",
                                "data": json.dumps({
                                    "step": "context",
                                    "message": f"Loaded context and active overrides for user {request.user_id}."
                                })
                            }
                        elif node_name == "agent":
                            yield {
                                "event": "status",
                                "data": json.dumps({
                                    "step": "reasoning",
                                    "message": "Gemma 4 evaluated query and selected analytical actions."
                                })
                            }
                        elif node_name == "execute_tools":
                            yield {
                                "event": "status",
                                "data": json.dumps({
                                    "step": "execution",
                                    "message": "Executed deterministic domain queries and vector search."
                                })
                            }
                        elif node_name == "synthesize":
                            final_narrative = node_output.get("narrative_response", "")
                            final_citations = node_output.get("citations", [])
                            final_ui = node_output.get("generative_ui")

                trace_id = getattr(handler, "last_trace_id", None) if handler else None
                if not trace_id and client and hasattr(client, "get_current_trace_id"):
                    trace_id = client.get_current_trace_id()

            # Stream narrative tokens for typewriter UI effect
            words = final_narrative.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i:i + 3]) + (" " if i + 3 < len(words) else "")
                yield {
                    "event": "token",
                    "data": json.dumps({"token": chunk})
                }
                await asyncio.sleep(0.015)

            # Emit citations if available
            if final_citations:
                yield {
                    "event": "citations",
                    "data": json.dumps(final_citations, default=str)
                }

            # Emit generative UI payload if available
            if final_ui:
                yield {
                    "event": "generative_ui",
                    "data": json.dumps(final_ui, default=str)
                }

            # Emit final completion signal with trace_id
            yield {
                "event": "done",
                "data": json.dumps({
                    "user_id": request.user_id,
                    "session_id": request.session_id,
                    "narrative": final_narrative,
                    "trace_id": trace_id
                })
            }

        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }

    return EventSourceResponse(event_generator())


@app.get("/api/history/{user_id}/{session_id}", response_model=List[SessionHistoryTurn])
async def get_session_history(user_id: str, session_id: str) -> List[SessionHistoryTurn]:
    """Returns conversational turns isolated strictly to user_id:session_id."""
    store = SessionStore.get_instance()
    turns = store.get_recent_history(user_id, session_id, limit=30)
    return [
        SessionHistoryTurn(
            user_query=t.get("user_query", ""),
            narrative_response=t.get("narrative_response", ""),
            timestamp=t.get("timestamp", ""),
            discussed_assets=t.get("discussed_assets", [])
        )
        for t in turns
    ]


@app.post("/api/history/clear")
async def clear_session_history(user_id: str, session_id: str) -> Dict[str, Any]:
    """Clears conversation turns for a specified user and session."""
    store = SessionStore.get_instance()
    store.clear_session(user_id, session_id)
    return {"status": "cleared", "user_id": user_id, "session_id": session_id}


@app.post("/api/feedback/override", response_model=FeedbackOverrideResponse)
async def submit_feedback_override(request: FeedbackOverrideRequest) -> FeedbackOverrideResponse:
    """
    Registers a human operational correction or dynamic policy override.
    Immediately updates shared_context for fleet-wide propagation.
    """
    conn = await get_raw_asyncpg_connection()
    try:
        if request.override_type == "raw_temp_correction":
            corrected_temp = float(request.corrected_value)
            res = await apply_raw_data_correction(
                conn=conn,
                author_user_id=request.author_user_id,
                inspection_id=request.target_id,
                corrected_wellhead_temp_c=corrected_temp,
                reason=request.reason or "Field crew re-measured wellhead temperature"
            )
            return FeedbackOverrideResponse(
                success=True,
                note_id="NOTE-CORR",
                message="Raw wellhead temperature correction saved to shared_context.",
                override_data=res
            )

        elif request.override_type == "spill_volume_ai_override":
            corrected_vol = float(request.corrected_value)
            res = await apply_ai_estimate_correction(
                conn=conn,
                author_user_id=request.author_user_id,
                inspection_id=request.target_id,
                corrected_volume_bbl=corrected_vol,
                reason=request.reason or "Field measurement updated from AI image estimate"
            )
            return FeedbackOverrideResponse(
                success=True,
                note_id="NOTE-CORR",
                message="AI spill volume correction registered to shared_context.",
                override_data=res
            )

        elif request.override_type == "rca_repair_threshold":
            threshold = int(request.corrected_value)
            res = await apply_policy_override(
                conn=conn,
                author_user_id=request.author_user_id,
                scope=request.scope or "well_type",
                target_id=request.target_id,
                policy_key="rca_threshold",
                new_value=threshold,
                reason=request.reason or "Operational team policy adjustment"
            )
            return FeedbackOverrideResponse(
                success=True,
                note_id="NOTE-POLICY",
                message="Dynamic RCA threshold policy registered to shared_context.",
                override_data=res
            )

        else:
            note_id = f"NOTE-{request.author_user_id}-GEN"
            await conn.execute(
                """
                INSERT INTO shared_context (
                    author_user_id, scope, target_id, note_type,
                    original_value, corrected_value, text, is_confirmed
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, TRUE);
                """,
                request.author_user_id,
                request.scope,
                request.target_id,
                request.override_type,
                json.dumps(request.original_value, default=str) if request.original_value else None,
                json.dumps(request.corrected_value, default=str),
                request.reason or "Generic operational override"
            )
            return FeedbackOverrideResponse(
                success=True,
                note_id=note_id,
                message=f"Override {request.override_type} saved for target {request.target_id}."
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to submit feedback override: {str(e)}"
        )
    finally:
        await conn.close()


@app.get("/api/overrides")
async def list_recent_overrides() -> List[Dict[str, Any]]:
    """Returns recent active overrides and shared feedback entries."""
    conn = await get_raw_asyncpg_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT 
                override_id,
                note_id,
                created_at,
                author_user_id,
                scope,
                target_id,
                note_type,
                original_value,
                corrected_value,
                text,
                is_confirmed
            FROM shared_context
            ORDER BY created_at DESC
            LIMIT 50;
            """
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


@app.post("/api/feedback/score", response_model=FeedbackScoreResponse)
async def submit_feedback_score(request: FeedbackScoreRequest) -> FeedbackScoreResponse:
    """
    Submits user feedback or human evaluation scores directly to Langfuse.
    Enables tracking of operator satisfaction, response quality, and RLHF/eval datasets.
    """
    try:
        scored = score_agent_trace(
            trace_id=request.trace_id,
            name=request.name,
            value=request.value,
            comment=request.comment,
            metadata={"user_id": request.user_id} if request.user_id else None
        )
        if not scored and not is_langfuse_active():
            return FeedbackScoreResponse(
                success=True,
                trace_id=request.trace_id,
                message="Langfuse inactive; feedback score accepted in offline mode."
            )
        return FeedbackScoreResponse(
            success=scored,
            trace_id=request.trace_id,
            message="Score successfully recorded in Langfuse." if scored else "Failed to transmit score to Langfuse."
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to submit feedback score: {str(e)}"
        )


@app.get("/api/history/{user_id}/{session_id}", response_model=List[SessionHistoryTurn])
async def get_session_history(user_id: str, session_id: str) -> List[SessionHistoryTurn]:
    """
    Returns private conversational turns for a specific user and session.
    Enforces strict user-level and session-level isolation.
    """
    session_store = SessionStore.get_instance()
    conn = None
    try:
        conn = await get_raw_asyncpg_connection()
        raw_turns = await session_store.get_recent_history_persistent(conn, user_id, session_id, limit=50)
    except Exception:
        raw_turns = session_store.get_recent_history(user_id, session_id, limit=50)
    finally:
        if conn:
            await conn.close()

    return [
        SessionHistoryTurn(
            user_query=t.get("user_query", ""),
            narrative_response=t.get("narrative_response", ""),
            timestamp=t.get("timestamp", ""),
            discussed_assets=t.get("discussed_assets", []),
            citations=t.get("citations", []),
            generative_ui=t.get("generative_ui")
        )
        for t in raw_turns
    ]


@app.post("/api/history/clear")
async def clear_session_history(user_id: str, session_id: str) -> Dict[str, Any]:
    """Clears conversational turns for a specific user session."""
    session_store = SessionStore.get_instance()
    session_store.clear_session(user_id, session_id)
    return {"status": "cleared", "user_id": user_id, "session_id": session_id}

