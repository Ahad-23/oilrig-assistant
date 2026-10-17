import json
import re
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple, Set

def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    # Handle ISO 8601 strings (e.g. 2026-10-15T09:45:00Z)
    dt_str = dt_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None

def parse_iso_date(d_str: Optional[str]) -> Optional[date]:
    if not d_str:
        return None
    try:
        return date.fromisoformat(d_str.split("T")[0])
    except Exception:
        return None

class DatasetParser:
    """Production-grade parser for oil field dataset."""

    def __init__(self, dataset_dir: Path):
        self.dataset_dir = dataset_dir
        self.fleet_dir = dataset_dir / "fleet"
        self.assets_dir = dataset_dir / "assets"

    def parse_fleet(self) -> Dict[str, Any]:
        """Parses areas, teams, users, and well-type manuals."""
        # 1. Areas and Teams
        areas_file = self.fleet_dir / "areas.json"
        with open(areas_file, "r", encoding="utf-8") as f:
            areas_data = json.load(f)

        teams = areas_data.get("teams", [])
        areas = areas_data.get("areas", [])

        # 2. Users
        users_file = self.fleet_dir / "users.json"
        with open(users_file, "r", encoding="utf-8") as f:
            users_data = json.load(f)
        users = users_data.get("users", [])

        # 3. Well-type manuals (extract thresholds dynamically)
        well_types = []
        well_types_dir = self.fleet_dir / "well-types"
        if well_types_dir.exists():
            for manual_file in well_types_dir.glob("*.md"):
                wt_code = manual_file.stem  # e.g. 'T200', 'T350', 'T500'
                content = manual_file.read_text(encoding="utf-8")
                
                # Dynamic threshold extraction (supports optional markdown formatting like **)
                delta_match = re.search(r"at least\s*(?:\*\*)?(\d+(?:\.\d+)?)\s*(?:\*\*)?\s*°?C\s+above\s+ambient", content, re.IGNORECASE)
                default_delta = 25.0 if wt_code == "T500" else (20.0 if wt_code == "T350" else 15.0)
                min_delta = float(delta_match.group(1)) if delta_match else default_delta

                alarm_match = re.search(r"at or below\s*(?:\*\*)?(\d+(?:\.\d+)?)\s*(?:\*\*)?\s*°?C", content, re.IGNORECASE)
                default_alarm = 95.0 if wt_code in ("T500", "T350") else 85.0
                alarm_temp = float(alarm_match.group(1)) if alarm_match else default_alarm

                # RCA escalation threshold: 2 for ESP / T500, 3 for rod-lift
                rca_match = re.search(r"(?:two|2)\s+or\s+more.*?corrective.*?require\s+(?:a\s+)?root-cause", content, re.IGNORECASE)
                default_rca = 2 if (wt_code == "T500" or rca_match) else 3

                well_name = f"{wt_code} ESP Well" if wt_code == "T500" else f"{wt_code} Rod-Lift Well"

                well_types.append({
                    "well_type": wt_code,
                    "name": well_name,
                    "min_producing_temp_delta_c": min_delta,
                    "temp_alarm_threshold_c": alarm_temp,
                    "default_rca_repairs_threshold": default_rca,
                    "manual_doc_path": str(manual_file.relative_to(self.dataset_dir)).replace("\\", "/")
                })

        return {
            "teams": teams,
            "areas": areas,
            "users": users,
            "well_types": well_types
        }

    def parse_context_notes(self) -> Tuple[List[Dict[str, Any]], Set[str], Dict[str, Dict[str, Any]]]:
        """
        Parses all context.jsonl files across all wells.
        Returns:
            all_notes: list of context dicts for shared_context table
            false_positive_inspections: set of inspection_ids that are false positive spills
            data_corrections_map: map of inspection_id -> {field: corrected_value}
        """
        all_notes = []
        false_positive_inspections = set()
        data_corrections_map: Dict[str, Dict[str, Any]] = {}

        for well_dir in self.assets_dir.glob("WELL-*"):
            context_file = well_dir / "context.jsonl"
            if not context_file.exists():
                continue

            with open(context_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    note = json.loads(line)
                    asset_id = note.get("asset_id", well_dir.name)
                    note_id = note.get("note_id")
                    note_type = note.get("note_type")
                    text = note.get("text", "")
                    inspection_id = note.get("inspection_id")
                    field = note.get("field")
                    orig_val = note.get("original_value")
                    corr_val = note.get("corrected_value")

                    # Check for false-positive spill corrections
                    if note_type in ("correction", "data_correction") and inspection_id:
                        lower_text = text.lower()
                        if (
                            "not a crude spill" in lower_text
                            or "not a spill" in lower_text
                            or "rainwater" in lower_text
                            or "shadow" in lower_text
                            or "produced water" in lower_text
                            or "wet soil" in lower_text
                            or "mud" in lower_text
                        ):
                            false_positive_inspections.add(inspection_id)

                    # Track data corrections for inspection readings
                    if note_type == "data_correction" and inspection_id and field:
                        if inspection_id not in data_corrections_map:
                            data_corrections_map[inspection_id] = {}
                        data_corrections_map[inspection_id][field] = corr_val

                    # Prepare original and corrected JSON values
                    if note_type == "data_correction" and field:
                        orig_json = json.dumps({field: orig_val})
                        corr_json = json.dumps({field: corr_val})
                    elif inspection_id:
                        orig_json = json.dumps({"inspection_id": inspection_id})
                        corr_json = json.dumps({"is_false_positive": True}) if inspection_id in false_positive_inspections else None
                    else:
                        orig_json = None
                        corr_json = None

                    all_notes.append({
                        "note_id": note_id,
                        "created_at": parse_iso_datetime(note.get("created_at")),
                        "author_user_id": note.get("author_user_id"),
                        "scope": "inspection" if inspection_id else "asset",
                        "target_id": inspection_id if inspection_id else asset_id,
                        "note_type": note_type,
                        "original_value": orig_json,
                        "corrected_value": corr_json,
                        "text": text,
                        "valid_from": parse_iso_date(note.get("valid_from")),
                        "valid_to": parse_iso_date(note.get("valid_to")),
                        "is_confirmed": True
                    })

        return all_notes, false_positive_inspections, data_corrections_map

    def parse_well_assets(
        self,
        well_type_thresholds: Dict[str, float],
        false_positives: Set[str],
        data_corrections: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Parses metadata, equipment, inspections, maintenance, reports, and regulatory events for all wells."""
        if data_corrections is None:
            data_corrections = {}

        wells_list = []
        equipment_list = []
        inspections_list = []
        maintenance_list = []
        regulatory_list = []
        report_metrics_list = []
        document_sections_list = []

        for well_dir in sorted(self.assets_dir.glob("WELL-*")):
            asset_id = well_dir.name

            # 1. Metadata & Equipment
            meta_file = well_dir / "metadata.json"
            meta = {}
            if meta_file.exists():
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)

                well_type = meta.get("well_type", "T200")
                type_history = meta.get("type_history")
                team_history = meta.get("team_history")
                status = meta.get("status")
                decommissioned_on = parse_iso_date(meta.get("decommissioned_on"))

                loc = meta.get("location", {})
                wells_list.append({
                    "asset_id": asset_id,
                    "name": meta.get("name", asset_id),
                    "asset_category": meta.get("asset_category", "oil_well"),
                    "well_type": well_type,
                    "area_id": meta.get("area_id"),
                    "team_id": meta.get("team_id"),
                    "in_charge_user_id": meta.get("in_charge_user_id"),
                    "lat": loc.get("lat", 0.0),
                    "lon": loc.get("lon", 0.0),
                    "installed_on": parse_iso_date(meta.get("installed_on")),
                    "recorded_status": meta.get("recorded_status", "active"),
                    "type_history": json.dumps(type_history) if type_history else None,
                    "team_history": json.dumps(team_history) if team_history else None,
                    "status": status,
                    "decommissioned_on": decommissioned_on
                })

                for eq in meta.get("equipment", []):
                    equipment_list.append({
                        "equipment_id": eq.get("equipment_id"),
                        "asset_id": asset_id,
                        "kind": eq.get("kind"),
                        "model": eq.get("model")
                    })

            # 2. Inspections
            insp_file = well_dir / "inspections.jsonl"
            if insp_file.exists():
                with open(insp_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        insp = json.loads(line)
                        insp_id = insp.get("inspection_id")
                        insp_dt = parse_iso_datetime(insp.get("inspected_at"))
                        recorded_at = parse_iso_datetime(insp.get("recorded_at"))
                        amb = float(insp.get("ambient_temp_c", 0.0))
                        wh = float(insp.get("wellhead_temp_c", 0.0))
                        spill_vol = insp.get("spill_est_volume_bbl")
                        if spill_vol is not None:
                            spill_vol = float(spill_vol)

                        # Apply data corrections if logged in context.jsonl
                        if insp_id in data_corrections:
                            corr_dict = data_corrections[insp_id]
                            if "wellhead_temp_c" in corr_dict:
                                wh = float(corr_dict["wellhead_temp_c"])
                            if "spill_est_volume_bbl" in corr_dict:
                                spill_vol = float(corr_dict["spill_est_volume_bbl"])

                        # Determine effective well type on inspection date via type_history
                        effective_wt = meta.get("well_type", "T200")
                        type_history = meta.get("type_history")
                        if type_history and insp_dt:
                            insp_d = insp_dt.date()
                            for th in type_history:
                                f_d = parse_iso_date(th.get("from"))
                                t_d = parse_iso_date(th.get("to"))
                                if f_d and insp_d < f_d:
                                    continue
                                if t_d and insp_d > t_d:
                                    continue
                                effective_wt = th.get("well_type", effective_wt)
                                break

                        threshold = well_type_thresholds.get(effective_wt, 15.0)
                        delta = round(wh - amb, 2)
                        is_prod = delta >= threshold
                        is_fp = insp_id in false_positives

                        inspections_list.append({
                            "inspection_id": insp_id,
                            "asset_id": asset_id,
                            "inspected_at": insp_dt,
                            "inspector_user_id": insp.get("inspector_user_id"),
                            "method": insp.get("method", "drone"),
                            "ambient_temp_c": amb,
                            "wellhead_temp_c": wh,
                            "delta_temp_c": delta,
                            "is_producing": is_prod,
                            "spill_detected": bool(insp.get("spill_detected", False)),
                            "spill_area_pct": insp.get("spill_area_pct"),
                            "spill_est_volume_bbl": spill_vol,
                            "notes": insp.get("notes"),
                            "is_false_positive_spill": is_fp,
                            "recorded_at": recorded_at
                        })

            # 3. Maintenance
            maint_file = well_dir / "maintenance.jsonl"
            if maint_file.exists():
                with open(maint_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        m = json.loads(line)
                        cost = m.get("cost_usd", {})
                        recorded_at = parse_iso_datetime(m.get("recorded_at"))
                        cost_rev = json.dumps(m["cost_revision"]) if m.get("cost_revision") else None

                        maintenance_list.append({
                            "maintenance_id": m.get("maintenance_id"),
                            "asset_id": asset_id,
                            "started_at": parse_iso_datetime(m.get("started_at")),
                            "completed_at": parse_iso_datetime(m.get("completed_at")),
                            "maintenance_type": m.get("maintenance_type", "corrective"),
                            "equipment_kind": m.get("equipment_kind"),
                            "issue": m.get("issue", ""),
                            "action_taken": m.get("action_taken", ""),
                            "technician_user_id": m.get("technician_user_id"),
                            "contractor": m.get("contractor"),
                            "downtime_hours": m.get("downtime_hours"),
                            "cost_labor": cost.get("labor", 0.0),
                            "cost_parts": cost.get("parts", 0.0),
                            "cost_total": cost.get("total", 0.0),
                            "triggered_by_inspection_id": m.get("triggered_by_inspection_id"),
                            "report_file": m.get("report_file"),
                            "recorded_at": recorded_at,
                            "cost_revision": cost_rev
                        })

            # 4. Maintenance Reports (Extract metrics & document sections)
            reports_dir = well_dir / "maintenance-reports"
            if reports_dir.exists():
                for report_file in reports_dir.glob("*.md"):
                    content = report_file.read_text(encoding="utf-8")
                    rel_report_path = str(report_file.relative_to(self.dataset_dir)).replace("\\", "/")

                    # Extract metrics
                    hours_contain = None
                    contain_match = re.search(r"contained\s+(?:about\s+)?(\d+(?:\.\d+)?)\s*hours", content, re.IGNORECASE)
                    if contain_match:
                        hours_contain = float(contain_match.group(1))

                    hours_report = None
                    rep_match = re.search(r"reported.*?(\d+(?:\.\d+)?)\s*hours\s+after\s+detection", content, re.IGNORECASE)
                    if rep_match:
                        hours_report = float(rep_match.group(1))

                    # Compliance table parser
                    sr01_status = None
                    sr02_status = None
                    sr03_status = None
                    tph_val = None

                    if "SR-01" in content:
                        sr01_m = re.search(r"\|\s*SR-01\s*\|\s*\*\*?(Met|Not met)\*\*?\s*\|", content, re.IGNORECASE)
                        if sr01_m:
                            sr01_status = "met" if "not" not in sr01_m.group(1).lower() else "not_met"

                    if "SR-02" in content:
                        sr02_m = re.search(r"\|\s*SR-02\s*\|\s*\*\*?(Met|Not met)\*\*?\s*\|", content, re.IGNORECASE)
                        if sr02_m:
                            sr02_status = "met" if "not" not in sr02_m.group(1).lower() else "not_met"

                    if "SR-03" in content:
                        sr03_m = re.search(r"\|\s*SR-03\s*\|\s*\*\*?(Met|Not met|In progress)\*\*?\s*\|", content, re.IGNORECASE)
                        if sr03_m:
                            sr03_raw = sr03_m.group(1).lower()
                            sr03_status = "in_progress" if "progress" in sr03_raw else ("not_met" if "not" in sr03_raw else "met")

                    tph_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*TPH", content, re.IGNORECASE)
                    if tph_match:
                        tph_val = float(tph_match.group(1))

                    # Extract Parts installed
                    parts_installed = None
                    parts_match = re.search(r"\*\*Parts installed:\*\*\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
                    if parts_match:
                        raw_parts = parts_match.group(1).strip()
                        model_m = re.search(r"^(.*?),\s*serial", raw_parts, re.IGNORECASE)
                        serial_m = re.search(r"serial\s+([A-Z0-9-]+)", raw_parts, re.IGNORECASE)
                        lot_m = re.search(r"lot\s+([A-Z0-9-]+)", raw_parts, re.IGNORECASE)
                        parts_installed = {
                            "raw": raw_parts,
                            "model": model_m.group(1).strip() if model_m else None,
                            "serial": serial_m.group(1).strip() if serial_m else None,
                            "lot": lot_m.group(1).strip() if lot_m else None
                        }

                    # Extract Follow-up
                    follow_up = None
                    fu_match = re.search(r"\*\*Follow-up:\*\*\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
                    if fu_match:
                        raw_fu = fu_match.group(1).strip()
                        days_m = re.search(r"within\s+(\d+)\s+days", raw_fu, re.IGNORECASE)
                        follow_up = {
                            "raw": raw_fu,
                            "days": int(days_m.group(1)) if days_m else None,
                            "action": raw_fu
                        }

                    report_metrics_list.append({
                        "report_file": rel_report_path,
                        "maintenance_id": None, # Linked in DB pipeline
                        "asset_id": asset_id,
                        "triggered_by_inspection_id": None,
                        "hours_to_contain": hours_contain,
                        "hours_to_report": hours_report,
                        "sr01_status": sr01_status,
                        "sr02_status": sr02_status,
                        "sr03_status": sr03_status,
                        "highest_tph_pct": tph_val,
                        "summary_fix": None,
                        "parts_installed": json.dumps(parts_installed) if parts_installed else None,
                        "follow_up": json.dumps(follow_up) if follow_up else None
                    })

                    # Document section chunk for hybrid search
                    document_sections_list.append({
                        "doc_type": "maintenance_report",
                        "doc_path": rel_report_path,
                        "asset_id": asset_id,
                        "section_title": report_file.stem,
                        "content": content,
                        "metadata": json.dumps({
                            "asset_id": asset_id,
                            "report_file": rel_report_path,
                            "hours_to_contain": hours_contain,
                            "sr02_status": sr02_status,
                            "parts_installed": parts_installed,
                            "follow_up": follow_up
                        })
                    })

            # 5. Regulatory Events
            reg_file = well_dir / "regulatory-events.jsonl"
            if reg_file.exists():
                with open(reg_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        r = json.loads(line)
                        regulatory_list.append({
                            "event_id": r.get("event_id"),
                            "asset_id": asset_id,
                            "date": parse_iso_date(r.get("date")),
                            "agency": r.get("agency", ""),
                            "event_type": r.get("event_type", ""),
                            "protocol_id": r.get("protocol_id"),
                            "related_inspection_id": r.get("related_inspection_id"),
                            "hours_to_report": r.get("hours_to_report"),
                            "fine_usd": r.get("fine_usd", 0.0),
                            "status": r.get("status", "open"),
                            "detail": r.get("detail", "")
                        })

        return {
            "wells": wells_list,
            "equipment": equipment_list,
            "inspections": inspections_list,
            "maintenance": maintenance_list,
            "report_metrics": report_metrics_list,
            "document_sections": document_sections_list,
            "regulatory_events": regulatory_list
        }

    def parse_sops(self) -> List[Dict[str, Any]]:
        """Parses SOPs into section chunks for hybrid search."""
        sops = []
        sops_dir = self.fleet_dir / "sops"
        if sops_dir.exists():
            for sop_file in sops_dir.glob("*.md"):
                content = sop_file.read_text(encoding="utf-8")
                rel_path = str(sop_file.relative_to(self.dataset_dir)).replace("\\", "/")
                sections = re.split(r"(?m)^##\s+", content)
                for sec in sections:
                    sec = sec.strip()
                    if not sec:
                        continue
                    lines = sec.split("\n", 1)
                    title = lines[0].strip()
                    sops.append({
                        "doc_type": "sop",
                        "doc_path": rel_path,
                        "asset_id": None,
                        "section_title": f"{sop_file.stem} - {title}",
                        "content": sec,
                        "metadata": json.dumps({"sop": sop_file.stem, "section": title})
                    })
        return sops

    def parse_manuals(self) -> List[Dict[str, Any]]:
        """Parses well-type operating manuals into section chunks for hybrid search."""
        manuals = []
        manuals_dir = self.fleet_dir / "well-types"
        if manuals_dir.exists():
            for manual_file in manuals_dir.glob("*.md"):
                content = manual_file.read_text(encoding="utf-8")
                rel_path = str(manual_file.relative_to(self.dataset_dir)).replace("\\", "/")
                sections = re.split(r"(?m)^##\s+", content)
                for sec in sections:
                    sec = sec.strip()
                    if not sec:
                        continue
                    lines = sec.split("\n", 1)
                    title = lines[0].strip()
                    manuals.append({
                        "doc_type": "manual",
                        "doc_path": rel_path,
                        "asset_id": None,
                        "section_title": f"{manual_file.stem} - {title}",
                        "content": sec,
                        "metadata": json.dumps({"manual": manual_file.stem, "well_type": manual_file.stem, "section": title})
                    })
        return manuals

