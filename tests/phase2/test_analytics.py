import pytest
from datetime import date
from src.analytics.domain_queries import (
    get_well_current_status,
    get_area_non_producing_wells,
    get_well_temperature_trend,
    get_well_spills_history,
    calculate_well_downtime_days,
    rank_area_downtime,
    get_area_recent_spills_geospatial,
    aggregate_spills_matrix,
)

@pytest.mark.asyncio
async def test_q1_single_well_status(db_conn):
    """
    Validates evaluation query Q1:
    - WELL-0001 status evaluated as not producing (delta 3.2 C < 15.0 C threshold).
    - Latest inspection by Ryan Brooks on 15 Oct 2026.
    - Context note CTX-0001-003 present detailing planned shut-in.
    - Stale recorded_status identified.
    """
    status = await get_well_current_status(db_conn, "WELL-0001")
    assert status is not None
    assert status["asset_id"] == "WELL-0001"
    assert status["is_producing"] is False
    assert status["delta_temp_c"] == 3.2
    assert status["wellhead_temp_c"] == 25.6
    assert status["ambient_temp_c"] == 22.4
    assert status["inspection_id"] == "INS-0001-0203"
    assert status["inspector_name"] == "Ryan Brooks"
    assert status["recorded_status"] == "active"
    assert status["is_status_stale"] is True

    # Validate note CTX-0001-003
    note_ids = [n["note_id"] for n in status["context_notes"]]
    assert "CTX-0001-003" in note_ids


@pytest.mark.asyncio
async def test_q2_area_non_producing_wells(db_conn):
    """
    Validates evaluation query Q2:
    - Identifies 4 non-producing wells in Northeast Block 8 (WELL-0164, 0170, 0172, 0175).
    - Identifies open repairs for WELL-0170 and WELL-0172.
    - Identifies absence of recorded reason for WELL-0164 and WELL-0175 without hallucination.
    """
    wells = await get_area_non_producing_wells(db_conn, "Northeast Block 8")
    assert len(wells) == 4

    well_map = {w["asset_id"]: w for w in wells}
    assert "WELL-0164" in well_map
    assert "WELL-0170" in well_map
    assert "WELL-0172" in well_map
    assert "WELL-0175" in well_map

    # WELL-0164 has no open maintenance record, but has inspector note
    assert well_map["WELL-0164"]["has_recorded_reason"] is False
    assert "Pump jack not moving" in well_map["WELL-0164"]["reason"]

    # WELL-0170 has open repair MNT-0170-031
    assert "MNT-0170-031" in well_map["WELL-0170"]["reason"]
    assert "bearing wear" in well_map["WELL-0170"]["reason"].lower()

    # WELL-0172 has open repair MNT-0172-028
    assert "MNT-0172-028" in well_map["WELL-0172"]["reason"]
    assert "pinhole leak" in well_map["WELL-0172"]["reason"].lower()

    # WELL-0175 has no recorded reason
    assert well_map["WELL-0175"]["has_recorded_reason"] is False
    assert well_map["WELL-0175"]["reason"] == "No recorded reason"


@pytest.mark.asyncio
async def test_q3_temperature_trend(db_conn):
    """
    Validates evaluation query Q3:
    - 13 weekly temperature readings for WELL-0001 ending 15 Oct 2026.
    - Non-producing readings marked on 8 Oct and 15 Oct 2026.
    """
    trend = await get_well_temperature_trend(db_conn, "WELL-0001", weeks=13)
    assert len(trend) == 13

    # Dates should span 23 Jul 2026 to 15 Oct 2026
    start_dt = trend[0]["inspected_at"].date()
    end_dt = trend[-1]["inspected_at"].date()
    assert start_dt == date(2026, 7, 23)
    assert end_dt == date(2026, 10, 15)

    # Check non-producing readings
    non_producing_dates = [r["inspected_at"].date() for r in trend if not r["is_producing"]]
    assert non_producing_dates == [date(2026, 10, 8), date(2026, 10, 15)]


