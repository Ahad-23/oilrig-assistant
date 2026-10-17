"""
Phase 3.2 Tests: Two-Level Memory, Dynamic Policy Overrides, and Conflict Detection.

Validates:
- Q11 & Q16: Private user session memory isolation (Michael Turner vs Jessica Reed) and repair cost tracking.
- Q12: Raw data correction for INS-0164-0205, delta recalculation, and inspector note contradiction detection.
- Q13: AI spill estimate correction for INS-0151-0201 with cascading SR-01 / SR-03 regulatory duties.
- Q14: Dynamic policy rule override for T350 wells altering RCA thresholds (adds WELL-0120, excludes WELL-0102).
- Q15: Shared propagation of corrections across other users (Jessica Reed, Laura Simmons).
- Q17: Physical sensor data contradicting user claims (WELL-0175 and WELL-0001).
- Q18: Disagreements between field staff on AI detections (WELL-0101 produced water vs crude).
"""

import pytest
from datetime import date
from src.memory.shared_context import (
    apply_raw_data_correction,
    apply_ai_estimate_correction,
    apply_policy_override,
    record_shared_context_note,
    get_wells_needing_rca,
    get_reportable_spills
)
from src.memory.session_store import SessionStore
from src.analytics.conflict_detector import (
    evaluate_claim_against_sensors,
    evaluate_spill_detection_disagreement
)
from src.analytics.domain_queries import get_area_non_producing_wells


@pytest.mark.asyncio
async def test_q11_and_q16_session_memory_isolation(db_conn):
    """
    Validates Q11 and Q16:
    - User A (Michael Turner, U-201) records discussed wells from Q6 in session 1.
    - Follow-up query retrieves repair costs for 2026 (WELL-0121: $25,794, WELL-0138: $46,942, WELL-0107: $5,176).
    - User B (Jessica Reed, U-202) asking for 'the three wells we discussed' finds zero session context.
    """
    store = SessionStore.get_instance()
    user_a = "U-201" # Michael Turner
    user_b = "U-202" # Jessica Reed
    session_a = "thread_turner_q6"
    session_b = "thread_reed_q16"

    # Clean sessions
    store.clear_user_sessions(user_a)
    store.clear_user_sessions(user_b)

    # 1. Day 1: Michael Turner discusses Q6 top 3 wells
    top_3_wells = ["WELL-0121", "WELL-0138", "WELL-0107"]
    store.record_turn(
        user_id=user_a,
        session_id=session_a,
        user_query="Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months?",
        narrative_response="Top 3 wells are WELL-0121, WELL-0138, and WELL-0107.",
        discussed_assets=top_3_wells
    )

    # 2. Day 2: Michael Turner follows up in his session
    assert store.has_prior_conversation(user_a, session_a) is True
    retrieved_wells = store.get_discussed_assets(user_a, session_a)
    assert retrieved_wells == top_3_wells

    # Compute repair costs for 2026 for these wells
    costs = {}
    for asset_id in retrieved_wells:
        total = await db_conn.fetchval("""
            SELECT COALESCE(SUM(cost_total), 0)::float
            FROM maintenance
            WHERE asset_id = $1 
              AND EXTRACT(YEAR FROM started_at) = 2026;
        """, asset_id)
        costs[asset_id] = round(total)

    assert costs["WELL-0121"] == 25794, f"Expected 25,794 USD for WELL-0121, got {costs['WELL-0121']}"
    assert costs["WELL-0138"] == 46942, f"Expected 46,942 USD for WELL-0138, got {costs['WELL-0138']}"
    assert costs["WELL-0107"] == 5176, f"Expected 5,176 USD for WELL-0107, got {costs['WELL-0107']}"

    # 3. Q16: Jessica Reed asks the identical question in her session
    assert store.has_prior_conversation(user_b, session_b) is False
    assert store.get_discussed_assets(user_b, session_b) == []


@pytest.mark.asyncio
async def test_q12_raw_data_correction_and_conflict(db_conn):
    """
    Validates Q12:
    - Michael Turner corrects INS-0164-0205 wellhead reading from 24.0 C to 41.0 C.
    - Production delta updates to 21.1 C >= 15.0 C (producing).
    - Inspector note contradiction flagged ('Pump jack not moving.' by Tyler Hughes).
    - Re-querying Q2 returns 3 wells (WELL-0170, WELL-0172, WELL-0175), excluding WELL-0164.
    """
    res = await apply_raw_data_correction(
        db_conn,
        author_user_id="U-201",
        inspection_id="INS-0164-0205",
        corrected_wellhead_temp_c=41.0,
        reason="Handheld thermal gun was faulty; re-measured at 41.0 C."
    )
    assert res["is_producing"] is True
    assert res["new_delta_temp_c"] == 21.1
    assert res["has_inspector_conflict"] is True
    assert "not moving" in res["inspector_note"].lower()

    # Re-run Q2: area non-producing wells in Northeast Block 8
    non_prod = await get_area_non_producing_wells(db_conn, "Northeast Block 8")
    asset_ids = [w["asset_id"] for w in non_prod]

    assert len(non_prod) == 3, f"Expected 3 non-producing wells after correction, got {len(non_prod)}"
    assert "WELL-0164" not in asset_ids
    assert set(asset_ids) == {"WELL-0170", "WELL-0172", "WELL-0175"}


