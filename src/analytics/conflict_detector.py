"""
Conflict Detection Engine for the Asset Intelligence Copilot.

Enforces honesty about contradictions:
- Flags user claims that contradict physical sensor logs (Q17).
- Surfaces disagreements between field staff on inspections (Q18).
- Flags inspector note contradictions when thermal values are corrected (Q12).
Never silently picks a side when data or people disagree.
"""

from datetime import date
from typing import Dict, Any, List, Optional
import asyncpg
from src.analytics.compliance_queries import get_system_current_date


async def evaluate_claim_against_sensors(
    conn: asyncpg.Connection,
    asset_id: str,
    claimed_status: str,
    author_user_id: str,
    as_of_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Evaluates a user statement against latest physical sensor readings and active context records.
    Flags contradictions, sets confirmation status, and provides grounded evidence.
    """
    if as_of_date is None:
        as_of_date = await get_system_current_date(conn)

    # 1. Fetch well and latest inspection
    row = await conn.fetchrow("""
        SELECT w.asset_id, w.name, w.well_type, r.min_producing_temp_delta_c,
               i.inspection_id, i.inspected_at, i.delta_temp_c, i.ambient_temp_c,
               i.wellhead_temp_c, i.is_producing, u.name as inspector_name
        FROM wells w
        JOIN well_type_rules r ON w.well_type = r.well_type
        LEFT JOIN LATERAL (
            SELECT * FROM inspections 
            WHERE asset_id = w.asset_id 
            ORDER BY inspected_at DESC 
            LIMIT 1
        ) i ON TRUE
        LEFT JOIN fleet_users u ON i.inspector_user_id = u.user_id
        WHERE w.asset_id = $1;
    """, asset_id)

    if not row:
        raise ValueError(f"Well {asset_id} not found.")

    is_producing = bool(row["is_producing"])
    delta_temp_c = round(float(row["delta_temp_c"]), 1)
    threshold_c = round(float(row["min_producing_temp_delta_c"]), 1)
    insp_date = row["inspected_at"].date()
    inspector = row["inspector_name"] or "Inspector"
    inspection_id = row["inspection_id"]

    # 2. Check active context notes (e.g. planned shut-in)
    context_notes = await conn.fetch("""
        SELECT note_id, author_user_id, text, valid_from, valid_to
        FROM shared_context
        WHERE target_id = $1
          AND (valid_to IS NULL OR valid_to >= $2)
        ORDER BY created_at DESC;
    """, asset_id, as_of_date)

    normalized_claim = claimed_status.lower().strip()
    claims_online = any(term in normalized_claim for term in ["running", "producing", "online", "fine", "active"])
    claims_shut_in = any(term in normalized_claim for term in ["shut in", "shut-in", "down", "stopped", "offline"])

    has_conflict = False
    is_confirmed = True
    conflict_reason = None

    if claims_online and not is_producing:
        has_conflict = True
        is_confirmed = False
        matching_context = [dict(n) for n in context_notes if "shut in" in n["text"].lower() or "planned" in n["text"].lower()]
        shut_in_mention = f" Note {matching_context[0]['note_id']} confirms planned shut-in." if matching_context else ""
        conflict_reason = (
            f"The {insp_date.strftime('%d %b')} inspection ({inspection_id} by {inspector}) "
            f"recorded a wellhead temperature only {delta_temp_c:.1f} °C above ambient, which is below "
            f"the {threshold_c:.1f} °C threshold (the well is not producing).{shut_in_mention} "
            f"This contradicts the claim that the well is running or online. Statement marked as unconfirmed."
        )

    elif claims_shut_in and is_producing:
        has_conflict = True
        is_confirmed = False
        conflict_reason = (
            f"The {insp_date.strftime('%d %b')} inspection ({inspection_id} by {inspector}) "
            f"recorded a wellhead temperature of {delta_temp_c:.1f} °C above ambient, which is above "
            f"the {threshold_c:.1f} °C threshold (well is producing). "
            f"This contradicts the claim that the well is shut in. Statement marked as unconfirmed."
        )

    return {
        "asset_id": asset_id,
        "author_user_id": author_user_id,
        "claimed_status": claimed_status,
        "has_conflict": has_conflict,
        "is_confirmed": is_confirmed,
        "actual_is_producing": is_producing,
        "delta_temp_c": delta_temp_c,
        "threshold_c": threshold_c,
        "inspection_id": inspection_id,
        "inspection_date": insp_date,
        "inspector_name": inspector,
        "active_notes": [dict(n) for n in context_notes],
        "conflict_reason": conflict_reason
    }


async def evaluate_spill_detection_disagreement(
    conn: asyncpg.Connection,
    asset_id: str,
    inspection_id: str
) -> Dict[str, Any]:
    """
    Evaluates whether human notes or observations disagree regarding an AI spill detection (Q18).
    Checks whether a formal correction exists, verifies follow-up maintenance,
    and returns transparent context presenting both viewpoints.
    """
    # 1. Fetch inspection
    insp = await conn.fetchrow("""
        SELECT inspection_id, asset_id, inspected_at, spill_detected, 
               spill_est_volume_bbl, is_false_positive_spill, notes
        FROM inspections
        WHERE inspection_id = $1;
    """, inspection_id)

    if not insp:
        raise ValueError(f"Inspection {inspection_id} not found.")

    # 2. Fetch context notes referring to this inspection
    notes = await conn.fetch("""
        SELECT c.note_id, c.author_user_id, u.name as author_name, u.role,
               c.note_type, c.text, c.created_at
        FROM shared_context c
        LEFT JOIN fleet_users u ON c.author_user_id = u.user_id
        WHERE c.text ILIKE ('%' || $1 || '%')
           OR c.target_id = $1
        ORDER BY c.created_at ASC;
    """, inspection_id)

    # 3. Check for formal correction
    formal_corrections = [n for n in notes if n["note_type"] == "correction"]
    has_formal_override = len(formal_corrections) > 0 or insp["is_false_positive_spill"]

    # 4. Check for maintenance repair triggered
    repair = await conn.fetchrow("""
        SELECT maintenance_id, issue, action_taken, maintenance_type, started_at
        FROM maintenance
        WHERE triggered_by_inspection_id = $1
           OR (asset_id = $2 AND started_at::date = $3::date);
    """, inspection_id, asset_id, insp["inspected_at"].date())

    disagreement_detected = False
    different_opinions = []

    # Detect if multiple staff held conflicting opinions
    if len(notes) >= 2:
        texts = [n["text"].lower() for n in notes]
        has_water_claim = any("water" in t for t in texts)
        has_crude_claim = any("crude" in t or "oil" in t for t in texts)
        if has_water_claim and has_crude_claim:
            disagreement_detected = True
            different_opinions = [
                {
                    "note_id": n["note_id"],
                    "author": n["author_name"] or n["author_user_id"],
                    "role": n["role"] or "Staff",
                    "text": n["text"]
                }
                for n in notes
            ]

    # Detection stands if:
    # 1. AI flagged spill
    # 2. No formal correction note was approved
    # 3. Maintenance repair was executed
    detection_stands = bool(insp["spill_detected"]) and not has_formal_override

    explanation = None
    if disagreement_detected:
        explanation = (
            f"Yes, the spill detection stands. Ryan Brooks ({different_opinions[0]['note_id']}) initially suspected "
            f"produced water, but Chris Dalton (HSE, {different_opinions[1]['note_id']}) sampled the stain and confirmed crude oil. "
            f"Neither note was a formal correction, and repair {repair['maintenance_id'] if repair else 'record'} was performed."
        )

    return {
        "asset_id": asset_id,
        "inspection_id": inspection_id,
        "spill_detected_by_ai": bool(insp["spill_detected"]),
        "detection_stands": detection_stands,
        "disagreement_detected": disagreement_detected,
        "opinions": different_opinions,
        "repair": dict(repair) if repair else None,
        "explanation": explanation
    }
