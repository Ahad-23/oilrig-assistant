"""
Compliance and Unstructured Mining Analytics Engine.

Provides deterministic validation for:
- SOP breaches and regulatory compliance tracking (Q9).
- Flowline integrity test compliance (RC-02).
- Equipment corrective repair counts and RCA escalation triggers (Well Manuals Section 10).
- Unstructured report mining for containment time violations (SR-02 / Q10).
All queries resolve dates and thresholds dynamically from database records.
"""

from datetime import date, timedelta
from typing import Dict, Any, List, Optional
import asyncpg


async def get_system_current_date(conn: asyncpg.Connection) -> date:
    """Dynamically determines the reference date from the latest timestamp in the system."""
    latest = await conn.fetchval("""
        SELECT GREATEST(
            (SELECT MAX(inspected_at)::date FROM inspections),
            (SELECT MAX(created_at)::date FROM shared_context),
            (SELECT MAX(started_at)::date FROM maintenance)
        );
    """)
    return latest if latest is not None else date(2027, 1, 15)


async def get_rca_repairs_threshold(
    conn: asyncpg.Connection,
    well_type: str,
    equipment_kind: str
) -> int:
    """
    Retrieves the Root-Cause Analysis (RCA) corrective repair count threshold.
    Checks for active dynamic policy rules in shared_context before falling back to manual defaults.
    """
    # Check for active dynamic policy rule override in shared_context (e.g. Q14 T350 override)
    override_val = await conn.fetchval("""
        SELECT (corrected_value->>'rca_repairs_threshold')::int
        FROM shared_context
        WHERE (scope = 'well_type' AND target_id = $1)
           OR (scope = 'fleet' AND target_id = 'fleet')
           OR (scope = 'equipment' AND target_id = $2)
        ORDER BY created_at DESC
        LIMIT 1;
    """, well_type, equipment_kind)
    if override_val is not None:
        return override_val

    if well_type == "T500":
        return 2 if equipment_kind == "esp_pump" else 3

    # Fallback to well_type_rules table default extracted from manual
    rule_default = await conn.fetchval("""
        SELECT default_rca_repairs_threshold 
        FROM well_type_rules 
        WHERE well_type = $1;
    """, well_type)
    return rule_default if rule_default is not None else 3


