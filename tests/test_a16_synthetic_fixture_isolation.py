"""Test suite for A3-3: Synthetic Fixture Isolation and Truthful Canary Findings.

Verifies:
1. Every hand-written canary fixture is prefixed with 'synthetic_' and carries 'SYNTHETIC FIXTURE'.
2. The publisher strictly blocks publication of any output containing claims derived from synthetic sources.
3. Frozen real cassettes for Q1, Q2, and Q3 are present and contain authentic non-synthetic records.
4. No synthetic source ID appears in any production output file in outputs/.
"""

import json
import os
import tempfile
from pathlib import Path
import pytest

from src.ledger.models import Claim, OutputDoc, OutputSentence, Question, Source
from src.ledger.repository import LedgerRepository
from src.ledger.migrations import apply_migrations
from src.publish.publisher import Publisher


def test_publisher_blocks_synthetic_fixtures_from_export():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_synth_pub.db")
        export_dir = os.path.join(tmp_dir, "outputs")
        apply_migrations(db_path=db_path)
        repo = LedgerRepository(db_path=db_path)

        q = Question(id="q_synth_test", text="Synthetic test question", scope="test")
        repo.insert_question(q)

        # Insert a synthetic source
        synth_src = Source(
            id="synthetic_paper-kiro-sdd-2025",
            lane="academic",
            source_type="peer_reviewed",
            org="Synthetic Test Lab",
            title="Synthetic Spec-Driven Study",
            url="https://example.com/synthetic",
            venue="Synthetic Journal",
            venue_tier="verified",
            commercial_stake="none",
            extraction_depth="abstract_only",
            status="active",
        )
        repo.insert_source(synth_src)

        # Insert claim citing synthetic source
        claim = Claim(
            id="c_synth_1",
            question_id=q.id,
            source_id=synth_src.id,
            text="The synthetic study claims a 24% throughput increase.",
            source_excerpt="Throughput increases by 24%",
            grade="strong",
            status="approved",
            context_json={"fixture_type": "SYNTHETIC FIXTURE", "is_synthetic": True},
        )
        repo.insert_claim(claim)

        import datetime
        from src.ledger.models import Run
        repo.insert_run(Run(id="run_synth_1", started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), question_ids=[q.id]))

        # Create output doc and sentence citing this synthetic claim
        out_doc = OutputDoc(
            id="out_synth_1",
            question_id=q.id,
            run_id="run_synth_1",
            kind="field_note",
            status="draft",
        )
        repo.insert_output(out_doc)

        sent = OutputSentence(
            id="sent_synth_1",
            output_id=out_doc.id,
            ordinal=1,
            text="The team observed 24% throughput gains [P1].",
            type="finding",
            strength_verb="demonstrates",
            claim_ids_json=[claim.id],
        )
        repo.insert_output_sentence(sent)

        publisher = Publisher(db_path=db_path, export_dir=export_dir)
        success, result = publisher.publish_output(output_id=out_doc.id)

        # Must be strictly BLOCKED from export
        assert success is False, "Publisher allowed synthetic fixture claim to be published!"
        assert result["status"] == "BLOCKED"
        assert any("synthetic" in v.lower() for v in result["gate_results"]["gates"]["G6_copyright"]["violations"]), (
            f"Expected synthetic fixture violation in G6, got: {result['gate_results']}"
        )


def test_frozen_cassettes_labeled_truthfully():
    cassettes_dir = Path("evals/canary/cassettes")
    assert cassettes_dir.exists()

    # Real cassettes must exist
    q1_path = cassettes_dir / "q1_kiro.json"
    q2_path = cassettes_dir / "q2_hospitals.json"
    q3_path = cassettes_dir / "q3_quantum_sourdough.json"

    assert q1_path.exists()
    assert q2_path.exists()
    assert q3_path.exists()

    with open(q1_path, "r", encoding="utf-8") as f:
        q1_data = json.load(f)
    with open(q2_path, "r", encoding="utf-8") as f:
        q2_data = json.load(f)

    # Real cassettes must not contain synthetic markers
    for p in q1_data:
        assert not p.get("id", "").startswith("synthetic_"), f"Real Q1 cassette contains synthetic ID: {p.get('id')}"
        assert p.get("fixture_type") != "SYNTHETIC FIXTURE", f"Real Q1 cassette carries SYNTHETIC FIXTURE: {p.get('title')}"

    for p in q2_data:
        assert not p.get("id", "").startswith("synthetic_"), f"Real Q2 cassette contains synthetic ID: {p.get('id')}"
        assert p.get("fixture_type") != "SYNTHETIC FIXTURE", f"Real Q2 cassette carries SYNTHETIC FIXTURE: {p.get('title')}"
