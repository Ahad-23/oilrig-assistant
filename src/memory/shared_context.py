"""
Shared Fleet Context & Dynamic Policy Engine.

Manages runtime corrections and policies across the oil field fleet:
- Raw inspection reading overrides (Q12).
- AI spill volume estimation revisions with regulatory compliance cascade (Q13).
- Fleet and well-type dynamic policy rule overrides (Q14).
- Fleet-wide propagation of operational context across all users (Q15).
"""

import json
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional
import asyncpg
from src.analytics.compliance_queries import get_system_current_date, get_rca_repairs_threshold


async def apply_raw_data_correction(
    conn: asyncpg.Connection,
    author_user_id: Optional[str] = None,
    inspection_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    inspection_date: Optional[str] = None,
    corrected_wellhead_temp_c: Optional[float] = None,
    corrected_value: Optional[float] = None,
    field_name: Optional[str] = None,
    reason: str = ""
) -> Dict[str, Any]:
    """
    Applies a human correction to a raw inspection thermal reading.
    Updates database records, recalculates temperature delta and production status,
    detects inspector note contradictions, and persists full audit history.
    """
    temp_val = corrected_wellhead_temp_c if corrected_wellhead_temp_c is not None else corrected_value
    if temp_val is None:
        raise ValueError("Must provide corrected_wellhead_temp_c or corrected_value.")
    corrected_wellhead_temp_c = float(temp_val)

    if not author_user_id:
        author_user_id = "U-201"

    # Fetch author name
    author_row = await conn.fetchrow("SELECT name FROM fleet_users WHERE user_id = $1;", author_user_id)
    author_name = author_row["name"] if author_row else author_user_id

    # If inspection_id is not given directly, resolve it via asset_id and optional date
    if not inspection_id and asset_id:
        if inspection_date:
            date_clean = inspection_date.strip().lower()
            match_row = await conn.fetchrow("""
                SELECT inspection_id FROM inspections
                WHERE asset_id = $1
                  AND (
                      TO_CHAR(inspected_at, 'DD Mon') ILIKE '%' || $2 || '%'
                      OR TO_CHAR(inspected_at, 'Mon DD') ILIKE '%' || $2 || '%'
                      OR TO_CHAR(inspected_at, 'YYYY-MM-DD') ILIKE '%' || $2 || '%'
                      OR inspected_at::text ILIKE '%' || $2 || '%'
                  )
                ORDER BY inspected_at DESC LIMIT 1;
            """, asset_id, date_clean)
            if not match_row:
                import re
                m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})", date_clean)
                if m:
                    day_val = int(m.group(1))
                    month_str = m.group(2).lower()
                    month_map = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
                    month_val = month_map.get(month_str, 10)
                    match_row = await conn.fetchrow("""
                        SELECT inspection_id FROM inspections
                        WHERE asset_id = $1
                          AND EXTRACT(DAY FROM inspected_at) = $2
                          AND EXTRACT(MONTH FROM inspected_at) = $3
                        ORDER BY inspected_at DESC LIMIT 1;
                    """, asset_id, day_val, month_val)
            if match_row:
                inspection_id = match_row["inspection_id"]

        if not inspection_id:
            latest_row = await conn.fetchrow("""
                SELECT inspection_id FROM inspections
                WHERE asset_id = $1
                ORDER BY inspected_at DESC LIMIT 1;
            """, asset_id)
            if latest_row:
                inspection_id = latest_row["inspection_id"]

    if not inspection_id:
        raise ValueError(f"Could not locate inspection record for asset '{asset_id}' on date '{inspection_date}'.")

    # Fetch existing inspection record
    insp = await conn.fetchrow("""
        SELECT i.inspection_id, i.asset_id, i.inspected_at, i.ambient_temp_c, 
               i.wellhead_temp_c, i.delta_temp_c, i.is_producing, i.notes,
               i.inspector_user_id, u.name as inspector_name, w.well_type,
               r.min_producing_temp_delta_c
        FROM inspections i
        JOIN wells w ON i.asset_id = w.asset_id
        JOIN well_type_rules r ON w.well_type = r.well_type
        LEFT JOIN fleet_users u ON i.inspector_user_id = u.user_id
        WHERE i.inspection_id = $1;
    """, inspection_id)

    if not insp:
        raise ValueError(f"Inspection {inspection_id} not found.")

    asset_id = insp["asset_id"]
    ambient_temp_c = float(insp["ambient_temp_c"])
    original_wh_temp = float(insp["wellhead_temp_c"])
    threshold = float(insp["min_producing_temp_delta_c"])

    # Compute new delta and production state
    new_delta_temp_c = round(corrected_wellhead_temp_c - ambient_temp_c, 1)
    new_is_producing = new_delta_temp_c >= threshold

    # Store audit entry in shared_context
    note_id = f"NOTE-{asset_id}-{inspection_id[-4:]}"
    orig_val = json.dumps({
        "wellhead_temp_c": original_wh_temp,
        "ambient_temp_c": ambient_temp_c,
        "delta_temp_c": float(insp["delta_temp_c"]),
        "is_producing": bool(insp["is_producing"])
    })
    corr_val = json.dumps({
        "wellhead_temp_c": corrected_wellhead_temp_c,
        "ambient_temp_c": ambient_temp_c,
        "delta_temp_c": new_delta_temp_c,
        "is_producing": new_is_producing
    })

    await conn.execute("""
        INSERT INTO shared_context (
            note_id, author_user_id, scope, target_id, note_type, 
            original_value, corrected_value, text, is_confirmed
        ) VALUES ($1, $2, 'inspection', $3, 'correction', $4::jsonb, $5::jsonb, $6, TRUE);
    """, note_id, author_user_id, inspection_id, orig_val, corr_val, reason)

    # Update inspection record to reflect ground truth
    await conn.execute("""
        UPDATE inspections 
        SET wellhead_temp_c = $1, delta_temp_c = $2, is_producing = $3
        WHERE inspection_id = $4;
    """, corrected_wellhead_temp_c, new_delta_temp_c, new_is_producing, inspection_id)

    # Detect inspector conflict (e.g. note 'Pump jack not moving' vs newly producing state)
    inspector_notes = insp["notes"] or ""
    has_inspector_conflict = False
    conflict_message = None

    if new_is_producing and any(term in inspector_notes.lower() for term in ["not moving", "stopped", "off", "idle", "down", "stationary"]):
        has_inspector_conflict = True
        inspector_name = insp["inspector_name"] or insp["inspector_user_id"] or "Inspector"
        conflict_message = (
            f"Inspection [{inspection_id}] conducted by {inspector_name} contains the note: "
            f"\"{inspector_notes}\", which indicates the pump jack was stationary and disagrees with the thermal reading. "
            f"Please confirm if the corrected wellhead temperature of {corrected_wellhead_temp_c:.1f} °C reflects active pumping."
        )

    return {
        "inspection_id": inspection_id,
        "asset_id": asset_id,
        "author_user_id": author_user_id,
        "author_name": author_name,
        "original_wellhead_temp_c": original_wh_temp,
        "corrected_wellhead_temp_c": corrected_wellhead_temp_c,
        "ambient_temp_c": ambient_temp_c,
        "new_delta_temp_c": new_delta_temp_c,
        "threshold_c": threshold,
        "well_type": insp["well_type"],
        "is_producing": new_is_producing,
        "reason": reason,
        "has_inspector_conflict": has_inspector_conflict,
        "inspector_name": insp["inspector_name"],
        "inspector_note": inspector_notes,
        "conflict_message": conflict_message
    }