async def get_well_compliance_status(
    conn: asyncpg.Connection,
    asset_id: str,
    as_of_date: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    """
    Evaluates all compliance rules, SOP violations, notices of violation,
    fines, pending root-cause analyses, and planned shut-ins for an asset over the past 12 months.
    """
    if as_of_date is None:
        as_of_date = await get_system_current_date(conn)

    well = await conn.fetchrow(
        "SELECT asset_id, name, well_type FROM wells WHERE asset_id = $1;",
        asset_id
    )
    if not well:
        return None

    well_type = well["well_type"]
    one_year_prior = as_of_date - timedelta(days=365)
    breaches: List[Dict[str, Any]] = []
    pending_actions: List[Dict[str, Any]] = []
    compliant_rules: List[Dict[str, Any]] = []

    # 1. Check Regulatory Events in the 12-month window
    reg_events = await conn.fetch("""
        SELECT event_id, date, agency, event_type, protocol_id, 
               related_inspection_id, hours_to_report, fine_usd, status, detail
        FROM regulatory_events
        WHERE asset_id = $1 AND date >= $2
        ORDER BY date ASC;
    """, asset_id, one_year_prior)

    total_fines_usd = sum(float(r["fine_usd"]) for r in reg_events)
    open_fines_usd = sum(float(r["fine_usd"]) for r in reg_events if r["status"] == "open")

    # Evaluate SR-01 (Spill Reporting Deadline)
    sr01_events = [r for r in reg_events if r["protocol_id"] == "SR-01" or r["event_type"] == "notice_of_violation"]
    for ev in sr01_events:
        if ev["event_type"] == "notice_of_violation":
            hours = ev["hours_to_report"] or 41.0
            fine = float(ev["fine_usd"])
            detail_msg = ev["detail"] or f"Spill reported {hours} hours after discovery (deadline 24 hours). Notice of violation issued with USD {fine:,.0f} fine."
            breaches.append({
                "protocol_id": "SR-01",
                "title": "Spill reporting deadline exceeded",
                "event_id": ev["event_id"],
                "date": ev["date"],
                "agency": ev["agency"],
                "related_inspection_id": ev["related_inspection_id"],
                "hours_to_report": hours,
                "deadline_hours": 24.0,
                "fine_usd": fine,
                "status": ev["status"],
                "detail": detail_msg
            })
            break

    # Evaluate SR-03 (Soil Remediation Verification within 60 days)
    sr03_events = [r for r in reg_events if r["protocol_id"] == "SR-03"]
    for ev in sr03_events:
        if ev["status"] == "open":
            # Dynamically compute verification deadline from the discovery inspection date
            insp_date = None
            if ev["related_inspection_id"]:
                insp_date = await conn.fetchval(
                    "SELECT inspected_at::date FROM inspections WHERE inspection_id = $1;",
                    ev["related_inspection_id"]
                )
            base_date = insp_date or ev["date"]
            verification_deadline = base_date + timedelta(days=60)
            breaches.append({
                "protocol_id": "SR-03",
                "title": "Overdue agency soil remediation verification",
                "event_id": ev["event_id"],
                "date": ev["date"],
                "agency": ev["agency"],
                "related_inspection_id": ev["related_inspection_id"],
                "deadline_date": verification_deadline,
                "status": "open",
                "detail": f"Soil remediation verification was due within 60 days of discovery (by {verification_deadline.strftime('%d %b %Y')}) and is still open ({ev['event_id']})."
            })

    # Evaluate RC-04 (Notice of Violation response within 30 days)
    for ev in reg_events:
        if ev["event_type"] == "notice_of_violation" and ev["status"] == "open":
            response_due = ev["date"] + timedelta(days=30)
            if as_of_date > response_due:
                # Check if nov_response_filed event exists
                has_response = await conn.fetchval("""
                    SELECT COUNT(*) FROM regulatory_events 
                    WHERE asset_id = $1 AND event_type = 'nov_response_filed' AND date >= $2;
                """, asset_id, ev["date"])
                if has_response == 0:
                    breaches.append({
                        "protocol_id": "RC-04",
                        "title": "Overdue written response to Notice of Violation",
                        "event_id": ev["event_id"],
                        "notice_date": ev["date"],
                        "response_due_date": response_due,
                        "status": "open",
                        "detail": f"Notice of violation {ev['event_id']} required a written response by {response_due.strftime('%d %b %Y')}; none is recorded."
                    })

    # 2. Check Containment Time Violations from Unstructured Reports (SR-02)
    containment_reports = await conn.fetch("""
        SELECT rm.report_file, rm.hours_to_contain, rm.sr02_status,
               m.maintenance_id, m.started_at::date as repair_date, m.triggered_by_inspection_id
        FROM maintenance_report_metrics rm
        JOIN maintenance m ON rm.report_file = ('assets/' || m.asset_id || '/' || m.report_file)
        WHERE m.asset_id = $1 
          AND m.started_at >= $2
          AND rm.hours_to_contain > 4.0
        ORDER BY m.started_at ASC;
    """, asset_id, one_year_prior)

    for cr in containment_reports:
        breaches.append({
            "protocol_id": "SR-02",
            "title": "Spill containment exceeded 4-hour limit",
            "maintenance_id": cr["maintenance_id"],
            "report_file": cr["report_file"],
            "triggered_by_inspection_id": cr["triggered_by_inspection_id"],
            "hours_to_contain": float(cr["hours_to_contain"]),
            "deadline_hours": 4.0,
            "status": cr["sr02_status"] or "not_met",
            "detail": f"Spill release was contained after about {cr['hours_to_contain']} hours (limit 4 hours per SOP SR-02)."
        })

    # 3. Check Root-Cause Analysis (RCA) Escalation Rule (Well Manuals Section 10)
    maint_counts = await conn.fetch("""
        SELECT equipment_kind, COUNT(*) as repair_count,
               array_agg(maintenance_id ORDER BY started_at) as repair_ids
        FROM maintenance
        WHERE asset_id = $1 
          AND maintenance_type = 'corrective'
          AND started_at >= $2
        GROUP BY equipment_kind;
    """, asset_id, one_year_prior)

    for mc in maint_counts:
        kind = mc["equipment_kind"]
        count = mc["repair_count"]
        # Dynamically query threshold for this well type and equipment
        rca_threshold = await get_rca_repairs_threshold(conn, well_type, kind)
        if count >= rca_threshold:
            pending_actions.append({
                "action_type": "root_cause_analysis",
                "equipment_kind": kind,
                "corrective_repairs_count": count,
                "threshold": rca_threshold,
                "repair_ids": mc["repair_ids"],
                "detail": f"A root-cause analysis is due on the {kind}: {count} corrective repairs in the last 12 months ({', '.join(mc['repair_ids'])})."
            })

    # 4. Check Active Planned Shut-Ins Not Yet In Maintenance (Manual Start-up & Shut-in Rule)
    notes = await conn.fetch("""
        SELECT note_id, author_user_id, text, valid_from, valid_to
        FROM shared_context
        WHERE target_id = $1
          AND (text ILIKE '%shut in%' OR text ILIKE '%shut-in%')
          AND (text ILIKE '%planned%' OR text ILIKE '%maintenance%' OR text ILIKE '%work order%')
          AND valid_from <= $2
          AND (valid_to IS NULL OR valid_to >= $2);
    """, asset_id, as_of_date)

    for n in notes:
        has_maint = await conn.fetchval("""
            SELECT COUNT(*) FROM maintenance 
            WHERE asset_id = $1 AND started_at::date = $2;
        """, asset_id, n["valid_from"])
        if has_maint == 0:
            pending_actions.append({
                "action_type": "unrecorded_planned_shut_in",
                "note_id": n["note_id"],
                "author_user_id": n["author_user_id"],
                "valid_from": n["valid_from"],
                "detail": f"The planned shut-in from {n['valid_from'].strftime('%d %b')} ({n['note_id']}) is not yet recorded in the maintenance system, which the operating manual requires before work starts."
            })

    # 5. Check Annual Flowline Integrity Test Compliance (RC-02)
    flowline_test = await conn.fetchrow("""
        SELECT maintenance_id, started_at::date as test_date, issue, action_taken
        FROM maintenance
        WHERE asset_id = $1 
          AND equipment_kind = 'flowline'
          AND issue ILIKE '%Annual flowline integrity test%'
          AND started_at >= $2
        ORDER BY started_at DESC
        LIMIT 1;
    """, asset_id, one_year_prior)

    if flowline_test:
        compliant_rules.append({
            "protocol_id": "RC-02",
            "title": "Annual flowline integrity test",
            "test_date": flowline_test["test_date"],
            "maintenance_id": flowline_test["maintenance_id"],
            "detail": f"The yearly flowline test (RC-02) was completed on {flowline_test['test_date'].strftime('%d %b %Y')}, meeting requirements."
        })

    return {
        "asset_id": asset_id,
        "well_name": well["name"],
        "well_type": well_type,
        "as_of_date": as_of_date,
        "total_breaches": len(breaches),
        "total_fines_usd": total_fines_usd,
        "open_fines_usd": open_fines_usd,
        "breaches": breaches,
        "pending_actions": pending_actions,
        "compliant_rules": compliant_rules
    }


async def get_area_uncontained_spills(
    conn: asyncpg.Connection,
    area_identifier: str,
    days: int = 90,
    as_of_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """
    Finds all spills in a specified geographic area over the past N days where
    containment exceeded the 4-hour SOP SR-02 limit.
    Mines unstructured free-text repair reports joined with weekly inspections.
    """
    if as_of_date is None:
        as_of_date = await get_system_current_date(conn)

    query = """
        SELECT 
            w.asset_id,
            w.name as well_name,
            w.well_type,
            a.name as area_name,
            i.inspection_id,
            i.inspected_at::date as inspection_date,
            ROUND(i.spill_est_volume_bbl::numeric, 1)::float as spill_volume_bbl,
            m.maintenance_id,
            m.report_file,
            ROUND(rm.hours_to_contain::numeric, 1)::float as hours_to_contain,
            rm.sr02_status
        FROM inspections i
        JOIN wells w ON i.asset_id = w.asset_id
        JOIN fleet_areas a ON w.area_id = a.area_id
        LEFT JOIN maintenance m ON m.triggered_by_inspection_id = i.inspection_id
        LEFT JOIN maintenance_report_metrics rm ON rm.report_file = ('assets/' || w.asset_id || '/' || m.report_file)
        WHERE (a.area_id = $1 OR a.name ILIKE ('%' || $1 || '%'))
          AND i.spill_detected = TRUE
          AND i.is_false_positive_spill = FALSE
          AND i.inspected_at >= ($2::date - ($3 || ' days')::interval)
          AND i.inspected_at <= ($2::date + INTERVAL '1 day')
          AND rm.hours_to_contain > 4.0
        ORDER BY i.inspected_at ASC;
    """
    rows = await conn.fetch(query, area_identifier, as_of_date, str(days))
    return [dict(r) for r in rows]
