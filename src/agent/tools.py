"""Autonomous Agent Tool Registry and Execution Engine.
Provides schema-safe SQL execution, analytical domain tools, vector search,
shared context overrides, and sensor conflict detection.
"""

import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
import asyncpg

from src.agent.prompts import SCHEMA_INFO_PROMPT
from src.analytics.domain_queries import (
    get_well_current_status,
    get_area_non_producing_wells,
    get_area_recently_corrected_wells,
    get_well_temperature_trend,
    get_well_spills_history,
    calculate_well_downtime_days,
    rank_area_downtime,
    get_area_recent_spills_geospatial,
    aggregate_spills_matrix,
    get_system_current_date,
)
from src.analytics.compliance_queries import (
    get_well_compliance_status,
    get_area_uncontained_spills,
)
from src.retrieval.hybrid_search import search_documents
from src.memory.shared_context import (
    apply_raw_data_correction,
    apply_ai_estimate_correction,
    apply_policy_override,
    record_shared_context_note,
    get_reportable_spills,
)
from src.analytics.conflict_detector import (
    evaluate_claim_against_sensors,
    evaluate_spill_detection_disagreement,
)


def _serialize_row_val(v: Any) -> Any:
    """Serializes date/time and numeric objects to JSON-friendly primitives."""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


# ---------------------------------------------------------------------------
# Tool Declarations (OpenAI / LiteLLM function calling format)
# ---------------------------------------------------------------------------