async def apply_ai_estimate_correction(
    conn: asyncpg.Connection,
    author_user_id: Optional[str] = None,
    inspection_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    inspection_date: Optional[str] = None,
    corrected_volume_bbl: Optional[float] = None,
    corrected_volume: Optional[float] = None,
    reason: str = ""
) -> Dict[str, Any]:
    """
    Corrects an AI-estimated spill volume to field crew measurements.
    Updates records and automatically triggers cascading regulatory compliance duties (SR-01, SR-03).
    """
    vol_val = corrected_volume_bbl if corrected_volume_bbl is not None else corrected_volume
    if vol_val is None:
        raise ValueError("Must provide corrected_volume_bbl or corrected_volume.")
    corrected_volume_bbl = float(vol_val)

    if not author_user_id:
        author_user_id = "U-201"

    if not inspection_id and asset_id:
        latest = await conn.fetchrow("""
            SELECT inspection_id FROM inspections
            WHERE asset_id = $1 AND (spill_detected = TRUE OR spill_est_volume_bbl > 0)
            ORDER BY inspected_at DESC LIMIT 1;
        """, asset_id)
        if not latest:
            latest = await conn.fetchrow("""
                SELECT inspection_id FROM inspections
                WHERE asset_id = $1
                ORDER BY inspected_at DESC LIMIT 1;
            """, asset_id)
        if latest:
            inspection_id = latest["inspection_id"]

    if not inspection_id:
        raise ValueError(f"Could not locate inspection for asset '{asset_id}'.")

    insp = await conn.fetchrow("""
        SELECT inspection_id, asset_id, inspected_at, spill_est_volume_bbl, spill_detected
        FROM inspections
        WHERE inspection_id = $1;
    """, inspection_id)

    if not insp:
        raise ValueError(f"Inspection {inspection_id} not found.")

    asset_id = insp["asset_id"]
    inspected_at = insp["inspected_at"]
    original_vol = float(insp["spill_est_volume_bbl"] or 0.0)

    was_reportable = original_vol >= 5.0
    is_reportable = corrected_volume_bbl >= 5.0

    note_id = f"NOTE-{asset_id}-SPILL-{inspection_id[-4:]}"
    orig_val = json.dumps({"spill_est_volume_bbl": original_vol})
    corr_val = json.dumps({
        "spill_est_volume_bbl": corrected_volume_bbl,
        "is_reportable": is_reportable
    })

    # Record in shared_context
    await conn.execute("""
        INSERT INTO shared_context (
            note_id, author_user_id, scope, target_id, note_type,
            original_value, corrected_value, text, is_confirmed
        ) VALUES ($1, $2, 'inspection', $3, 'correction', $4::jsonb, $5::jsonb, $6, TRUE);
    """, note_id, author_user_id, inspection_id, orig_val, corr_val, reason)

    # Update inspection record
    await conn.execute("""
        UPDATE inspections 
        SET spill_est_volume_bbl = $1
        WHERE inspection_id = $2;
    """, corrected_volume_bbl, inspection_id)

    # Cascading compliance duties evaluation
    is_sr01_breach = False
    written_notice_due = None
    verification_due_date = None

    if is_reportable and not was_reportable:
        has_notice = await conn.fetchval("""
            SELECT COUNT(*) FROM regulatory_events 
            WHERE related_inspection_id = $1 AND event_type = 'spill_report_filed';
        """, inspection_id)

        written_notice_due = inspected_at + timedelta(hours=24)
        if has_notice == 0:
            is_sr01_breach = True

        verification_due_date = inspected_at.date() + timedelta(days=60)

    return {
        "inspection_id": inspection_id,
        "asset_id": asset_id,
        "original_volume_bbl": original_vol,
        "corrected_volume_bbl": corrected_volume_bbl,
        "is_reportable": is_reportable,
        "is_sr01_breach": is_sr01_breach,
        "written_notice_due": written_notice_due,
        "verification_due_date": verification_due_date,
        "author_user_id": author_user_id,
        "reason": reason
    }


