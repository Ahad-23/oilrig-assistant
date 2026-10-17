import asyncio
import time
from pathlib import Path
from src.config import settings
from src.db.connection import init_db, get_raw_asyncpg_connection
from src.ingestion.parser import DatasetParser

async def run_ingestion_pipeline(dataset_dir: Path = settings.DATASET_DIR) -> dict:
    """
    Executes high-speed asynchronous ingestion of all fleet and asset data.
    Uses asyncpg copy_records_to_table for maximum throughput (< 5 seconds).
    """
    start_time = time.time()
    print(f"[*] Starting ingestion from {dataset_dir}...")

    # 1. Initialize schema
    await init_db()
    conn = await get_raw_asyncpg_connection()

    try:
        parser = DatasetParser(dataset_dir)

        # 2. Parse Fleet & Rules
        fleet = parser.parse_fleet()
        well_types = fleet["well_types"]
        threshold_map = {wt["well_type"]: wt["min_producing_temp_delta_c"] for wt in well_types}

        # Clear existing data for idempotent re-runs
        await conn.execute("""
            TRUNCATE shared_context, document_sections, regulatory_events,
                     maintenance_report_metrics, maintenance, inspections,
                     equipment, wells, well_type_rules, fleet_areas, fleet_users, fleet_teams
            CASCADE;
        """)

        # Insert Teams
        teams_records = [(t["team_id"], t["name"], t.get("lead_user_id", "U-101")) for t in fleet["teams"]]
        await conn.copy_records_to_table("fleet_teams", records=teams_records, columns=["team_id", "name", "lead_user_id"])

        # Insert Users
        users_records = [(u["user_id"], u["name"], u["role"], u.get("team_id")) for u in fleet["users"]]
        await conn.copy_records_to_table("fleet_users", records=users_records, columns=["user_id", "name", "role", "team_id"])

        # Insert Areas
        areas_records = [
            (a["area_id"], a["name"], a["team_id"], a["center"]["lat"], a["center"]["lon"])
            for a in fleet["areas"]
        ]
        await conn.copy_records_to_table("fleet_areas", records=areas_records, columns=["area_id", "name", "team_id", "center_lat", "center_lon"])

        # Insert Well Type Rules
        wt_records = [
            (wt["well_type"], wt["name"], wt["min_producing_temp_delta_c"], wt["temp_alarm_threshold_c"], wt["default_rca_repairs_threshold"], wt["manual_doc_path"])
            for wt in well_types
        ]
        await conn.copy_records_to_table("well_type_rules", records=wt_records, columns=["well_type", "name", "min_producing_temp_delta_c", "temp_alarm_threshold_c", "default_rca_repairs_threshold", "manual_doc_path"])

        # 3. Parse Context Notes, False Positives & Data Corrections
        notes, false_positives, data_corrections = parser.parse_context_notes()

        # 4. Parse Wells & Time Series with dynamic date-aware thresholds and corrections
        assets_data = parser.parse_well_assets(threshold_map, false_positives, data_corrections)

        # Insert Wells
        wells_records = [
            (
                w["asset_id"], w["name"], w["asset_category"], w["well_type"],
                w["area_id"], w["team_id"], w["in_charge_user_id"],
                w["lat"], w["lon"], w["installed_on"], w["recorded_status"],
                w["type_history"], w["team_history"], w["status"], w["decommissioned_on"]
            )
            for w in assets_data["wells"]
        ]
        await conn.copy_records_to_table(
            "wells",
            records=wells_records,
            columns=[
                "asset_id", "name", "asset_category", "well_type",
                "area_id", "team_id", "in_charge_user_id",
                "lat", "lon", "installed_on", "recorded_status",
                "type_history", "team_history", "status", "decommissioned_on"
            ]
        )

        # Insert Equipment
        equipment_records = [
            (e["equipment_id"], e["asset_id"], e["kind"], e["model"])
            for e in assets_data["equipment"]
        ]
        await conn.copy_records_to_table("equipment", records=equipment_records, columns=["equipment_id", "asset_id", "kind", "model"])

        # Insert Inspections
        inspections_records = [
            (
                i["inspection_id"], i["asset_id"], i["inspected_at"], i["inspector_user_id"],
                i["method"], i["ambient_temp_c"], i["wellhead_temp_c"], i["delta_temp_c"],
                i["is_producing"], i["spill_detected"], i["spill_area_pct"],
                i["spill_est_volume_bbl"], i["notes"], i["is_false_positive_spill"],
                i["recorded_at"]
            )
            for i in assets_data["inspections"]
        ]
        await conn.copy_records_to_table(
            "inspections",
            records=inspections_records,
            columns=[
                "inspection_id", "asset_id", "inspected_at", "inspector_user_id",
                "method", "ambient_temp_c", "wellhead_temp_c", "delta_temp_c",
                "is_producing", "spill_detected", "spill_area_pct",
                "spill_est_volume_bbl", "notes", "is_false_positive_spill",
                "recorded_at"
            ]
        )

        # Insert Maintenance
        maint_records = [
            (
                m["maintenance_id"], m["asset_id"], m["started_at"], m["completed_at"],
                m["maintenance_type"], m["equipment_kind"], m["issue"], m["action_taken"],
                m["technician_user_id"], m["contractor"], m["downtime_hours"],
                m["cost_labor"], m["cost_parts"], m["cost_total"],
                m["triggered_by_inspection_id"], m["report_file"],
                m["recorded_at"], m["cost_revision"]
            )
            for m in assets_data["maintenance"]
        ]
        await conn.copy_records_to_table(
            "maintenance",
            records=maint_records,
            columns=[
                "maintenance_id", "asset_id", "started_at", "completed_at",
                "maintenance_type", "equipment_kind", "issue", "action_taken",
                "technician_user_id", "contractor", "downtime_hours",
                "cost_labor", "cost_parts", "cost_total",
                "triggered_by_inspection_id", "report_file",
                "recorded_at", "cost_revision"
            ]
        )

        # Insert Maintenance Report Metrics
        report_records = [
            (
                rm["report_file"], rm["maintenance_id"], rm["asset_id"], rm["triggered_by_inspection_id"],
                rm["hours_to_contain"], rm["hours_to_report"], rm["sr01_status"],
                rm["sr02_status"], rm["sr03_status"], None, rm["highest_tph_pct"],
                None, rm["summary_fix"], rm["parts_installed"], rm["follow_up"]
            )
            for rm in assets_data["report_metrics"]
        ]
        await conn.copy_records_to_table(
            "maintenance_report_metrics",
            records=report_records,
            columns=[
                "report_file", "maintenance_id", "asset_id", "triggered_by_inspection_id",
                "hours_to_contain", "hours_to_report", "sr01_status",
                "sr02_status", "sr03_status", "ws05_tested_psi", "highest_tph_pct",
                "total_cost_usd", "summary_fix", "parts_installed", "follow_up"
            ]
        )

        # Link maintenance_report_metrics with maintenance records
        await conn.execute("""
            UPDATE maintenance_report_metrics mrm
            SET maintenance_id = m.maintenance_id,
                triggered_by_inspection_id = m.triggered_by_inspection_id,
                total_cost_usd = m.cost_total
            FROM maintenance m
            WHERE mrm.report_file LIKE '%' || m.report_file;
        """)

        # Insert Regulatory Events
        reg_records = [
            (
                r["event_id"], r["asset_id"], r["date"], r["agency"],
                r["event_type"], r["protocol_id"], r["related_inspection_id"],
                r["hours_to_report"], r["fine_usd"], r["status"], r["detail"]
            )
            for r in assets_data["regulatory_events"]
        ]
        await conn.copy_records_to_table(
            "regulatory_events",
            records=reg_records,
            columns=[
                "event_id", "asset_id", "date", "agency", "event_type",
                "protocol_id", "related_inspection_id", "hours_to_report",
                "fine_usd", "status", "detail"
            ]
        )

        # Insert Shared Context Notes
        notes_records = [
            (
                n["note_id"], n["created_at"], n["author_user_id"], n["scope"],
                n["target_id"], n["note_type"], n["original_value"], n["corrected_value"],
                n["text"], n["valid_from"], n["valid_to"], n["is_confirmed"]
            )
            for n in notes
        ]
        await conn.copy_records_to_table(
            "shared_context",
            records=notes_records,
            columns=[
                "note_id", "created_at", "author_user_id", "scope",
                "target_id", "note_type", "original_value", "corrected_value",
                "text", "valid_from", "valid_to", "is_confirmed"
            ]
        )

        # Insert Document Sections (SOPs + Manuals + Reports)
        all_docs = assets_data["document_sections"] + parser.parse_sops() + parser.parse_manuals()
        docs_records = [
            (d["doc_type"], d["doc_path"], d["asset_id"], d["section_title"], d["content"], d["metadata"])
            for d in all_docs
        ]
        await conn.copy_records_to_table(
            "document_sections",
            records=docs_records,
            columns=["doc_type", "doc_path", "asset_id", "section_title", "content", "metadata"]
        )

        # Generate vector embeddings for hybrid retrieval
        from src.retrieval.embeddings import populate_document_embeddings
        print("[*] Generating dense vector embeddings for document sections...")
        try:
            embedded_count = await populate_document_embeddings(conn, batch_size=128)
            print(f"[+] Successfully generated embeddings for {embedded_count} document sections.")
        except Exception as e:
            print(f"[!] Warning: Vector embedding generation failed ({e}), continuing with textual data.")

        elapsed = round(time.time() - start_time, 2)
        summary = {
            "elapsed_seconds": elapsed,
            "wells_count": len(wells_records),
            "inspections_count": len(inspections_records),
            "maintenance_count": len(maint_records),
            "reports_count": len(report_records),
            "regulatory_events_count": len(reg_records),
            "context_notes_count": len(notes_records),
            "document_sections_count": len(docs_records)
        }
        print(f"[+] Ingestion completed in {elapsed}s: {summary}")
        return summary

    finally:
        await conn.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingest oil field dataset into PostgreSQL")
    parser.add_argument("--data-dir", type=Path, default=settings.DATASET_DIR, help="Path to sample-data or test dataset directory")
    args = parser.parse_args()
    asyncio.run(run_ingestion_pipeline(args.data_dir))