AGENT_TOOLS_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_schema_info",
            "description": "Returns the complete database schema including table names, columns, and foreign keys.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_custom_sql",
            "description": "Executes a strictly read-only SQL SELECT query against the PostgreSQL database. Use this for novel, ad-hoc, or custom analytical questions. Only SELECT statements are permitted.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A valid PostgreSQL SELECT query. Must start with SELECT or WITH."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_well_current_status",
            "description": "Retrieves the current physical operational status of a specific well, calculating delta_T against well-type thermal thresholds and surfacing active context notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": "Well identifier (e.g. WELL-0001)."
                    }
                },
                "required": ["asset_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_area_non_producing_wells",
            "description": "Finds all wells in a designated area that are currently non-producing based on their latest thermal inspection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "area_id": {
                        "type": "string",
                        "description": "Area identifier (e.g. AREA-01)."
                    }
                },
                "required": ["area_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_well_temperature_trend",
            "description": "Retrieves historical temperature inspections for a well to inspect thermal trends and production stability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": "Well identifier (e.g. WELL-0001)."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of recent inspections to fetch (default: 52)."
                    }
                },
                "required": ["asset_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_well_downtime",
            "description": "Calculates downtime days for a specific well using weekly inspection telemetry. Can specify calendar year (e.g. year=2025), explicit date range (start_date, end_date), or lookback window (days, default 365).",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": "Well identifier (e.g. WELL-0001)."
                    },
                    "year": {
                        "type": "integer",
                        "description": "Specific calendar year to calculate downtime for (e.g. 2025 or 2026)."
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format."
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format."
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days in lookback window (default: 365, used when year/dates not specified)."
                    }
                },
                "required": ["asset_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rank_area_downtime",
            "description": "Ranks wells in an area by total downtime days over a designated lookback window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "area_id": {
                        "type": "string",
                        "description": "Area identifier or name (e.g. 'NE-07', 'Northeast Block 7', 'SW-23', 'SW-24')."
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days in lookback window (default: 120 days / 4 months)."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of top wells to return (default: 3)."
                    }
                },
                "required": ["area_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_well_spills_history",
            "description": "Retrieves verified spill incidents for a well, filtering out false positives.",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": "Well identifier (e.g. WELL-0001)."
                    }
                },
                "required": ["asset_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_area_recent_spills_geospatial",
            "description": "Retrieves verified spill incidents across an area within a lookback period with geospatial surface coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "area_id": {
                        "type": "string",
                        "description": "Area identifier (e.g. AREA-01)."
                    },
                    "days": {
                        "type": "integer",
                        "description": "Lookback days (default: 90)."
                    }
                },
                "required": ["area_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "aggregate_spills_matrix",
            "description": "Computes a monthly aggregation matrix of spill incidents and volumes across all operating areas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "Year to aggregate (e.g. 2026)."
                    }
                },
                "required": ["year"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_well_compliance_status",
            "description": "Evaluates regulatory compliance for a well over the trailing 12-month window against safety, environmental (SR-01, SR-02, SR-03), and mechanical integrity rules (RC-04, pending RCA, RC-02 flowline test).",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": "Well identifier (e.g. WELL-0001)."
                    }
                },
                "required": ["asset_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_area_uncontained_spills",
            "description": "Identifies all spill containment events in a designated area over the past N days where containment exceeded the SLA limit (4.0 hours per SR-02).",
            "parameters": {
                "type": "object",
                "properties": {
                    "area_identifier": {
                        "type": "string",
                        "description": "Area identifier or name (e.g. 'AREA-01', 'SW-24', or 'North Shallows')."
                    },
                    "days": {
                        "type": "integer",
                        "description": "Lookback days (default: 90)."
                    }
                },
                "required": ["area_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Performs hybrid semantic and keyword retrieval over SOPs, well-type manuals, and maintenance reports.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query describing procedures, manuals, or maintenance narratives."
                    },
                    "doc_type": {
                        "type": "string",
                        "description": "Optional filter: 'sop', 'manual', or 'maintenance_report'."
                    },
                    "asset_id": {
                        "type": "string",
                        "description": "Optional well identifier to filter maintenance reports."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of sections to return (default: 5)."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_raw_data_correction",
            "description": "Applies a human operational correction to an inspection reading (e.g. field crew re-measured wellhead temperature with a calibrated thermal gun after a faulty reading). Resolves the inspection automatically if asset_id (e.g. WELL-0164) and inspection_date/asset_id are given, preserves original values in shared_context audit records, updates the inspection record, recalculates thermal delta_T and production status, and checks for contradictions with inspector notes (e.g. 'Pump jack not moving').",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": "Well identifier (e.g. WELL-0164)."
                    },
                    "inspection_date": {
                        "type": "string",
                        "description": "Inspection date or month reference (e.g. '15 Oct' or '2026-10-15')."
                    },
                    "inspection_id": {
                        "type": "string",
                        "description": "Inspection record identifier (e.g. INS-0164-0205). Optional if asset_id is provided."
                    },
                    "corrected_wellhead_temp_c": {
                        "type": "number",
                        "description": "The corrected wellhead temperature reading in degrees Celsius (e.g. 41.0)."
                    },
                    "corrected_value": {
                        "type": "number",
                        "description": "Alternative key for the corrected reading."
                    },
                    "reason": {
                        "type": "string",
                        "description": "Explanation for the correction (e.g. 'The handheld thermal gun used in that inspection was faulty; the field crew re-measured the wellhead at 41.0 deg C')."
                    },
                    "author_user_id": {
                        "type": "string",
                        "description": "User ID submitting the correction (optional, defaults to active user)."
                    }
                },
                "required": ["reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_ai_estimate_correction",
            "description": "Applies a human correction to an AI-estimated spill volume, evaluating regulatory threshold transitions and reporting deadlines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": "Well identifier (e.g. WELL-0151)."
                    },
                    "inspection_id": {
                        "type": "string",
                        "description": "Inspection record identifier (e.g. INS-0151-0201). Optional if asset_id is provided."
                    },
                    "corrected_volume": {
                        "type": "number",
                        "description": "Corrected spill volume in barrels."
                    },
                    "corrected_volume_bbl": {
                        "type": "number",
                        "description": "Corrected spill volume in barrels."
                    },
                    "reason": {
                        "type": "string",
                        "description": "Explanation for the override."
                    },
                    "author_user_id": {
                        "type": "string",
                        "description": "User ID submitting the override (optional)."
                    }
                },
                "required": ["reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_policy_override",
            "description": "Updates or overrides an operational policy threshold (e.g. RCA trigger threshold) across an asset class.",
            "parameters": {
                "type": "object",
                "properties": {
                    "well_type": {
                        "type": "string",
                        "description": "Well type to override (e.g. 'T350')."
                    },
                    "target_id": {
                        "type": "string",
                        "description": "Target well type or fleet identifier."
                    },
                    "policy_name": {
                        "type": "string",
                        "description": "Policy parameter name (e.g. 'rca_repairs_threshold')."
                    },
                    "new_value": {
                        "type": "integer",
                        "description": "New threshold value (e.g. 2)."
                    },
                    "reason": {
                        "type": "string",
                        "description": "Operational justification for the override."
                    },
                    "author_user_id": {
                        "type": "string",
                        "description": "User ID issuing the override (optional)."
                    }
                },
                "required": ["new_value", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "record_shared_context_note",
            "description": "Records an operational observation, note, broadcast, or planned shut-in into shared context visible fleet-wide to all operators (e.g. planned workover announcements like 'FYI for everyone: WELL-0007 will be shut in from 17 Oct for a 10-day planned workover').",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_id": {
                        "type": "string",
                        "description": "Target well or asset identifier (e.g. WELL-0007)."
                    },
                    "target_id": {
                        "type": "string",
                        "description": "Alternative key for asset identifier."
                    },
                    "text": {
                        "type": "string",
                        "description": "Operational note or announcement content."
                    },
                    "note_type": {
                        "type": "string",
                        "description": "Type of note (e.g. 'planned_shut_in', 'observation', 'maintenance_plan'). Defaults to planned_shut_in if shut-in mentioned."
                    },
                    "valid_from": {
                        "type": "string",
                        "description": "Effective start date (e.g. '2026-10-17' or '17 Oct')."
                    },
                    "duration_days": {
                        "type": "integer",
                        "description": "Duration of planned event in days (e.g. 10)."
                    },
                    "author_user_id": {
                        "type": "string",
                        "description": "User ID creating the note (optional, defaults to active user)."
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_claim_conflicts",
            "description": "Evaluates whether an operator or inspector claim contradicts physical sensor records or opposing notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "well_id": {
                        "type": "string",
                        "description": "Well identifier (e.g. WELL-0175 or WELL-0001)."
                    },
                    "claimed_status": {
                        "type": "string",
                        "description": "Claimed status (e.g. 'running', 'producing', 'shut_in')."
                    },
                    "claim_date": {
                        "type": "string",
                        "description": "Optional ISO date string of the claim."
                    },
                    "claim_user_id": {
                        "type": "string",
                        "description": "Optional user ID making the claim."
                    }
                },
                "required": ["well_id", "claimed_status"]
            }
        }
    }
]