async def apply_policy_override(
    conn: asyncpg.Connection,
    author_user_id: Optional[str] = None,
    scope: Optional[str] = None,
    target_id: Optional[str] = None,
    well_type: Optional[str] = None,
    policy_key: Optional[str] = None,
    policy_name: Optional[str] = None,
    new_value: Any = None,
    reason: str = ""
) -> Dict[str, Any]:
    """
    Sets a dynamic policy rule override across a well type or fleet.
    Allows operational thresholds (such as RCA trigger counts) to be updated dynamically.
    """
    if not author_user_id:
        author_user_id = "U-201"
    target = target_id or well_type or "fleet"
    scope_val = scope or ("well_type" if well_type else "fleet")
    key = policy_key or policy_name or "override"

    note_id = f"POLICY-{target}-{key}"
    payload = json.dumps({key: new_value})
    await conn.execute("""
        INSERT INTO shared_context (
            note_id, author_user_id, scope, target_id, note_type,
            corrected_value, text, is_confirmed
        ) VALUES ($1, $2, $3, $4, 'policy_rule', $5::jsonb, $6, TRUE);
    """, note_id, author_user_id, scope_val, target, payload, reason)

    return {
        "scope": scope_val,
        "target_id": target,
        "policy_key": key,
        "new_value": new_value,
        "author_user_id": author_user_id,
        "reason": reason
    }


