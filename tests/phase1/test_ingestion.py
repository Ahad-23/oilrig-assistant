import pytest

@pytest.mark.asyncio
async def test_wells_and_areas_integrity(db_conn):
    """Verifies that all 200 wells and 4 geographic areas are loaded correctly with 50 wells each."""
    # Check total wells
    wells_count = await db_conn.fetchval("SELECT COUNT(*) FROM wells;")
    assert wells_count == 200, f"Expected 200 wells, got {wells_count}"

    # Check 50 wells per area
    area_counts = await db_conn.fetch("""
        SELECT area_id, COUNT(*) as count 
        FROM wells 
        GROUP BY area_id 
        ORDER BY area_id;
    """)
    assert len(area_counts) == 4, f"Expected 4 areas, got {len(area_counts)}"
    for row in area_counts:
        assert row["count"] == 50, f"Expected 50 wells in area {row['area_id']}, got {row['count']}"

@pytest.mark.asyncio
async def test_well_type_rules(db_conn):
    """Verifies dynamic extraction of production temperature thresholds from manuals."""
    rules = await db_conn.fetch("SELECT well_type, min_producing_temp_delta_c, temp_alarm_threshold_c FROM well_type_rules;")
    rule_map = {r["well_type"]: (r["min_producing_temp_delta_c"], r["temp_alarm_threshold_c"]) for r in rules}

    assert "T200" in rule_map
    assert "T350" in rule_map
    assert rule_map["T200"][0] == 15.0, "T200 producing threshold must be 15.0 °C"
    assert rule_map["T350"][0] == 20.0, "T350 producing threshold must be 20.0 °C"
    assert rule_map["T200"][1] == 85.0, "T200 alarm temp must be 85.0 °C"
    assert rule_map["T350"][1] == 95.0, "T350 alarm temp must be 95.0 °C"

@pytest.mark.asyncio
async def test_inspections_data_and_delta(db_conn):
    """Verifies inspections count (>39k), delta calculation, and production logic."""
    total_inspections = await db_conn.fetchval("SELECT COUNT(*) FROM inspections;")
    assert total_inspections >= 39500, f"Expected at least 39,500 inspections, got {total_inspections}"

    # Check that delta_temp_c strictly equals round(wellhead_temp_c - ambient_temp_c, 2)
    invalid_deltas = await db_conn.fetchval("""
        SELECT COUNT(*) 
        FROM inspections 
        WHERE delta_temp_c != ROUND((wellhead_temp_c - ambient_temp_c)::numeric, 2)::real;
    """)
    assert invalid_deltas == 0, f"Found {invalid_deltas} rows with mismatched delta_temp_c"

    # Check that producing status matches the manual's threshold
    mismatched_prod = await db_conn.fetchval("""
        SELECT COUNT(*)
        FROM inspections i
        JOIN wells w ON i.asset_id = w.asset_id
        JOIN well_type_rules r ON w.well_type = r.well_type
        WHERE i.is_producing != (i.delta_temp_c >= r.min_producing_temp_delta_c);
    """)
    assert mismatched_prod == 0, f"Found {mismatched_prod} rows with mismatched is_producing logic"

@pytest.mark.asyncio
async def test_false_positive_rainwater_override(db_conn):
    """Verifies that false-positive corrections (INS-0001-0070 rainwater) are correctly flagged."""
    fp_insp = await db_conn.fetchrow("""
        SELECT is_false_positive_spill, spill_detected 
        FROM inspections 
        WHERE inspection_id = 'INS-0001-0070';
    """)
    assert fp_insp is not None, "INS-0001-0070 must exist"
    assert fp_insp["is_false_positive_spill"] is True, "INS-0001-0070 must be flagged as false positive spill"

    # Check a real spill has is_false_positive_spill = False
    real_insp = await db_conn.fetchrow("""
        SELECT is_false_positive_spill, spill_detected 
        FROM inspections 
        WHERE inspection_id = 'INS-0001-0185';
    """)
    assert real_insp is not None, "INS-0001-0185 must exist"
    assert real_insp["is_false_positive_spill"] is False, "INS-0001-0185 is a real spill and must not be false positive"

@pytest.mark.asyncio
async def test_extracted_report_metrics(db_conn):
    """Verifies extraction of containment time and compliance status from free-text reports."""
    total_metrics = await db_conn.fetchval("SELECT COUNT(*) FROM maintenance_report_metrics;")
    assert total_metrics >= 1500, f"Expected >= 1500 report metric rows, got {total_metrics}"

    # Verify the June 2026 flowline spill report on WELL-0001
    report = await db_conn.fetchrow("""
        SELECT hours_to_contain, sr01_status, sr02_status
        FROM maintenance_report_metrics
        WHERE report_file LIKE '%MNT-0001-june-2026-flowline-spill.md';
    """)
    assert report is not None, "June 2026 flowline spill report must exist"
    assert report["hours_to_contain"] == 7.0, f"Expected 7.0 hours to contain, got {report['hours_to_contain']}"
    assert report["sr01_status"] == "not_met", "SR-01 status should be not_met"
    assert report["sr02_status"] == "not_met", "SR-02 status should be not_met"

@pytest.mark.asyncio
async def test_regulatory_events_and_shared_context(db_conn):
    """Verifies regulatory events and human context notes."""
    reg_count = await db_conn.fetchval("SELECT COUNT(*) FROM regulatory_events;")
    assert reg_count == 90, f"Expected 90 regulatory events, got {reg_count}"

    # Verify REG-0001-001
    reg1 = await db_conn.fetchrow("SELECT hours_to_report, fine_usd, status FROM regulatory_events WHERE event_id = 'REG-0001-001';")
    assert reg1 is not None, "REG-0001-001 must exist"
    assert reg1["hours_to_report"] == 41.0, f"Expected 41.0 hours to report, got {reg1['hours_to_report']}"

    # Verify shared context notes
    notes_count = await db_conn.fetchval("SELECT COUNT(*) FROM shared_context;")
    assert notes_count >= 140, f"Expected at least 140 context notes, got {notes_count}"
