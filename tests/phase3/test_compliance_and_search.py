"""
Phase 3.1 Tests: Compliance Engine & Hybrid Search.

Validates:
- Evaluation Query Q9: 12-month rule breaches and open compliance actions for WELL-0001.
- Evaluation Query Q10: Southwest Block 24 uncontained spills in the last 90 days.
- FastEmbed vector indexing and hybrid cosine similarity search.
"""

import pytest
from datetime import date
from src.analytics.compliance_queries import (
    get_well_compliance_status,
    get_area_uncontained_spills
)
from src.retrieval.hybrid_search import search_documents


@pytest.mark.asyncio
async def test_q9_well_0001_compliance_status(db_conn):
    """
    Validates evaluation query Q9:
    - Exactly 4 rule breaches on WELL-0001 in the past 12 months.
    - USD 5,000 in open fines from notice of violation REG-0001-002.
    - Breach 1 (SR-01): 41 hours to report spill vs 24-hour limit.
    - Breach 2 (SR-02): Containment took about 7 hours vs 4-hour limit.
    - Breach 3 (SR-03): Overdue cleanup verification due 10 Aug 2026, still open (REG-0001-003).
    - Breach 4 (RC-04): 30-day NOV response due 30 Jul 2026, none recorded.
    - Pending action: Root-cause analysis due on flowline (3 corrective repairs in 12m).
    - Pending action: Planned shut-in from 7 Oct not yet recorded in maintenance.
    - Compliant rule: Yearly flowline test (RC-02) done on 7 Mar 2026.
    """
    status = await get_well_compliance_status(db_conn, "WELL-0001", as_of_date=date(2026, 10, 16))
    assert status is not None
    assert status["asset_id"] == "WELL-0001"
    assert status["total_breaches"] == 4, f"Expected 4 breaches, got {status['total_breaches']}"
    assert status["open_fines_usd"] == 5000.0, f"Expected 5,000 USD open fines, got {status['open_fines_usd']}"

    # Verify specific breach protocols
    breach_protocols = {b["protocol_id"]: b for b in status["breaches"]}
    assert "SR-01" in breach_protocols
    assert "SR-02" in breach_protocols
    assert "SR-03" in breach_protocols
    assert "RC-04" in breach_protocols

    # SR-01 details
    assert breach_protocols["SR-01"]["hours_to_report"] == 41.0
    assert breach_protocols["SR-01"]["fine_usd"] == 5000.0
    assert breach_protocols["SR-01"]["status"] == "open"

    # SR-02 details
    assert breach_protocols["SR-02"]["hours_to_contain"] == 7.0
    assert "MNT-0001-june-2026-flowline-spill.md" in breach_protocols["SR-02"]["report_file"]

    # SR-03 details
    assert breach_protocols["SR-03"]["status"] == "open"
    assert breach_protocols["SR-03"]["event_id"] == "REG-0001-003"

    # RC-04 details
    assert breach_protocols["RC-04"]["event_id"] == "REG-0001-002"
    assert breach_protocols["RC-04"]["response_due_date"] == date(2026, 7, 30)

    # Verify pending actions (RCA + planned shut-in)
    pending_types = {p["action_type"]: p for p in status["pending_actions"]}
    assert "root_cause_analysis" in pending_types
    rca = pending_types["root_cause_analysis"]
    assert rca["equipment_kind"] == "flowline"
    assert rca["corrective_repairs_count"] == 3
    assert set(rca["repair_ids"]) == {"MNT-0001-028", "MNT-0001-029", "MNT-0001-032"}

    assert "unrecorded_planned_shut_in" in pending_types
    shut_in = pending_types["unrecorded_planned_shut_in"]
    assert shut_in["note_id"] == "CTX-0001-003"

    # Verify compliant rules (RC-02)
    compliant_protocols = {c["protocol_id"]: c for c in status["compliant_rules"]}
    assert "RC-02" in compliant_protocols
    assert compliant_protocols["RC-02"]["test_date"] == date(2026, 3, 7)
    assert compliant_protocols["RC-02"]["maintenance_id"] == "MNT-0001-026"