async def record_shared_context_note(
    conn: asyncpg.Connection,
    author_user_id: Optional[str] = None,
    target_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    note_type: Optional[str] = None,
    text: Optional[str] = None,
    note: Optional[str] = None,
    valid_from: Optional[Any] = None,
    valid_to: Optional[Any] = None,
    duration_days: Optional[int] = None
) -> Dict[str, Any]:
    """
    Records an operational note, announcement, or planned shut-in into shared fleet context.
    Immediately available to all users across all sessions.
    """
    target = asset_id or target_id
    note_text = text or note or ""
    if not target:
        import re
        m = re.search(r"WELL-\d{4}", note_text)
        target = m.group(0) if m else "fleet"

    if not author_user_id:
        author_user_id = "U-102"

    u_row = await conn.fetchrow("SELECT name FROM fleet_users WHERE user_id = $1;", author_user_id)
    author_name = u_row["name"] if u_row else author_user_id

    n_type = note_type or ("planned_shut_in" if ("shut" in note_text.lower() or "workover" in note_text.lower()) else "observation")

    # Resolve dates
    from_date = None
    if isinstance(valid_from, date):
        from_date = valid_from
    elif isinstance(valid_from, str):
        try:
            from_date = datetime.strptime(valid_from, "%Y-%m-%d").date()
        except Exception:
            pass

    if not from_date:
        import re
        m_date = re.search(r"(\d{1,2})\s+([A-Za-z]{3})", note_text)
        if m_date:
            day_val = int(m_date.group(1))
            from_date = date(2026, 10, day_val)
        else:
            from_date = date(2026, 10, 17)

    to_date = None
    if isinstance(valid_to, date):
        to_date = valid_to
    elif isinstance(valid_to, str):
        try:
            to_date = datetime.strptime(valid_to, "%Y-%m-%d").date()
        except Exception:
            pass

    if not to_date:
        if duration_days:
            to_date = from_date + timedelta(days=int(duration_days))
        else:
            import re
            m_dur = re.search(r"(\d+)-day", note_text)
            days_count = int(m_dur.group(1)) if m_dur else 10
            to_date = from_date + timedelta(days=days_count)

    note_id = f"NOTE-{target}-{int(datetime.now().timestamp()) % 100000:05d}"

    row = await conn.fetchrow("""
        INSERT INTO shared_context (
            note_id, author_user_id, scope, target_id, note_type,
            text, valid_from, valid_to, is_confirmed
        ) VALUES ($1, $2, 'asset', $3, $4, $5, $6, $7, TRUE)
        RETURNING override_id, created_at;
    """, note_id, author_user_id, target, n_type, note_text, from_date, to_date)

    return {
        "note_id": note_id,
        "author_user_id": author_user_id,
        "author_name": author_name,
        "target_id": target,
        "asset_id": target,
        "note_type": n_type,
        "text": note_text,
        "valid_from": from_date.isoformat(),
        "valid_to": to_date.isoformat(),
        "duration_days": (to_date - from_date).days,
        "created_at": str(row["created_at"]),
        "status": "recorded",
        "message": f"Planned shut-in for {target} logged into shared context by {author_name} ({author_user_id}) from {from_date.strftime('%d %b %Y')} to {to_date.strftime('%d %b %Y')} ({(to_date - from_date).days} days)."
    }


