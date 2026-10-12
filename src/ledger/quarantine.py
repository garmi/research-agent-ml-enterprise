"""Quarantine Manager for Pre-A1 Contaminated Records and Outputs (Prompt A2-9).

Identifies runs, outputs, claims, and exported deliverables generated prior to
the A1 commit (2026-10-11T16:35:21Z) that may contain fabricated DOIs, simulated
percentage figures, or unverified seeded practitioner notes.

Enforces:
- Marks output records as 'legacy-ungraded' in SQLite ledger.
- Marks claim records created before A1 as 'legacy-ungraded'.
- Tags run configs with legacy-ungraded quarantine status.
- Permanently blocks export across all formats via export_policy.
- Moves/watermarks legacy pre-A1 file deliverables in outputs/.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Commit 81e2fd6 timestamp (fix(A1): remove hardcoded report content strings and templates)
A1_COMMIT_CUTOFF_ISO = "2026-10-11T16:35:21Z"

KNOWN_PRE_A1_FILES = [
    "outputs/reports/demo_research_brief.md",
    "outputs/reports/gemini-research.html",
    "outputs/reports/kiro_research_brief.md",
    "outputs/reports/research_report_gemini.md",
    "outputs/reports/research_report_v2.md",
    "outputs/reports/how_kiro_is_being_used_for_development_b.md",
    "outputs/reports/measuring_roi_and_developer_productivity.md",
    "outputs/json/publish_export_out_636bd066b77e.json",
    "outputs/json/publish_export_out_df7b5084c036.json",
    "outputs/json/publish_export_out_458ae9566b28.json",
    "outputs/json/field_note_export.json",
]


def quarantine_pre_a1_records(
    db_path: str = "ledger/ledger.db",
    cutoff_iso: str = A1_COMMIT_CUTOFF_ISO,
    quarantine_files: bool = True,
    outputs_dir: str = "outputs",
) -> Dict[str, Any]:
    """Quarantine all runs, claims, and outputs created before commit A1 cutoff."""
    summary: Dict[str, Any] = {
        "cutoff_iso": cutoff_iso,
        "outputs_quarantined": 0,
        "quarantined_output_ids": [],
        "claims_quarantined": 0,
        "runs_quarantined": 0,
        "quarantined_run_ids": [],
        "files_quarantined": [],
    }

    if not os.path.exists(db_path):
        logger.warning("Database %s does not exist; skipping database quarantine.", db_path)
        return summary

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 1. Quarantine Outputs
    out_rows = conn.execute(
        "SELECT id, created_at, status FROM outputs WHERE created_at < ? OR status != 'legacy-ungraded';",
        (cutoff_iso,),
    ).fetchall()
    
    quarantined_out_ids = []
    for r in out_rows:
        created = r["created_at"] or ""
        if created < cutoff_iso:
            quarantined_out_ids.append(r["id"])

    if quarantined_out_ids:
        placeholders = ",".join("?" for _ in quarantined_out_ids)
        conn.execute(
            f"UPDATE outputs SET status = 'legacy-ungraded' WHERE id IN ({placeholders});",
            quarantined_out_ids,
        )
        summary["outputs_quarantined"] = len(quarantined_out_ids)
        summary["quarantined_output_ids"] = quarantined_out_ids

    # 2. Quarantine Claims
    claim_rows = conn.execute(
        "SELECT id, created_at FROM claims WHERE created_at < ?;",
        (cutoff_iso,),
    ).fetchall()
    quarantined_claim_ids = [r["id"] for r in claim_rows]
    if quarantined_claim_ids:
        placeholders = ",".join("?" for _ in quarantined_claim_ids)
        conn.execute(
            f"UPDATE claims SET status = 'legacy-ungraded' WHERE id IN ({placeholders});",
            quarantined_claim_ids,
        )
        summary["claims_quarantined"] = len(quarantined_claim_ids)

    # 3. Quarantine Runs
    run_rows = conn.execute(
        "SELECT id, created_at, config_json FROM runs WHERE created_at < ?;",
        (cutoff_iso,),
    ).fetchall()
    quarantined_run_ids = []
    for r in run_rows:
        run_id = r["id"]
        cfg_str = r["config_json"] or "{}"
        try:
            cfg = json.loads(cfg_str)
        except Exception:
            cfg = {}
        cfg["status"] = "legacy-ungraded"
        cfg["quarantine"] = "pre-a1-legacy"
        conn.execute(
            "UPDATE runs SET config_json = ? WHERE id = ?;",
            (json.dumps(cfg), run_id),
        )
        quarantined_run_ids.append(run_id)

    summary["runs_quarantined"] = len(quarantined_run_ids)
    summary["quarantined_run_ids"] = quarantined_run_ids

    conn.commit()
    conn.close()

    # 4. Quarantine File Deliverables on Disk
    if quarantine_files and os.path.exists(outputs_dir):
        quarantine_dir = Path(outputs_dir) / "quarantine"
        quarantine_dir.mkdir(parents=True, exist_ok=True)

        for rel_path in KNOWN_PRE_A1_FILES:
            fpath = Path(rel_path)
            if fpath.exists():
                dest = quarantine_dir / fpath.name
                shutil.move(str(fpath), str(dest))
                # Add watermark disclaimer file beside quarantined file
                meta_dest = quarantine_dir / f"{fpath.name}.quarantined.txt"
                meta_dest.write_text(
                    f"QUARANTINED DELIVERABLE: {fpath.name}\n"
                    f"Status: legacy-ungraded\n"
                    f"Reason: Generated prior to commit A1 (cutoff {cutoff_iso}).\n"
                    f"May contain fabricated DOIs or unconfirmed seeded notes.\n"
                    f"Export and publication permanently blocked.\n",
                    encoding="utf-8",
                )
                summary["files_quarantined"].append(fpath.name)

    return summary


if __name__ == "__main__":
    import sys
    db = sys.argv[1] if len(sys.argv) > 1 else "ledger/ledger.db"
    res = quarantine_pre_a1_records(db_path=db)
    print("Quarantine Results:")
    print(json.dumps(res, indent=2))