# ---------------------------------------------------------------------------
# Tool Execution Dispatcher
# ---------------------------------------------------------------------------

async def execute_tool(
    tool_name: str,
    args: Dict[str, Any],
    conn: asyncpg.Connection
) -> Dict[str, Any]:
    """
    Executes a requested tool function and returns structured results.
    Guarantees read-only safety for custom SQL and enforces error boundaries.
    Automatically tracked in Langfuse with semantic observation types (retriever, guardrail, tool).
    """
    from src.observability.langfuse_tracer import record_tool_execution

    async with record_tool_execution(tool_name, args) as tool_obs:
        try:
            res = await _execute_tool_impl(tool_name, args, conn)
            tool_obs.update(
                output=res,
                metadata={"status": "success", "is_error": "error" in res if isinstance(res, dict) else False}
            )
            return res
        except Exception as e:
            tool_obs.update(level="ERROR", status_message=str(e), output={"error": str(e)})
            return {"error": f"Execution error in tool '{tool_name}': {str(e)}"}


async def _execute_tool_impl(
    tool_name: str,
    args: Dict[str, Any],
    conn: asyncpg.Connection
) -> Dict[str, Any]:
    try:
        if tool_name == "get_schema_info":
            return {"schema": SCHEMA_INFO_PROMPT}

        elif tool_name == "execute_custom_sql":
            query = args.get("query", "").strip()
            # Enforce read-only constraint
            normalized = re.sub(r"\s+", " ", query.upper())
            if not (normalized.startswith("SELECT ") or normalized.startswith("WITH ")):
                return {
                    "error": "Security constraint violation: only SELECT and WITH statements are permitted."
                }
            forbidden_tokens = ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE ", "GRANT ", "REVOKE ", "CREATE "]
            if any(token in normalized for token in forbidden_tokens):
                return {
                    "error": "Security constraint violation: statement contains disallowed write or schema-modifying keywords."
                }

            # Execute with limit protection
            rows = await conn.fetch(query)
            max_rows = 50
            truncated = len(rows) > max_rows
            serialized_rows = []
            for row in rows[:max_rows]:
                serialized_rows.append({k: _serialize_row_val(v) for k, v in dict(row).items()})

            columns = list(rows[0].keys()) if rows else []
            return {
                "row_count": len(rows),
                "columns": columns,
                "rows": serialized_rows,
                "truncated": truncated
            }

        elif tool_name == "get_well_current_status":
            asset_id = args["asset_id"]
            res = await get_well_current_status(conn, asset_id)
            return res or {"error": f"Well {asset_id} not found."}

        elif tool_name == "get_area_non_producing_wells":
            area_id = args["area_id"]
            wells = await get_area_non_producing_wells(conn, area_id)
            recent_corrections = await get_area_recently_corrected_wells(conn, area_id)
            return {
                "area_id": area_id, 
                "non_producing_wells": wells, 
                "count": len(wells),
                "recently_corrected_to_producing": recent_corrections
            }

        elif tool_name == "get_well_temperature_trend":
            asset_id = args["asset_id"]
            weeks = args.get("weeks") or args.get("limit") or 13
            trend = await get_well_temperature_trend(conn, asset_id, weeks=int(weeks))
            return {"asset_id": asset_id, "records": trend, "count": len(trend)}

        elif tool_name == "calculate_well_downtime":
            asset_id = args["asset_id"]
            year = args.get("year")
            start_date_str = args.get("start_date")
            end_date_str = args.get("end_date")
            if year:
                y = int(year)
                start_date = date(y, 1, 1)
                end_date = date(y, 12, 31)
            elif start_date_str and end_date_str:
                from datetime import datetime
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            else:
                days = int(args.get("days", 365))
                end_date = await get_system_current_date(conn)
                start_date = end_date - timedelta(days=days)
            res = await calculate_well_downtime_days(conn, asset_id, start_date=start_date, end_date=end_date)
            return res

        elif tool_name == "rank_area_downtime":
            area_id = args.get("area_id") or args.get("area_identifier", "")
            days = int(args.get("days", 120))
            limit = int(args.get("limit", 3))
            ranking = await rank_area_downtime(conn, area_identifier=area_id, days=days, limit=limit)
            return {"area_id": area_id, "ranking": ranking}

        elif tool_name == "get_well_spills_history":
            asset_id = args["asset_id"]
            spills_res = await get_well_spills_history(conn, asset_id)
            return spills_res

        elif tool_name == "get_area_recent_spills_geospatial":
            area_id = args["area_id"]
            days = int(args.get("days", 90))
            spills = await get_area_recent_spills_geospatial(conn, area_identifier=area_id, days=days)
            return {"area_id": area_id, "spills": spills, "count": len(spills)}

        elif tool_name == "aggregate_spills_matrix":
            year = args.get("year", 2026)
            result = await aggregate_spills_matrix(conn, year=year)
            # result = { year, max_month, rows: [...] }
            return {"year": year, "matrix": result}

        elif tool_name == "get_well_compliance_status":
            asset_id = args["asset_id"]
            report = await get_well_compliance_status(conn, asset_id)
            return report or {"asset_id": asset_id, "breaches": []}

        elif tool_name == "get_area_uncontained_spills":
            area_id = args["area_identifier"]
            days = args.get("days", 90)
            breaches = await get_area_uncontained_spills(conn, area_identifier=area_id, days=days)
            return {"area_identifier": area_id, "days": days, "breaches": breaches, "count": len(breaches)}

        elif tool_name == "search_knowledge_base":
            query = args["query"]
            doc_type = args.get("doc_type")
            asset_id = args.get("asset_id")
            limit = args.get("limit", 5)
            results = await search_documents(
                conn,
                query=query,
                asset_id=asset_id,
                doc_type=doc_type,
                limit=limit
            )
            return {"query": query, "results": results, "count": len(results)}

        elif tool_name == "apply_raw_data_correction":
            res = await apply_raw_data_correction(
                conn,
                author_user_id=args.get("author_user_id"),
                inspection_id=args.get("inspection_id"),
                asset_id=args.get("asset_id"),
                inspection_date=args.get("inspection_date") or args.get("date"),
                corrected_wellhead_temp_c=args.get("corrected_wellhead_temp_c"),
                corrected_value=args.get("corrected_value"),
                field_name=args.get("field_name"),
                reason=args.get("reason", "")
            )
            return res

        elif tool_name == "apply_ai_estimate_correction":
            res = await apply_ai_estimate_correction(
                conn,
                author_user_id=args.get("author_user_id"),
                inspection_id=args.get("inspection_id"),
                asset_id=args.get("asset_id"),
                inspection_date=args.get("inspection_date"),
                corrected_volume_bbl=args.get("corrected_volume_bbl") or args.get("corrected_volume"),
                reason=args.get("reason", "")
            )
            return res

        elif tool_name == "apply_policy_override":
            res = await apply_policy_override(
                conn,
                author_user_id=args.get("author_user_id"),
                target_id=args.get("target_id"),
                well_type=args.get("well_type"),
                policy_name=args.get("policy_name") or args.get("policy_key"),
                new_value=args.get("new_value"),
                reason=args.get("reason", "")
            )
            return res

        elif tool_name == "record_shared_context_note":
            res = await record_shared_context_note(
                conn,
                author_user_id=args.get("author_user_id"),
                target_id=args.get("target_id") or args.get("asset_id"),
                asset_id=args.get("asset_id") or args.get("target_id"),
                note_type=args.get("note_type"),
                text=args.get("text") or args.get("note"),
                valid_from=args.get("valid_from"),
                valid_to=args.get("valid_to"),
                duration_days=args.get("duration_days")
            )
            return res

        elif tool_name == "check_claim_conflicts":
            res = await evaluate_claim_against_sensors(
                conn,
                well_id=args["well_id"],
                claimed_status=args["claimed_status"],
                claim_date=args.get("claim_date"),
                claim_user_id=args.get("claim_user_id")
            )
            return res

        else:
            return {"error": f"Tool '{tool_name}' is not recognized."}

    except Exception as e:
        return {"error": f"Execution error in tool '{tool_name}': {str(e)}"}