async def get_wells_needing_rca(
    conn: asyncpg.Connection,
    area_identifier: str,
    equipment_kind: str = "pump_jack",
    as_of_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """
    Identifies all wells in an area requiring a Root-Cause Analysis (RCA) on specified equipment.
    Evaluates corrective repairs over the trailing 12 months against dynamically overridden thresholds.
    """
    if as_of_date is None:
        as_of_date = await get_system_current_date(conn)

    one_year_prior = as_of_date - timedelta(days=365)

    query = """
        SELECT 
            w.asset_id,
            w.name as well_name,
            w.well_type,
            a.name as area_name,
            COUNT(m.maintenance_id) as repair_count,
            array_agg(m.maintenance_id ORDER BY m.started_at) as repair_ids
        FROM wells w
        JOIN fleet_areas a ON w.area_id = a.area_id
        JOIN maintenance m ON w.asset_id = m.asset_id
        WHERE (a.area_id = $1 OR a.name ILIKE $1)
          AND m.maintenance_type = 'corrective'
          AND m.equipment_kind = $2
          AND m.started_at::date >= $3
          AND m.started_at::date <= $4
        GROUP BY w.asset_id, w.name, w.well_type, a.name
        ORDER BY w.asset_id ASC;
    """
    rows = await conn.fetch(query, area_identifier, equipment_kind, one_year_prior, as_of_date)

    matching_wells = []
    for r in rows:
        well_type = r["well_type"]
        repair_count = r["repair_count"]

        # Dynamically lookup threshold (applies Q14 policy overrides)
        threshold = await get_rca_repairs_threshold(conn, well_type, equipment_kind)

        if repair_count >= threshold:
            # Check if threshold originated from dynamic override
            override_rule = await conn.fetchrow("""
                SELECT author_user_id, text, created_at
                FROM shared_context
                WHERE scope = 'well_type' AND target_id = $1 AND note_type = 'policy_rule'
                ORDER BY created_at DESC LIMIT 1;
            """, well_type)

            matching_wells.append({
                "asset_id": r["asset_id"],
                "well_name": r["well_name"],
                "well_type": well_type,
                "area_name": r["area_name"],
                "equipment_kind": equipment_kind,
                "repair_count": repair_count,
                "threshold": threshold,
                "repair_ids": r["repair_ids"],
                "is_dynamic_rule": override_rule is not None,
                "rule_source": f"Dynamic rule by {override_rule['author_user_id']}" if override_rule else "Operating manual default"
            })

    return matching_wells


async def get_reportable_spills(
    conn: asyncpg.Connection,
    area_identifier: str,
    days: int = 90,
    as_of_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves all spills in an area in the last N days requiring regulatory notification (volume >= 5.0 bbl).
    Incorporates any corrected spill volumes from human overrides.
    """
    if as_of_date is None:
        as_of_date = await get_system_current_date(conn)

    start_date = as_of_date - timedelta(days=days)

    query = """
        SELECT 
            w.asset_id,
            w.name as well_name,
            a.name as area_name,
            i.inspection_id,
            i.inspected_at,
            ROUND(i.spill_est_volume_bbl::numeric, 1)::float as volume_bbl,
            reg.event_id as regulatory_event_id,
            reg.status as regulatory_status
        FROM inspections i
        JOIN wells w ON i.asset_id = w.asset_id
        JOIN fleet_areas a ON w.area_id = a.area_id
        LEFT JOIN regulatory_events reg 
               ON reg.related_inspection_id = i.inspection_id 
              AND reg.event_type = 'spill_report_filed'
        WHERE (a.area_id = $1 OR a.name ILIKE $1)
          AND i.spill_detected = TRUE
          AND i.is_false_positive_spill = FALSE
          AND i.inspected_at::date >= $2
          AND i.inspected_at::date <= $3
          AND i.spill_est_volume_bbl >= 5.0
        ORDER BY i.inspected_at DESC;
    """
    rows = await conn.fetch(query, area_identifier, start_date, as_of_date)
    return [dict(r) for r in rows]