@pytest.mark.asyncio
async def test_q13_ai_estimate_correction_and_cascades(db_conn):
    """
    Validates Q13:
    - Michael Turner corrects INS-0151-0201 spill volume from 4.5 bbl to 5.4 bbl.
    - At 5.4 bbl, spill becomes reportable (>= 5.0 bbl).
    - Flags SR-01 written notice breach (due within 24h of discovery, none on record).
    - Flags SR-03 agency soil remediation verification due within 60 days (by 23 Nov 2026).
    """
    res = await apply_ai_estimate_correction(
        db_conn,
        author_user_id="U-201",
        inspection_id="INS-0151-0201",
        corrected_volume_bbl=5.4,
        reason="Field crew measured 5.4 bbl on pad."
    )
    assert res["is_reportable"] is True
    assert res["is_sr01_breach"] is True
    assert res["verification_due_date"] == date(2026, 11, 23)

    # Q15 check: Laura Simmons queries reportable spills in Northeast Block 8
    rep_spills = await get_reportable_spills(db_conn, "Northeast Block 8", days=90)
    assert len(rep_spills) == 1
    assert rep_spills[0]["asset_id"] == "WELL-0151"
    assert rep_spills[0]["volume_bbl"] == 5.4


@pytest.mark.asyncio
async def test_q14_dynamic_policy_override_t350_rca(db_conn):
    """
    Validates Q14:
    - Baseline: pump jack RCA check in Northeast Block 7 returns WELL-0108, WELL-0121, WELL-0138 (3 repairs).
    - Michael Turner sets policy rule: T350 wells trigger RCA after 2 repairs, not 3.
    - Post-rule: WELL-0120 (T350 with 2 repairs) is added.
    - Post-rule: WELL-0102 (T200 with 2 repairs) is NOT added.
    """
    # 1. Baseline
    baseline = await get_wells_needing_rca(db_conn, "Northeast Block 7", "pump_jack")
    baseline_ids = [w["asset_id"] for w in baseline]
    assert set(baseline_ids) == {"WELL-0108", "WELL-0121", "WELL-0138"}

    # 2. Apply dynamic rule for T350 wells
    await apply_policy_override(
        db_conn,
        author_user_id="U-201",
        scope="well_type",
        target_id="T350",
        policy_key="rca_repairs_threshold",
        new_value=2,
        reason="Our team now wants a pump jack root-cause analysis after 2 repairs, not 3."
    )

    # 3. Re-evaluate with dynamic rule
    updated = await get_wells_needing_rca(db_conn, "Northeast Block 7", "pump_jack")
    updated_ids = [w["asset_id"] for w in updated]

    assert set(updated_ids) == {"WELL-0108", "WELL-0120", "WELL-0121", "WELL-0138"}
    assert "WELL-0120" in updated_ids

    # Verify WELL-0102 (T200 with 2 repairs) was not added
    assert "WELL-0102" not in updated_ids


@pytest.mark.asyncio
async def test_q17_sensor_data_vs_user_claim_conflict(db_conn):
    """
    Validates Q17:
    - Tyler Hughes claims 'WELL-0175 is running fine'.
    - Physical inspection shows delta 0.4 C (not producing). Flagged as unconfirmed conflict.
    - Jake Morales claims 'WELL-0001 is back online since 14 Oct'.
    - Physical inspection shows delta 3.2 C (not producing). Flagged as unconfirmed conflict.
    """
    res_175 = await evaluate_claim_against_sensors(
        db_conn,
        asset_id="WELL-0175",
        claimed_status="running fine",
        author_user_id="U-204"
    )
    assert res_175["has_conflict"] is True
    assert res_175["is_confirmed"] is False
    assert res_175["delta_temp_c"] == 0.4
    assert res_175["actual_is_producing"] is False

    res_001 = await evaluate_claim_against_sensors(
        db_conn,
        asset_id="WELL-0001",
        claimed_status="back online",
        author_user_id="U-102"
    )
    assert res_001["has_conflict"] is True
    assert res_001["is_confirmed"] is False
    assert res_001["actual_is_producing"] is False


@pytest.mark.asyncio
async def test_q18_spill_detection_disagreement_transparency(db_conn):
    """
    Validates Q18:
    - User asks if 20 Aug spill on WELL-0101 was real oil.
    - Context notes show disagreement between Ryan Brooks (produced water) and Chris Dalton (crude).
    - Copilot confirms detection stands (spill repair MNT-0101-029 done, no formal correction),
      but displays both sources honestly.
    """
    res = await evaluate_spill_detection_disagreement(
        db_conn,
        asset_id="WELL-0101",
        inspection_id="INS-0101-0197"
    )
    assert res["detection_stands"] is True
    assert res["disagreement_detected"] is True
    assert len(res["opinions"]) >= 2
    authors = [o["author"] for o in res["opinions"]]
    assert any("Brooks" in a for a in authors)
    assert any("Dalton" in a for a in authors)
    assert res["repair"] is not None
    assert res["repair"]["maintenance_id"] == "MNT-0101-029"