@pytest.mark.asyncio
async def test_q10_area_uncontained_spills(db_conn):
    """
    Validates evaluation query Q10:
    - In Southwest Block 24, exactly 2 spills in the last 90 days exceeded the 4-hour containment limit.
    - WELL-0082: contained after 7.1 hours (MNT-0082-028, INS-0082-0198).
    - WELL-0100: contained after 8.1 hours (MNT-0100-034, INS-0100-0196).
    """
    spills = await get_area_uncontained_spills(
        db_conn,
        "Southwest Block 24",
        days=90,
        as_of_date=date(2026, 10, 16)
    )
    assert len(spills) == 2, f"Expected 2 uncontained spills, got {len(spills)}"

    well_map = {s["asset_id"]: s for s in spills}
    assert "WELL-0082" in well_map
    assert "WELL-0100" in well_map

    # Check WELL-0082 details
    s82 = well_map["WELL-0082"]
    assert s82["hours_to_contain"] == 7.1
    assert s82["inspection_id"] == "INS-0082-0198"
    assert "MNT-0082-028" in s82["report_file"]

    # Check WELL-0100 details
    s100 = well_map["WELL-0100"]
    assert s100["hours_to_contain"] == 8.1
    assert s100["inspection_id"] == "INS-0100-0196"
    assert "MNT-0100-034" in s100["report_file"]


@pytest.mark.asyncio
async def test_hybrid_search_documents(db_conn):
    """
    Validates semantic hybrid search over document sections using FastEmbed:
    - Finds SOP protocol for spill containment deadline (SR-02).
    - Finds June 2026 flowline spill report for WELL-0001.
    """
    # 1. Search for containment deadline
    sop_results = await search_documents(
        db_conn,
        query="spill containment deadline source stopped within 4 hours",
        doc_type="sop",
        limit=3
    )
    assert len(sop_results) > 0
    top_sop = sop_results[0]
    assert "SR-02" in top_sop["content"] or "4 hours" in top_sop["content"]
    assert top_sop["similarity"] > 0.5

    # 2. Search for WELL-0001 flowline corrosion failure
    report_results = await search_documents(
        db_conn,
        query="threaded coupling external corrosion failed protective wrap pinhole",
        asset_id="WELL-0001",
        doc_type="maintenance_report",
        limit=3
    )
    assert len(report_results) > 0
    top_report = report_results[0]
    assert top_report["asset_id"] == "WELL-0001"
    assert "MNT-0001" in top_report["section_title"] or "coupling" in top_report["content"].lower()
    assert top_report["similarity"] > 0.5


@pytest.mark.asyncio
async def test_dynamic_generalization_across_other_assets(db_conn):
    """
    Validates autonomous execution on arbitrary assets and dates without relying on hardcoded values:
    - WELL-0082 compliance status resolves dynamically from database records.
    - Status evaluation works with dynamic date resolution (as_of_date=None).
    - Spill aggregations correctly handle other years (e.g. 2025) across full 12 months.
    """
    from src.analytics.domain_queries import get_well_current_status, aggregate_spills_matrix

    # 1. Dynamic compliance evaluation on a different well (WELL-0082)
    status_82 = await get_well_compliance_status(db_conn, "WELL-0082")
    assert status_82 is not None
    assert status_82["asset_id"] == "WELL-0082"
    assert isinstance(status_82["breaches"], list)
    assert isinstance(status_82["pending_actions"], list)

    # 2. Dynamic status evaluation without passing explicit dates
    status_random = await get_well_current_status(db_conn, "WELL-0050")
    assert status_random is not None
    assert status_random["asset_id"] == "WELL-0050"
    assert isinstance(status_random["is_producing"], bool)
    assert isinstance(status_random["is_status_stale"], bool)

    # 3. Aggregation across past year (2025) handles all 12 months dynamically
    matrix_2025 = await aggregate_spills_matrix(db_conn, year=2025)
    assert matrix_2025["year"] == 2025
    assert matrix_2025["max_month"] == 12
    assert len(matrix_2025["rows"]) == 4
    for r in matrix_2025["rows"]:
        assert len(r["months"]) == 12

