"""
Domain Analytics Engine for the Asset Intelligence Copilot.

Provides deterministic, schema-driven operational queries for:
- Asset status evaluation and stale record detection.
- Operational downtime calculations (7-day rule per non-producing inspection).
- False-positive-filtered spill tracking and aggregations.
- Geospatial mapping of environmental releases.
- Multi-dimensional pivot aggregations (Area x Month).
All functions dynamically resolve dates from dataset boundaries to support arbitrary test datasets.
"""

import json
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional
import asyncpg


async def get_system_current_date(conn: asyncpg.Connection) -> date:
    """
    Dynamically determines the reference 'today' date from the latest timestamp in the system
    (inspections, shared context notes, or maintenance).
    Ensures autonomous operation across any new test dataset or expanded history.
    """
    latest = await conn.fetchval("""
        SELECT GREATEST(
            (SELECT MAX(inspected_at)::date FROM inspections),
            (SELECT MAX(created_at)::date FROM shared_context),
            (SELECT MAX(started_at)::date FROM maintenance)
        );
    """)
    return latest if latest is not None else date(2027, 1, 15)


async def get_well_current_status(
    conn: asyncpg.Connection,
    asset_id: str,
    as_of_date: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieves the latest operational status of an oil well.
    Determines production state based on temperature delta compared to the well-type threshold.
    Identifies if recorded_status is stale and surfaces active operator notes/shut-ins.
    """
    if as_of_date is None:
        as_of_date = await get_system_current_date(conn)

    query = """
        SELECT 
            w.asset_id,
            w.name,
            w.well_type,
            w.recorded_status,
            a.name AS area_name,
            t.name AS team_name,
            r.min_producing_temp_delta_c,
            r.temp_alarm_threshold_c,
            i.inspection_id,
            i.inspected_at,
            i.inspector_user_id,
            u.name AS inspector_name,
            i.method,
            ROUND(i.ambient_temp_c::numeric, 1)::float AS ambient_temp_c,
            ROUND(i.wellhead_temp_c::numeric, 1)::float AS wellhead_temp_c,
            ROUND(i.delta_temp_c::numeric, 1)::float AS delta_temp_c,
            i.is_producing,
            i.notes AS inspection_notes
        FROM wells w
        JOIN fleet_areas a ON w.area_id = a.area_id
        JOIN fleet_teams t ON w.team_id = t.team_id
        JOIN well_type_rules r ON w.well_type = r.well_type
        LEFT JOIN LATERAL (
            SELECT * FROM inspections 
            WHERE asset_id = w.asset_id 
            ORDER BY inspected_at DESC 
            LIMIT 1
        ) i ON TRUE
        LEFT JOIN fleet_users u ON i.inspector_user_id = u.user_id
        WHERE w.asset_id = $1;
    """
    row = await conn.fetchrow(query, asset_id)
    if not row:
        return None

    res = dict(row)

    # Check for active context notes valid for the reference date
    notes_query = """
        SELECT sc.note_id, sc.note_type, sc.text, sc.author_user_id, u.name as author_name,
               sc.valid_from, sc.valid_to, sc.created_at
        FROM shared_context sc
        LEFT JOIN fleet_users u ON sc.author_user_id = u.user_id
        WHERE sc.target_id = $1
          AND (sc.valid_to IS NULL OR sc.valid_to >= $2)
        ORDER BY sc.created_at DESC;
    """
    notes = await conn.fetch(notes_query, asset_id, as_of_date)
    res["context_notes"] = [dict(n) for n in notes]
    res["planned_downtime"] = [
        {
            "note_id": n["note_id"],
            "author_name": n["author_name"] or n["author_user_id"],
            "text": n["text"],
            "valid_from": str(n["valid_from"]),
            "valid_to": str(n["valid_to"])
        }
        for n in notes if "shut" in (n["note_type"] or "").lower() or "shut" in (n["text"] or "").lower()
    ]

    # Stale record detection
    computed_status = "active" if res["is_producing"] else "down"
    res["is_status_stale"] = (res["recorded_status"] != computed_status)

    return res


async def get_area_non_producing_wells(
    conn: asyncpg.Connection,
    area_identifier: str,
    as_of_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """
    Finds all wells in a specified area that are currently not producing oil.
    Searches open repairs or active field notes to provide reasons.
    If no record exists, explicitly states that no reason was recorded.
    """
    if as_of_date is None:
        as_of_date = await get_system_current_date(conn)

    query = """
        WITH latest_inspections AS (
            SELECT DISTINCT ON (asset_id)
                inspection_id,
                asset_id,
                inspected_at,
                ROUND(wellhead_temp_c::numeric, 1)::float AS wellhead_temp_c,
                ROUND(ambient_temp_c::numeric, 1)::float AS ambient_temp_c,
                ROUND(delta_temp_c::numeric, 1)::float AS delta_temp_c,
                is_producing,
                notes AS inspector_notes
            FROM inspections
            ORDER BY asset_id, inspected_at DESC
        )
        SELECT 
            w.asset_id,
            w.name AS well_name,
            w.well_type,
            w.recorded_status,
            a.name AS area_name,
            li.delta_temp_c,
            li.ambient_temp_c,
            li.wellhead_temp_c,
            li.inspected_at,
            li.inspector_notes
        FROM wells w
        JOIN fleet_areas a ON w.area_id = a.area_id
        JOIN latest_inspections li ON w.asset_id = li.asset_id
        WHERE (a.area_id = $1 OR a.name ILIKE $1)
          AND li.is_producing = FALSE
        ORDER BY w.asset_id;
    """
    non_producing_wells = await conn.fetch(query, area_identifier)
    results = []

    for well in non_producing_wells:
        w_dict = dict(well)
        asset_id = w_dict["asset_id"]

        # Check for open corrective maintenance
        maint_query = """
            SELECT maintenance_id, issue, action_taken, started_at
            FROM maintenance
            WHERE asset_id = $1 
              AND (completed_at IS NULL OR completed_at::date > $2)
            ORDER BY started_at DESC
            LIMIT 1;
        """
        open_maint = await conn.fetchrow(maint_query, asset_id, as_of_date)

        # Check for active context note (valid currently)
        note_query = """
            SELECT note_id, text, note_type, author_user_id
            FROM shared_context
            WHERE target_id = $1
              AND (valid_to IS NULL OR valid_to >= $2)
            ORDER BY created_at DESC
            LIMIT 1;
        """
        recent_note = await conn.fetchrow(note_query, asset_id, as_of_date)

        reason = None
        has_recorded_reason = True

        if open_maint:
            reason = f"Repair {open_maint['maintenance_id']}, {open_maint['issue']}, started {open_maint['started_at'].strftime('%d %b')}, still open"
        elif recent_note:
            reason = f"Note {recent_note['note_id']}: {recent_note['text']}"
        elif w_dict["inspector_notes"]:
            has_recorded_reason = False
            reason = f"No recorded reason. Inspector note: '{w_dict['inspector_notes']}'"
        else:
            has_recorded_reason = False
            reason = "No recorded reason"

        w_dict["reason"] = reason
        w_dict["has_recorded_reason"] = has_recorded_reason
        w_dict["is_status_stale"] = (w_dict["recorded_status"] == "active")
        results.append(w_dict)

    return results


async def get_area_recently_corrected_wells(
    conn: asyncpg.Connection,
    area_identifier: str
) -> List[Dict[str, Any]]:
    """
    Identifies wells in the specified area that were recently corrected to producing
    via shared_context audit overrides, explaining why they are no longer in the non-producing list.
    """
    rows = await conn.fetch("""
        SELECT sc.target_id as inspection_id, sc.text as reason, 
               sc.original_value, sc.corrected_value, sc.author_user_id,
               u.name as author_name, w.asset_id, w.name as well_name, w.well_type
        FROM shared_context sc
        JOIN inspections i ON sc.target_id = i.inspection_id
        JOIN wells w ON i.asset_id = w.asset_id
        JOIN fleet_areas a ON w.area_id = a.area_id
        LEFT JOIN fleet_users u ON sc.author_user_id = u.user_id
        WHERE (a.area_id = $1 OR a.name ILIKE $1)
          AND sc.note_type = 'correction'
          AND (sc.corrected_value->>'is_producing')::boolean = TRUE
        ORDER BY sc.created_at DESC;
    """, area_identifier)

    output = []
    for r in rows:
        orig = json.loads(r["original_value"]) if isinstance(r["original_value"], str) else (r["original_value"] or {})
        corr = json.loads(r["corrected_value"]) if isinstance(r["corrected_value"], str) else (r["corrected_value"] or {})
        author = r["author_name"] or r["author_user_id"] or "Operator"
        output.append({
            "asset_id": r["asset_id"],
            "inspection_id": r["inspection_id"],
            "well_name": r["well_name"],
            "author_name": author,
            "reason": r["reason"],
            "original_reading": orig,
            "corrected_reading": corr,
            "status_explanation": (
                f"{r['asset_id']} is no longer listed as non-producing because {author} corrected "
                f"inspection [{r['inspection_id']}] ({r['reason']}). It is now producing with corrected "
                f"wellhead temp {corr.get('wellhead_temp_c')} °C (delta_T = {corr.get('delta_temp_c')} °C)."
            )
        })
    return output


async def get_well_temperature_trend(
    conn: asyncpg.Connection,
    asset_id: str,
    end_date: Optional[date] = None,
    weeks: int = 13
) -> List[Dict[str, Any]]:
    """
    Retrieves the last N weekly temperature inspection readings for an asset up to end_date.
    Returns ambient temperature, wellhead temperature, delta, and production status in chronological order.
    """
    query = """
        SELECT * FROM (
            SELECT 
                inspection_id,
                inspected_at,
                ROUND(ambient_temp_c::numeric, 1)::float AS ambient_temp_c,
                ROUND(wellhead_temp_c::numeric, 1)::float AS wellhead_temp_c,
                ROUND(delta_temp_c::numeric, 1)::float AS delta_temp_c,
                is_producing
            FROM inspections
            WHERE asset_id = $1
              AND ($2::date IS NULL OR inspected_at::date <= $2)
            ORDER BY inspected_at DESC
            LIMIT $3
        ) sub
        ORDER BY inspected_at ASC;
    """
    rows = await conn.fetch(query, asset_id, end_date, weeks)
    return [dict(r) for r in rows]



async def get_well_spills_history(
    conn: asyncpg.Connection,
    asset_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    years: int = 4
) -> Dict[str, Any]:
    """
    Retrieves confirmed oil spill history for a well over a date range.
    Automatically filters out false-positive spill detections (such as rainwater).
    """
    if end_date is None:
        end_date = await get_system_current_date(conn)
    if start_date is None:
        start_date = end_date - timedelta(days=365 * years)

    query = """
        SELECT 
            inspection_id,
            inspected_at,
            ROUND(spill_est_volume_bbl::numeric, 1)::float AS spill_est_volume_bbl,
            spill_area_pct,
            notes,
            is_false_positive_spill
        FROM inspections
        WHERE asset_id = $1
          AND spill_detected = TRUE
          AND inspected_at::date >= $2
          AND inspected_at::date <= $3
        ORDER BY inspected_at ASC;
    """
    all_detections = await conn.fetch(query, asset_id, start_date, end_date)

    confirmed_spills = []
    excluded_false_positives = []
    total_volume_bbl = 0.0

    for d in all_detections:
        item = dict(d)
        if item["is_false_positive_spill"]:
            excluded_false_positives.append(item)
        else:
            vol = item["spill_est_volume_bbl"] or 0.0
            total_volume_bbl += vol
            confirmed_spills.append(item)

    return {
        "asset_id": asset_id,
        "total_detections_count": len(all_detections),
        "confirmed_spills_count": len(confirmed_spills),
        "total_volume_bbl": round(total_volume_bbl, 1),
        "confirmed_spills": confirmed_spills,
        "excluded_false_positives": excluded_false_positives
    }


async def calculate_well_downtime_days(
    conn: asyncpg.Connection,
    asset_id: str,
    start_date: date,
    end_date: date
) -> Dict[str, Any]:
    """
    Calculates operational downtime days based on weekly inspections in the date range.
    Rule: Each non-producing weekly inspection adds exactly 7 days of downtime.
    Missed inspections add 0 downtime.
    """
    query = """
        SELECT 
            inspection_id,
            inspected_at,
            ROUND(ambient_temp_c::numeric, 1)::float AS ambient_temp_c,
            ROUND(wellhead_temp_c::numeric, 1)::float AS wellhead_temp_c,
            ROUND(delta_temp_c::numeric, 1)::float AS delta_temp_c,
            is_producing,
            notes
        FROM inspections
        WHERE asset_id = $1
          AND inspected_at::date >= $2
          AND inspected_at::date <= $3
          AND is_producing = FALSE
        ORDER BY inspected_at ASC;
    """
    down_inspections = await conn.fetch(query, asset_id, start_date, end_date)
    downtime_days = len(down_inspections) * 7

    events = []
    for insp in down_inspections:
        insp_id = insp["inspection_id"]
        insp_date = insp["inspected_at"].date()
        date_min = insp_date - timedelta(days=3)
        date_max = insp_date + timedelta(days=7)
        maint_query = """
            SELECT maintenance_id, issue, action_taken, maintenance_type
            FROM maintenance
            WHERE asset_id = $1
              AND (
                  triggered_by_inspection_id = $2 
                  OR (started_at::date >= $3 AND started_at::date <= $4)
                  OR (started_at::date <= $5 AND (completed_at IS NULL OR completed_at::date >= $5))
              )
            ORDER BY started_at DESC
            LIMIT 1;
        """
        maint = await conn.fetchrow(maint_query, asset_id, insp_id, date_min, date_max, insp_date)
        events.append({
            "inspection_id": insp_id,
            "date": str(insp_date),
            "ambient_temp_c": insp["ambient_temp_c"],
            "wellhead_temp_c": insp["wellhead_temp_c"],
            "delta_temp_c": insp["delta_temp_c"],
            "maintenance": dict(maint) if maint else None
        })

    # Check for planned downtime notes in shared_context
    planned_notes = await conn.fetch("""
        SELECT sc.note_id, sc.text, sc.author_user_id, u.name as author_name,
               sc.valid_from, sc.valid_to
        FROM shared_context sc
        LEFT JOIN fleet_users u ON sc.author_user_id = u.user_id
        WHERE sc.target_id = $1
          AND (sc.note_type = 'planned_shut_in' OR sc.note_type = 'shut_in' OR sc.text ILIKE '%shut%')
        ORDER BY sc.created_at DESC;
    """, asset_id)
    planned = [
        {
            "note_id": pn["note_id"],
            "author_name": pn["author_name"] or pn["author_user_id"],
            "text": pn["text"],
            "valid_from": str(pn["valid_from"]),
            "valid_to": str(pn["valid_to"])
        }
        for pn in planned_notes
    ]

    return {
        "asset_id": asset_id,
        "non_producing_inspections_count": len(down_inspections),
        "downtime_days": downtime_days,
        "events": events,
        "planned_downtime": planned
    }


async def rank_area_downtime(
    conn: asyncpg.Connection,
    area_identifier: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    days: int = 120,
    limit: int = 3
) -> List[Dict[str, Any]]:
    """
    Ranks wells in a given geographic area by operational downtime over a specified window.
    Downtime days = non_producing_inspections * 7.
    """
    if end_date is None:
        end_date = await get_system_current_date(conn)
    if start_date is None:
        start_date = end_date - timedelta(days=days)

    query = """
        SELECT 
            w.asset_id,
            w.name AS well_name,
            w.well_type,
            a.name AS area_name,
            COUNT(i.inspection_id) AS non_producing_inspections,
            (COUNT(i.inspection_id) * 7) AS downtime_days
        FROM wells w
        JOIN fleet_areas a ON w.area_id = a.area_id
        JOIN inspections i ON w.asset_id = i.asset_id
        WHERE (a.area_id = $1 OR a.name ILIKE ('%' || $1 || '%'))
          AND i.inspected_at::date >= $2
          AND i.inspected_at::date <= $3
          AND i.is_producing = FALSE
        GROUP BY w.asset_id, w.name, w.well_type, a.name
        ORDER BY downtime_days DESC, w.asset_id ASC
        LIMIT $4;
    """
    rows = await conn.fetch(query, area_identifier, start_date, end_date, limit)
    return [dict(r) for r in rows]


async def get_area_recent_spills_geospatial(
    conn: asyncpg.Connection,
    area_identifier: str,
    end_date: Optional[date] = None,
    days: int = 90
) -> List[Dict[str, Any]]:
    """
    Retrieves all wells in an area with confirmed oil spills in the last N days.
    Includes latitude and longitude coordinates for map visualization.
    Filters out false-positive spills.
    """
    if end_date is None:
        end_date = await get_system_current_date(conn)

    start_date = end_date - timedelta(days=days)
    query = """
        SELECT 
            w.asset_id,
            w.name AS well_name,
            w.lat,
            w.lon,
            a.name AS area_name,
            i.inspection_id,
            i.inspected_at::date AS spill_date,
            ROUND(i.spill_est_volume_bbl::numeric, 1)::float AS barrels
        FROM inspections i
        JOIN wells w ON i.asset_id = w.asset_id
        JOIN fleet_areas a ON w.area_id = a.area_id
        WHERE (a.area_id = $1 OR a.name ILIKE $1)
          AND i.spill_detected = TRUE
          AND i.is_false_positive_spill = FALSE
          AND i.inspected_at::date >= $2
          AND i.inspected_at::date <= $3
        ORDER BY i.inspected_at DESC;
    """
    rows = await conn.fetch(query, area_identifier, start_date, end_date)
    return [dict(r) for r in rows]


async def aggregate_spills_matrix(
    conn: asyncpg.Connection,
    year: int = 2026
) -> Dict[str, Any]:
    """
    Aggregates real oil spills by geographic area and calendar month for a given year.
    Filters out false-positive spill detections.
    Dynamically bounds months to available data for in-progress years or full 12 months for past years.
    """
    max_month = await conn.fetchval(
        "SELECT MAX(EXTRACT(MONTH FROM inspected_at))::int FROM inspections WHERE EXTRACT(YEAR FROM inspected_at) = $1;",
        year
    )
    if not max_month:
        max_month = 12

    query = """
        SELECT 
            a.name AS area_name,
            EXTRACT(MONTH FROM i.inspected_at)::int AS month,
            COUNT(*) AS spill_count
        FROM inspections i
        JOIN wells w ON i.asset_id = w.asset_id
        JOIN fleet_areas a ON w.area_id = a.area_id
        WHERE EXTRACT(YEAR FROM i.inspected_at) = $1
          AND i.spill_detected = TRUE
          AND i.is_false_positive_spill = FALSE
        GROUP BY a.name, EXTRACT(MONTH FROM i.inspected_at)
        ORDER BY a.name, month;
    """
    rows = await conn.fetch(query, year)

    # Structure into matrix dictionary
    matrix = {}
    # Pre-populate all known areas
    all_areas = await conn.fetch("SELECT name FROM fleet_areas ORDER BY area_id;")
    for a in all_areas:
        matrix[a["name"]] = {m: 0 for m in range(1, max_month + 1)}

    for r in rows:
        area = r["area_name"]
        month = r["month"]
        count = r["spill_count"]
        if area in matrix and month <= max_month:
            matrix[area][month] = count

    # Compute row totals
    result_rows = []
    for area, months in matrix.items():
        total = sum(months.values())
        result_rows.append({
            "area": area,
            "months": months,
            "total": total
        })

    return {
        "year": year,
        "max_month": max_month,
        "rows": result_rows
    }
