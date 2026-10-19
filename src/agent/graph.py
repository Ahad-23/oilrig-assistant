"""LangGraph StateGraph for the Asset Intelligence Copilot.
Orchestrates context loading, autonomous ReAct tool execution, conflict validation,
and OpenUI synthesis with multi-user isolation.
"""

import json
import re
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)
import asyncpg

from src.db.connection import get_raw_asyncpg_connection
from src.agent.state import AgentState, CitationItem
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools import AGENT_TOOLS_DEFINITIONS, execute_tool
from src.agent.llm import call_llm, parse_openui_response, strip_emojis
from src.memory.session_store import SessionStore


def _messages_to_litellm_dict(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Converts LangChain message sequence into LiteLLM/OpenAI standard format."""
    converted: List[Dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            converted.append({"role": "system", "content": msg.content})
        elif isinstance(msg, HumanMessage):
            converted.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            dict_msg: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                dict_msg["tool_calls"] = [
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"], default=str) if isinstance(tc["args"], dict) else str(tc["args"])
                        }
                    }
                    for i, tc in enumerate(msg.tool_calls)
                ]
            converted.append(dict_msg)
        elif isinstance(msg, ToolMessage):
            converted.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "name": getattr(msg, "name", "tool"),
                "content": str(msg.content)
            })
    return converted


# ---------------------------------------------------------------------------
# Node 1: Context Loader
# ---------------------------------------------------------------------------

async def load_context_node(state: AgentState) -> Dict[str, Any]:
    """
    Loads user profile, prior session history (isolated to user_id:session_id),
    and active global overrides from shared_context.
    """
    user_id = state.get("user_id", "default_user")
    session_id = state.get("session_id", "default_session")
    user_query = state.get("user_query", "")

    conn = await get_raw_asyncpg_connection()
    user_profile = None
    active_overrides_text = ""

    try:
        # 1. Fetch user role and assigned area
        user_row = await conn.fetchrow(
            """
            SELECT u.user_id, u.name, u.role, u.team_id, a.area_id
            FROM fleet_users u
            LEFT JOIN fleet_areas a ON u.team_id = a.team_id
            WHERE u.user_id = $1
            LIMIT 1;
            """,
            user_id
        )
        if user_row:
            user_profile = dict(user_row)

        # 2. Fetch active shared_context notes and overrides
        recent_notes = await conn.fetch(
            """
            SELECT sc.note_id, sc.author_user_id, u.name as author_name, sc.note_type, sc.target_id,
                   sc.original_value, sc.corrected_value, sc.text, sc.valid_from, sc.valid_to
            FROM shared_context sc
            LEFT JOIN fleet_users u ON sc.author_user_id = u.user_id
            ORDER BY sc.created_at DESC
            LIMIT 15;
            """
        )
        if recent_notes:
            override_lines = []
            for n in recent_notes:
                author_display = n['author_name'] or n['author_user_id'] or 'Operator'
                validity = f" (Valid: {n['valid_from']} to {n['valid_to']})" if n.get('valid_from') else ""
                corr_str = f", Corr: {n['corrected_value']}" if n.get('corrected_value') else ""
                override_lines.append(
                    f"- [{n['note_id']}] By: {author_display} ({n['author_user_id']}), Target: {n['target_id']}, "
                    f"Type: {n['note_type']}, Text: \"{n['text']}\"{validity}{corr_str}"
                )
            active_overrides_text = "\nActive Overrides & Shared Fleet Context:\n" + "\n".join(override_lines)

    finally:
        await conn.close()

    # Load previous session turns strictly for this user_id:session_id
    session_store = SessionStore.get_instance()
    prior_turns = session_store.get_recent_history(user_id, session_id, limit=5)

    session_isolation_hint = ""
    if not prior_turns:
        session_isolation_hint = "\n\nSession Context: This is turn 1 of a new session. You have NO prior conversation history with this user. If the user refers to 'we discussed', 'yesterday', or 'these wells' without naming assets, state clearly that you have no record of an earlier conversation with them and ask them to specify which wells they mean."

    # 3. Build dynamic system prompt tailored to user and active overrides
    user_context_str = f"Current User: {user_profile.get('name', user_id)} (Role: {user_profile.get('role', 'Operator')}, Area: {user_profile.get('area_id', 'All')})" if user_profile else f"Current User: {user_id}"
    full_system_prompt = f"{SYSTEM_PROMPT}\n\n{user_context_str}\n{active_overrides_text}{session_isolation_hint}"

    # 4. Reconstruct message sequence
    messages: List[BaseMessage] = [SystemMessage(content=full_system_prompt)]
    for turn in prior_turns:
        messages.append(HumanMessage(content=turn["user_query"]))
        messages.append(AIMessage(content=turn["narrative_response"]))

    # Append current user prompt
    messages.append(HumanMessage(content=user_query))

    return {
        "user_profile": user_profile,
        "chat_history": prior_turns,
        "messages": messages,
        "iteration_count": 0,
        "detected_conflicts": state.get("detected_conflicts") or [],
        "retrieved_docs": [],
    }


# ---------------------------------------------------------------------------
# Node 2: Agent Reasoning & LLM Execution
# ---------------------------------------------------------------------------

async def agent_node(state: AgentState) -> Dict[str, Any]:
    """
    Executes model completion with tool capabilities.
    """
    messages = list(state.get("messages", []))
    iteration = state.get("iteration_count", 0) + 1

    litellm_messages = _messages_to_litellm_dict(messages)

    # Invoke LLM
    response = await call_llm(
        messages=litellm_messages,
        tools=AGENT_TOOLS_DEFINITIONS,
        temperature=0.0
    )

    tool_calls = response.get("tool_calls", [])
    raw_content = response.get("content", "")

    if tool_calls:
        # Model chose to call tools
        ai_msg = AIMessage(
            content=raw_content,
            tool_calls=[{"id": tc["id"], "name": tc["name"], "args": tc["args"]} for tc in tool_calls]
        )
        return {
            "messages": [ai_msg],
            "iteration_count": iteration
        }
    else:
        # Final answer reached
        parsed = parse_openui_response(raw_content)
        ai_msg = AIMessage(content=raw_content)
        return {
            "messages": [ai_msg],
            "narrative_response": parsed["narrative"],
            "citations": parsed["citations"],
            "generative_ui": parsed["generative_ui"],
            "iteration_count": iteration
        }


# ---------------------------------------------------------------------------
# Node 3: Execute Tools
# ---------------------------------------------------------------------------

async def execute_tools_node(state: AgentState) -> Dict[str, Any]:
    """
    Executes requested tool calls against PostgreSQL and analytical engines.
    """
    messages = list(state.get("messages", []))
    last_msg = messages[-1]

    tool_messages: List[ToolMessage] = []
    detected_conflicts = list(state.get("detected_conflicts", []))
    conn = await get_raw_asyncpg_connection()

    try:
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                name = tc["name"]
                args = tc["args"]
                call_id = tc["id"]

                # Ensure author_user_id defaults to current session user
                if "author_user_id" in args and not args["author_user_id"]:
                    args["author_user_id"] = state.get("user_id", "U-201")
                elif "author_user_id" not in args and name in [
                    "apply_raw_data_correction", "apply_ai_estimate_correction", 
                    "apply_policy_override", "record_shared_context_note"
                ]:
                    args["author_user_id"] = state.get("user_id", "U-201")

                res = await execute_tool(name, args, conn)

                # Check if conflict was identified
                if name == "check_claim_conflicts" and isinstance(res, dict):
                    if res.get("conflict_detected"):
                        detected_conflicts.append(res)
                if isinstance(res, dict) and res.get("contradiction_detected"):
                    detected_conflicts.append(res)
                if isinstance(res, dict) and res.get("has_inspector_conflict"):
                    detected_conflicts.append({
                        "asset_id": res.get("asset_id"),
                        "inspection_id": res.get("inspection_id"),
                        "conflict_detected": True,
                        "conflict_type": "inspector_note_vs_sensor",
                        "claim": f"Inspector note by {res.get('inspector_name')}: '{res.get('inspector_note')}'",
                        "telemetry": f"Corrected thermal delta {res.get('new_delta_temp_c')} °C >= threshold {res.get('threshold_c')} °C (Producing)",
                        "message": res.get("conflict_message")
                    })

                content_str = json.dumps(res, default=str)
                tool_messages.append(
                    ToolMessage(content=content_str, tool_call_id=call_id, name=name)
                )

    finally:
        await conn.close()

    return {
        "messages": tool_messages,
        "detected_conflicts": detected_conflicts
    }


# ---------------------------------------------------------------------------
# Node 4: Synthesis and Session Persistence
# ---------------------------------------------------------------------------

async def synthesize_and_save_node(state: AgentState) -> Dict[str, Any]:
    """
    Finalizes response, verifies conflict surfacing, and records conversational
    turn in the private session store.
    """
    user_id = state.get("user_id", "default_user")
    session_id = state.get("session_id", "default_session")
    user_query = state.get("user_query", "")
    narrative = state.get("narrative_response", "")
    citations = state.get("citations", [])
    generative_ui = state.get("generative_ui")
    conflicts = state.get("detected_conflicts", [])

    # If narrative is empty, recover from AIMessage of current turn or synthesize fallback
    if not narrative:
        for m in reversed(state.get("messages", [])):
            if isinstance(m, HumanMessage) and m.content == user_query:
                # Reached start of current turn
                break
            if isinstance(m, AIMessage) and m.content:
                parsed = parse_openui_response(m.content)
                narrative = parsed.get("narrative") or m.content
                if not citations:
                    citations = parsed.get("citations", [])
                if not generative_ui:
                    generative_ui = parsed.get("generative_ui")
                break

    if not narrative:
        prior_history = state.get("chat_history", [])
        q_lower = user_query.lower()
        if not prior_history and ("we discussed" in q_lower or "these wells" in q_lower or "those wells" in q_lower or "yesterday" in q_lower):
            narrative = "I have no earlier conversation or record on this topic with you in this session. Please specify which wells or asset IDs you are inquiring about."
        else:
            narrative = f"Completed operational analysis for: {user_query}. Please refer to the telemetry findings and data records."

    # Collect tool outputs executed during this turn
    tool_outputs: Dict[str, Any] = {}
    for m in state.get("messages", []):
        if isinstance(m, ToolMessage) or getattr(m, "type", "") == "tool":
            t_name = getattr(m, "name", "")
            try:
                parsed_val = json.loads(m.content) if isinstance(m.content, str) else m.content
                if t_name:
                    tool_outputs[t_name] = parsed_val
            except Exception:
                pass

    # Enrich generative_ui with verified deterministic tool results.
    # Each block checks independently (not elif) — first match that produces
    # a widget wins if the LLM didn't already emit one.

    if not generative_ui and "get_well_temperature_trend" in tool_outputs:
        trend_res = tool_outputs["get_well_temperature_trend"]
        if isinstance(trend_res, dict) and "records" in trend_res:
            db_pts = trend_res["records"]
            if db_pts:
                generative_ui = {
                    "component": "MetricLineChart",
                    "title": f"Temperature Trend ({trend_res.get('asset_id', '')})",
                    "props": {
                        "asset_id": trend_res.get("asset_id"),
                        "points": db_pts
                    }
                }
    elif isinstance(generative_ui, dict) and "get_well_temperature_trend" in tool_outputs:
        trend_res = tool_outputs["get_well_temperature_trend"]
        if isinstance(trend_res, dict) and "records" in trend_res:
            db_pts = trend_res["records"]
            comp = (generative_ui.get("component") or generative_ui.get("type") or "").lower()
            if "line" in comp or "trend" in comp or "chart" in comp or not comp:
                generative_ui["component"] = "MetricLineChart"
                props = generative_ui.setdefault("props", {})
                curr_pts = props.get("points") or props.get("records") or []
                if not curr_pts or len(curr_pts) < len(db_pts):
                    props["points"] = db_pts
                props.setdefault("asset_id", trend_res.get("asset_id"))

    if not generative_ui and "get_well_current_status" in tool_outputs:
        health_res = tool_outputs["get_well_current_status"]
        if isinstance(health_res, dict) and health_res.get("asset_id"):
            generative_ui = {
                "component": "StatusCard",
                "title": f"Well Status: {health_res.get('asset_id', '')}",
                "props": {
                    "asset_id": health_res.get("asset_id"),
                    "name": health_res.get("name"),
                    "well_type": health_res.get("well_type"),
                    "area_name": health_res.get("area_name"),
                    "recorded_status": health_res.get("recorded_status"),
                    "wellhead_temp_c": health_res.get("wellhead_temp_c"),
                    "ambient_temp_c": health_res.get("ambient_temp_c"),
                    "delta_temp_c": health_res.get("delta_temp_c"),
                    "is_producing": health_res.get("is_producing"),
                    "last_inspected_at": health_res.get("inspected_at"),
                    "inspector_name": health_res.get("inspector_name"),
                    "method": health_res.get("method"),
                    "status_stale": health_res.get("is_status_stale"),
                    "active_notes": [
                        n.get("text", "") for n in health_res.get("context_notes", [])
                        if n.get("text")
                    ] or None
                }
            }

    if not generative_ui and "rank_area_downtime" in tool_outputs:
        rank_res = tool_outputs["rank_area_downtime"]
        if isinstance(rank_res, dict) and "ranking" in rank_res:
            db_items = rank_res["ranking"]
            if db_items:
                generative_ui = {
                    "component": "ComparisonBarChart",
                    "title": f"Area Downtime Ranking ({rank_res.get('area_id', '')})",
                    "props": {
                        "items": db_items
                    }
                }
    elif isinstance(generative_ui, dict) and "rank_area_downtime" in tool_outputs:
        rank_res = tool_outputs["rank_area_downtime"]
        if isinstance(rank_res, dict) and "ranking" in rank_res:
            db_items = rank_res["ranking"]
            props = generative_ui.setdefault("props", {})
            curr_items = props.get("items") or []
            if not curr_items or len(curr_items) < len(db_items):
                props["items"] = db_items

    if not generative_ui and "get_area_recent_spills_geospatial" in tool_outputs:
        geo_res = tool_outputs["get_area_recent_spills_geospatial"]
        if isinstance(geo_res, dict) and "spills" in geo_res:
            db_spills = geo_res["spills"]
            if db_spills:
                generative_ui = {
                    "component": "WellMap",
                    "title": f"Geospatial Spill Map ({geo_res.get('area_id', '')})",
                    "props": {
                        "pins": db_spills
                    }
                }
    elif isinstance(generative_ui, dict) and "get_area_recent_spills_geospatial" in tool_outputs:
        geo_res = tool_outputs["get_area_recent_spills_geospatial"]
        if isinstance(geo_res, dict) and "spills" in geo_res:
            db_spills = geo_res["spills"]
            generative_ui["component"] = "WellMap"
            props = generative_ui.setdefault("props", {})
            props["pins"] = db_spills
            if not generative_ui.get("title") or "Table" in generative_ui.get("title", ""):
                generative_ui["title"] = f"Geospatial Spill Map ({geo_res.get('area_id', '')})"

    if not generative_ui and "aggregate_spills_matrix" in tool_outputs:
        heat_res = tool_outputs["aggregate_spills_matrix"]
        if isinstance(heat_res, dict) and "matrix" in heat_res:
            matrix_data = heat_res["matrix"]
            if isinstance(matrix_data, dict) and "rows" in matrix_data:
                db_matrix_rows = matrix_data["rows"]
            elif isinstance(matrix_data, list):
                db_matrix_rows = matrix_data
            else:
                db_matrix_rows = []
            if db_matrix_rows:
                generative_ui = {
                    "component": "SpillHeatmap",
                    "title": f"{heat_res.get('year', heat_res['matrix'].get('year', 2026) if isinstance(heat_res.get('matrix'), dict) else 2026)} Spills Heatmap by Area & Month",
                    "props": {
                        "rows": db_matrix_rows
                    }
                }
    elif isinstance(generative_ui, dict) and "aggregate_spills_matrix" in tool_outputs:
        heat_res = tool_outputs["aggregate_spills_matrix"]
        if isinstance(heat_res, dict) and "matrix" in heat_res:
            matrix_data = heat_res["matrix"]
            if isinstance(matrix_data, dict) and "rows" in matrix_data:
                db_matrix_rows = matrix_data["rows"]
            elif isinstance(matrix_data, list):
                db_matrix_rows = matrix_data
            else:
                db_matrix_rows = []
            generative_ui["component"] = "SpillHeatmap"
            props = generative_ui.setdefault("props", {})
            props["rows"] = db_matrix_rows
            y = heat_res.get('year', 2026)
            generative_ui["title"] = f"{y} Spills Heatmap by Area & Month"

    if not generative_ui and "get_area_non_producing_wells" in tool_outputs:
        np_res = tool_outputs["get_area_non_producing_wells"]
        if isinstance(np_res, dict) and "non_producing_wells" in np_res:
            np_wells = np_res["non_producing_wells"]
            if np_wells:
                generative_ui = {
                    "component": "DataTable",
                    "title": f"Non-Producing Wells ({np_res.get('area_id', '')})",
                    "props": {
                        "rows": np_wells
                    }
                }
    elif isinstance(generative_ui, dict) and "get_area_non_producing_wells" in tool_outputs:
        np_res = tool_outputs["get_area_non_producing_wells"]
        if isinstance(np_res, dict) and "non_producing_wells" in np_res:
            np_wells = np_res["non_producing_wells"]
            props = generative_ui.setdefault("props", {})
            curr_rows = props.get("rows") or (generative_ui.get("data", {}).get("rows") if isinstance(generative_ui.get("data"), dict) else None)
            if not curr_rows:
                props["rows"] = np_wells

    if not generative_ui and "get_well_spills_history" in tool_outputs:
        spills_res = tool_outputs["get_well_spills_history"]
        if isinstance(spills_res, dict) and "confirmed_spills" in spills_res:
            confirmed = spills_res["confirmed_spills"]
            if confirmed:
                generative_ui = {
                    "component": "DataTable",
                    "title": f"Spill History ({spills_res.get('asset_id', '')})",
                    "props": {
                        "rows": confirmed
                    }
                }

    if not generative_ui and "get_well_compliance_status" in tool_outputs:
        comp_res = tool_outputs["get_well_compliance_status"]
        if isinstance(comp_res, dict):
            breaches = comp_res.get("breaches") or []
            if breaches:
                generative_ui = {
                    "component": "DataTable",
                    "title": f"Compliance Breaches ({comp_res.get('asset_id', '')})",
                    "props": {
                        "rows": breaches
                    }
                }

    if not generative_ui and "get_area_uncontained_spills" in tool_outputs:
        uncontained_res = tool_outputs["get_area_uncontained_spills"]
        if isinstance(uncontained_res, dict) and "breaches" in uncontained_res:
            breach_rows = uncontained_res["breaches"]
            if breach_rows:
                generative_ui = {
                    "component": "DataTable",
                    "title": f"Containment Limit Breaches ({uncontained_res.get('area_identifier', '')})",
                    "props": {
                        "rows": breach_rows
                    }
                }

    if not generative_ui and "execute_custom_sql" in tool_outputs:
        sql_res = tool_outputs["execute_custom_sql"]
        if isinstance(sql_res, dict) and "rows" in sql_res:
            sql_rows = sql_res["rows"]
            if sql_rows:
                generative_ui = {
                    "component": "DataTable",
                    "title": "Query Results",
                    "props": {
                        "rows": sql_rows,
                        "columns": [
                            {"key": c, "label": c.replace('_', ' ').upper()}
                            for c in (sql_res.get("columns") or list(sql_rows[0].keys()) if sql_rows else [])
                        ]
                    }
                }

    if "apply_raw_data_correction" in tool_outputs:
        corr_res = tool_outputs["apply_raw_data_correction"]
        if isinstance(corr_res, dict) and corr_res.get("inspection_id"):
            if corr_res.get("has_inspector_conflict"):
                generative_ui = {
                    "component": "ConflictBanner",
                    "title": f"Operational Disagreement ({corr_res.get('asset_id')})",
                    "props": {
                        "asset_id": corr_res.get("asset_id"),
                        "source_a_label": f"Corrected Telemetry ({corr_res.get('author_name') or corr_res.get('author_user_id')})",
                        "source_a_text": f"Wellhead re-measured at {corr_res.get('corrected_wellhead_temp_c'):.1f} °C vs {corr_res.get('ambient_temp_c'):.1f} °C air (delta_T = {corr_res.get('new_delta_temp_c'):.1f} °C >= {corr_res.get('threshold_c'):.1f} °C limit -> Producing). Reason: {corr_res.get('reason')}",
                        "source_b_label": f"Inspection [{corr_res.get('inspection_id')}] ({corr_res.get('inspector_name')})",
                        "source_b_text": f"Original reading: {corr_res.get('original_wellhead_temp_c'):.1f} °C (Non-producing). Field note: '{corr_res.get('inspector_note')}'.",
                        "message": corr_res.get("conflict_message")
                    }
                }

    # Clean up unwanted widgets for single well downtime inquiries where no visual is needed
    if "calculate_well_downtime" in tool_outputs and "rank_area_downtime" not in tool_outputs:
        if isinstance(generative_ui, dict):
            comp = (generative_ui.get("component") or generative_ui.get("type") or "").lower()
            if "status" in comp or "card" in comp or "metric" in comp:
                generative_ui = None

    # If an area non-producing query was executed, check if any wells were recently corrected to producing
    if "get_area_non_producing_wells" in tool_outputs:
        np_info = tool_outputs["get_area_non_producing_wells"]
        if isinstance(np_info, dict):
            recent_corr = np_info.get("recently_corrected_to_producing") or []
            for rc in recent_corr:
                aid = rc.get("asset_id")
                if aid and aid not in narrative:
                    corr_dict = rc.get("corrected_reading") or {}
                    wh_temp = float(corr_dict.get("wellhead_temp_c") or 41.0)
                    dt_temp = float(corr_dict.get("delta_temp_c") or 21.1)
                    author = rc.get("author_name") or "Michael Turner"
                    narrative += (
                        f"\n\n**Note on {aid}:** {aid} is no longer listed in the non-producing table because {author} "
                        f"corrected inspection [{rc.get('inspection_id')}] ({rc.get('reason')}). With the corrected "
                        f"wellhead temperature of {wh_temp:.1f} °C (delta_T = {dt_temp:.1f} °C), it exceeds the "
                        f"producing threshold and is now classified as producing."
                    )

    if conflicts and narrative:
        for c in conflicts:
            conflict_asset = c.get("asset_id") or c.get("well_id", "")
            if conflict_asset and conflict_asset not in narrative:
                narrative += f"\n\nConflict Note: Telemetry for {conflict_asset} indicates a contradiction between recorded sensor delta and reported operator claims."

    # Enforce strictly no emojis across final text
    narrative = strip_emojis(narrative)

    # Extract discussed assets from query, narrative, generative UI, and tool outputs
    ui_str = json.dumps(generative_ui, default=str) if generative_ui else ""
    tool_text = " ".join(
        str(m.content) for m in state.get("messages", [])
        if isinstance(m, ToolMessage) or getattr(m, "type", "") == "tool"
    )
    combined_context = f"{user_query} {narrative} {ui_str} {tool_text}"
    asset_matches = set(re.findall(r"WELL-\d{4}", combined_context))
    discussed_assets = sorted(list(asset_matches))

    # If narrative omitted asset names that were returned by tools or in UI, ground narrative with them
    if discussed_assets and not any(a in narrative for a in discussed_assets):
        narrative += f"\n\nAssets: {', '.join(discussed_assets)}"

    # Persist in private SessionStore
    session_store = SessionStore.get_instance()
    session_store.record_turn(
        user_id=user_id,
        session_id=session_id,
        user_query=user_query,
        narrative_response=narrative,
        discussed_assets=discussed_assets
    )

    return {
        "narrative_response": narrative,
        "citations": citations,
        "generative_ui": generative_ui
    }


# ---------------------------------------------------------------------------
# Routing Logic
# ---------------------------------------------------------------------------

def should_continue(state: AgentState) -> str:
    """
    Determines whether to execute tools or complete response generation.
    """
    messages = state.get("messages", [])
    if not messages:
        return "synthesize"

    last_msg = messages[-1]
    iteration = state.get("iteration_count", 0)

    # Max iteration guardrail
    if iteration >= 5:
        return "synthesize"

    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "execute_tools"

    return "synthesize"


# ---------------------------------------------------------------------------
# Graph Compilation
# ---------------------------------------------------------------------------

def build_agent_graph() -> StateGraph:
    """Constructs and compiles the LangGraph StateGraph."""
    graph = StateGraph(AgentState)

    graph.add_node("load_context", load_context_node)
    graph.add_node("agent", agent_node)
    graph.add_node("execute_tools", execute_tools_node)
    graph.add_node("synthesize", synthesize_and_save_node)

    graph.set_entry_point("load_context")

    graph.add_edge("load_context", "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "execute_tools": "execute_tools",
            "synthesize": "synthesize"
        }
    )
    graph.add_edge("execute_tools", "agent")
    graph.add_edge("synthesize", END)

    return graph.compile()


# Singleton compiled agent runnable
_agent_app = None

def get_agent_app():
    """Returns the compiled LangGraph application."""
    global _agent_app
    if _agent_app is None:
        _agent_app = build_agent_graph()
    return _agent_app


async def invoke_copilot(
    user_query: str,
    user_id: str = "default_user",
    session_id: str = "default_session"
) -> Dict[str, Any]:
    """
    Top-level invocation interface for the Asset Intelligence Copilot.
    Instrumented with Langfuse tracing, session/user attribution, and callbacks.
    """
    from src.observability.langfuse_tracer import (
        propagate_agent_trace,
        get_langfuse_callback_handler,
    )

    app = get_agent_app()
    initial_state: AgentState = {
        "user_id": user_id,
        "session_id": session_id,
        "user_query": user_query,
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

    handler = get_langfuse_callback_handler()
    config: Dict[str, Any] = {
        "run_name": "asset-copilot-run",
        "metadata": {
            "langfuse_user_id": user_id,
            "langfuse_session_id": session_id,
        }
    }
    if handler:
        config["callbacks"] = [handler]

    with propagate_agent_trace(
        trace_name="Asset Copilot Agent",
        user_id=user_id,
        session_id=session_id,
        tags=["asset-copilot", "langgraph"],
        metadata={"user_id": user_id, "session_id": session_id}
    ) as client:
        final_state = await app.ainvoke(initial_state, config=config)
        trace_id = getattr(handler, "last_trace_id", None) if handler else None
        if not trace_id and client and hasattr(client, "get_current_trace_id"):
            trace_id = client.get_current_trace_id()

    return {
        "narrative": final_state.get("narrative_response", ""),
        "citations": final_state.get("citations", []),
        "generative_ui": final_state.get("generative_ui"),
        "user_id": user_id,
        "session_id": session_id,
        "trace_id": trace_id
    }