@pytest.mark.asyncio
async def test_q4_spill_count_and_volume(db_conn):
    """
    Validates evaluation query Q4:
    - Confirmed spills = 6, total volume = 15.1 bbl.
    - False positive detection INS-0001-0070 (rainwater) excluded.
    """
    history = await get_well_spills_history(db_conn, "WELL-0001")
    assert history["total_detections_count"] == 7
    assert history["confirmed_spills_count"] == 6
    assert history["total_volume_bbl"] == 15.1

    # Verify excluded false positive
    excluded_ids = [d["inspection_id"] for d in history["excluded_false_positives"]]
    assert "INS-0001-0070" in excluded_ids

    # Verify confirmed spill volumes
    volumes = [s["spill_est_volume_bbl"] for s in history["confirmed_spills"]]
    assert volumes == [0.5, 2.6, 3.3, 0.3, 6.8, 1.6]


@pytest.mark.asyncio
async def test_q5_downtime_2025(db_conn):
    """
    Validates evaluation query Q5:
    - WELL-0001 downtime in 2025 = 21 days (3 weekly inspections * 7).
    - 24 Jul 2025: prime mover trip (MNT-0001-021).
    - 16 and 23 Oct 2025: stuffing box packing leak (MNT-0001-023).
    """
    downtime = await calculate_well_downtime_days(
        db_conn,
        "WELL-0001",
        date(2025, 1, 1),
        date(2025, 12, 31)
    )
    assert downtime["non_producing_inspections_count"] == 3
    assert downtime["downtime_days"] == 21

    dates = [e["date"] for e in downtime["events"]]
    assert dates == [date(2025, 7, 24), date(2025, 10, 16), date(2025, 10, 23)]

    # 24 Jul 2025 associated maintenance
    event_jul = downtime["events"][0]
    assert event_jul["maintenance"] is not None
    assert event_jul["maintenance"]["maintenance_id"] == "MNT-0001-021"


@pytest.mark.asyncio
async def test_q6_downtime_ranking(db_conn):
    """
    Validates evaluation query Q6:
    - Top 3 wells with highest downtime in Northeast Block 7 (16 Jun to 16 Oct 2026).
    - WELL-0121: 49 days.
    - WELL-0138: 42 days.
    - WELL-0107: 42 days.
    """
    top3 = await rank_area_downtime(
        db_conn,
        "Northeast Block 7",
        date(2026, 6, 16),
        date(2026, 10, 16),
        limit=3
    )
    assert len(top3) == 3

    assert top3[0]["asset_id"] == "WELL-0121"
    assert top3[0]["downtime_days"] == 49

    tied_wells = {top3[1]["asset_id"], top3[2]["asset_id"]}
    assert tied_wells == {"WELL-0138", "WELL-0107"}
    assert top3[1]["downtime_days"] == 42
    assert top3[2]["downtime_days"] == 42


@pytest.mark.asyncio
async def test_q7_geospatial_recent_spills(db_conn):
    """
    Validates evaluation query Q7:
    - 4 wells in Northeast Block 8 with confirmed spills in last 90 days.
    - WELL-0151 (4.5 bbl), WELL-0165 (1.2 bbl), WELL-0175 (3.9 bbl), WELL-0186 (0.6 bbl).
    - Excludes false positive detections (e.g. WELL-0194, WELL-0199).
    """
    spills = await get_area_recent_spills_geospatial(db_conn, "Northeast Block 8", days=90)
    assert len(spills) == 4

    spill_map = {s["asset_id"]: s for s in spills}
    assert "WELL-0151" in spill_map
    assert "WELL-0165" in spill_map
    assert "WELL-0175" in spill_map
    assert "WELL-0186" in spill_map

    assert spill_map["WELL-0151"]["barrels"] == 4.5
    assert spill_map["WELL-0165"]["barrels"] == 1.2
    assert spill_map["WELL-0175"]["barrels"] == 3.9
    assert spill_map["WELL-0186"]["barrels"] == 0.6

    for s in spills:
        assert s["lat"] is not None
        assert s["lon"] is not None


@pytest.mark.asyncio
async def test_q8_spills_matrix_heatmap(db_conn):
    """
    Validates evaluation query Q8:
    - 2026 spills by area and month with corrected detections removed.
    - Expected area totals:
      - Southwest Block 23: 35
      - Southwest Block 24: 43
      - Northeast Block 7: 37
      - Northeast Block 8: 26
    """
    matrix = await aggregate_spills_matrix(db_conn, year=2026)
    totals = {r["area"]: r["total"] for r in matrix["rows"]}

    assert totals["Southwest Block 23"] == 35
    assert totals["Southwest Block 24"] == 43
    assert totals["Northeast Block 7"] == 37
    assert totals["Northeast Block 8"] == 26
