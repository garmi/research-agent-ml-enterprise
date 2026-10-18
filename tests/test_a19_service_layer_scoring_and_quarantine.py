"""Test A19: Service-Layer S6 Recalculation, Honest S7 Labeling, and Quarantine Reconciliation (Prompt A3-6).

Verifies:
1. Approving a claim via the service layer (LedgerService.approve_claim) recalculates S6 on subsequent scoring.
2. S7 is honestly labeled as 'extraction determinism' (measuring local cache agreement, not external reproducibility).
3. Quarantine inventory reconciliation:
   - 11 base files and 11 companion watermark files in outputs/quarantine/ (explaining the 7 vs 11 discrepancy).
   - 3 formerly published outputs are strictly updated to 'legacy-ungraded' in ledger.db.
   - Pre-quarantine / pre-migration backup database files exist in ledger/backups/.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
import pytest

from src.ledger.models import Claim, Question, Run, Source
from src.ledger.repository import LedgerRepository
from src.ledger.service import LedgerService
from src.ledger.migrations import apply_migrations, create_backup
from src.score.scorer import QualityScorer
from src.synth.generator import SynthesisEngine


def test_s6_recomputed_on_service_layer_human_approval():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_s6_service.db")
        backups_dir = str(Path(tmpdir) / "backups")
        apply_migrations(db_path=db_path, backups_dir=backups_dir)
        service = LedgerService(db_path=db_path)
        repo = service.repo

        q = Question(
            id="q_s6_test",
            text="How do AI coding assistants perform in enterprise software delivery?",
            scope="enterprise AI coding assistants",
        )
        repo.insert_question(q)

        run = Run(
            id="run_s6_1",
            config_json={},
            question_ids=[q.id],
        )
        repo.insert_run(run)

        src = Source(
            id="src_s6_1",
            lane="academic",
            source_type="peer_reviewed",
            title="Controlled Study of Developer Velocity with AI Assistants",
            venue="IEEE Transactions on Software Engineering",
            venue_tier="verified",
            status="active",
        )
        repo.insert_source(src)

        # Insert claim in 'auto' status (unreviewed by human)
        claim = Claim(
            id="c_s6_auto_1",
            question_id=q.id,
            source_id=src.id,
            text="AI coding assistants increase developer velocity by 25% in controlled tasks.",
            source_excerpt="developer velocity increased by 25%",
            grade="strong",
            status="auto",
        )
        repo.insert_claim(claim)

        synth = SynthesisEngine(db_path=db_path)

        # 1. First score before human review
        _, _, summary_before = synth.build_field_note(
            question_id=q.id,
            human_view="Our teams note that AI assistants accelerate routine boilerplate tasks.",
            run_id=run.id,
        )
        s6_before = summary_before["score_results"]["components"]["S6_human_review"]
        assert s6_before == 0.0, f"Expected S6 to be 0.0 before human review, got {s6_before}"

        # 2. Human operator approves the claim through the service layer
        service.approve_claim(claim_id=claim.id, reviewer="lead_researcher_auditor")

        # Verify claim status in database is now 'approved'
        saved_claim = repo.get_claim(claim.id)
        assert saved_claim.status == "approved"

        # 3. Second score after service-layer human review
        _, _, summary_after = synth.build_field_note(
            question_id=q.id,
            human_view="Our teams note that AI assistants accelerate routine boilerplate tasks.",
            run_id=run.id,
        )
        s6_after = summary_after["score_results"]["components"]["S6_human_review"]

        # Must strictly increase
        assert s6_after > s6_before, f"Expected S6 to increase after human review approval! Before: {s6_before}, After: {s6_after}"
        assert s6_after == 6.0, f"Expected S6 to be 6.0 (60% human reviewed claims share * 10 weight), got {s6_after}"


def test_s7_honestly_labeled_extraction_determinism():
    scorer = QualityScorer()
    cached_papers = [
        {
            "id": "p-det-1",
            "title": "Deterministic Test Paper on Developer Velocity",
            "abstract": "We evaluate velocity increases by 20% in standard code delivery tasks.",
            "year": 2024,
        }
    ]
    from src.extract.claim_extractor import extract_claims_from_paper
    extracted = extract_claims_from_paper(cached_papers[0], "q_test")
    ledger_claims = {c.id: c for c in extracted}

    from src.score.checker import GateCheckResult
    gate_res = GateCheckResult()

    res = scorer.calculate_score(
        gate_result=gate_res,
        sentences=[],
        ledger_claims=ledger_claims,
        sources={},
        questions=[],
        cached_papers=cached_papers,
    )

    # Must contain honest extraction determinism component
    assert "S7_extraction_determinism" in res["components"]
    assert res["components"]["S7_extraction_determinism"] == 10.0

    # Recommendation must state extraction determinism when unmeasured
    unmeasured_res = scorer.calculate_score(
        gate_result=gate_res,
        sentences=[],
        ledger_claims={},
        sources={},
        questions=[],
        cached_papers=None,
    )
    rec_text = " ".join(unmeasured_res["top_3_improvements"]).lower()
    assert "extraction determinism" in rec_text


def test_quarantine_inventory_reconciliation(tmp_path, monkeypatch):
    """Quarantine moves the 11 known pre-A1 deliverables, watermarks each one, and flags legacy outputs.

    Builds its own fixture data under tmp_path (cwd is moved there because the quarantine
    paths are relative to it), so the result does not depend on what outputs/ or ledger/
    happen to hold on this machine.
    """
    from src.ledger.quarantine import KNOWN_PRE_A1_FILES, quarantine_pre_a1_records

    monkeypatch.chdir(tmp_path)

    # 11 legacy deliverables: 7 reports and 4 JSON exports.
    assert len(KNOWN_PRE_A1_FILES) == 11
    for rel_path in KNOWN_PRE_A1_FILES:
        Path(rel_path).parent.mkdir(parents=True, exist_ok=True)
        Path(rel_path).write_text("legacy deliverable\n", encoding="utf-8")

    # Ledger with three outputs that were published before the A1 cutoff.
    ledger_dir = tmp_path / "ledger"
    db_path = str(ledger_dir / "ledger.db")
    backups_dir = str(ledger_dir / "backups")
    apply_migrations(db_path=db_path, backups_dir=backups_dir)

    legacy_ids = ("out_636bd066b77e", "out_df7b5084c036", "out_458ae9566b28")
    conn = sqlite3.connect(db_path)
    for oid in legacy_ids:
        conn.execute(
            "INSERT INTO outputs (id, kind, status, created_at) VALUES (?, 'field_note', 'published', ?);",
            (oid, "2026-10-01T00:00:00+00:00"),
        )
    conn.commit()
    conn.close()

    # Pre-quarantine snapshot, the same kind of backup an operator takes before quarantining.
    create_backup(db_path, backups_dir=backups_dir, prefix="pre_quarantine")

    summary = quarantine_pre_a1_records(db_path=db_path, outputs_dir="outputs")

    quarantine_dir = Path("outputs/quarantine")
    assert quarantine_dir.exists()
    quarantine_files = sorted([f.name for f in quarantine_dir.iterdir() if f.is_file()])

    base_files = [f for f in quarantine_files if not f.endswith(".quarantined.txt")]
    watermark_files = [f for f in quarantine_files if f.endswith(".quarantined.txt")]

    assert len(summary["files_quarantined"]) == 11
    assert len(base_files) == 11, f"Expected 11 base files in quarantine, found {len(base_files)}: {base_files}"
    assert len(watermark_files) == 11, f"Expected 11 companion watermark files in quarantine, found {len(watermark_files)}"
    assert len(quarantine_files) == 22, f"Expected 22 total files (11 + 11 watermarks), found {len(quarantine_files)}"
    for rel_path in KNOWN_PRE_A1_FILES:
        assert not Path(rel_path).exists(), f"{rel_path} should have been moved out of outputs/"

    # The three formerly published outputs must now be legacy-ungraded in the ledger.
    conn = sqlite3.connect(db_path)
    for oid in legacy_ids:
        row = conn.execute("SELECT status FROM outputs WHERE id = ?", (oid,)).fetchone()
        assert row is not None, f"Output {oid} not found in ledger.db"
        assert row[0] == "legacy-ungraded", f"Output {oid} status is '{row[0]}', expected 'legacy-ungraded'"
    conn.close()

    # The pre-quarantine backup snapshot exists in the backups directory.
    backup_files = list(Path(backups_dir).glob("*.db"))
    assert any(b.name.startswith("pre_quarantine_") for b in backup_files), "Expected pre-quarantine snapshot in backups/"
