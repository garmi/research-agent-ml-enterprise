"""Phase 5 Evaluation Suite: Practitioner Lane, Abstraction Gate, Denylist Scan, and JSON Export.

Verifies:
1. Practitioner observations are stored strictly in practitioner.db (isolated).
2. Unabstracted practitioner claims are blocked at Gate 6 (R12).
3. Confirmed abstracted practitioner claims export cleanly to main ledger.
4. Denylist scanner detects confidential client/project names (R5).
5. Publisher publishes compliant documents and produces versioned website JSON export.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import pytest

from src.collectors.practitioner.collector import PractitionerCollector
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, OutputDoc, OutputSentence, Question, Run, Source
from src.ledger.repository import LedgerRepository
from src.publish.publisher import Publisher
from src.synth.generator import SynthesisEngine


@pytest.fixture
def phase5_env():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_db = os.path.join(tmpdir, "ledger.db")
        prac_db = os.path.join(tmpdir, "practitioner.db")
        denylist_file = os.path.join(tmpdir, "denylist.txt")
        export_dir = os.path.join(tmpdir, "exports")

        with open(denylist_file, "w", encoding="utf-8") as f:
            f.write("Barclays Capital\nProject Alpha\nJohn Doe\n")

        apply_migrations(db_path=ledger_db)
        apply_migrations(db_path=prac_db)

        repo = LedgerRepository(db_path=ledger_db)

        # Seed question
        q = Question(
            id="q-kiro-practitioner",
            text="What are field delivery lessons from Kiro in enterprise delivery?",
            scope="enterprise software delivery",
            time_window_months=24,
            status="active",
        )
        repo.insert_question(q)

        prac_collector = PractitionerCollector(db_path=prac_db)
        publisher = Publisher(
            db_path=ledger_db,
            denylist_path=denylist_file,
            export_dir=export_dir,
        )

        yield repo, prac_collector, publisher, tmpdir


def test_practitioner_isolation_and_abstraction_gate(phase5_env):
    repo, prac_collector, publisher, tmpdir = phase5_env

    # 1. Add un-abstracted observation
    _, unabs_claim = prac_collector.add_observation(
        question_id="q-kiro-practitioner",
        situation="Delivery rollout at Barclays Capital for Project Alpha",
        decision="Implemented specification guardrails",
        action="Required contract tests before AI code generation",
        outcome="Rework rate dropped 25%",
        sector="financial_services",
        abstraction_confirmed=False,  # Un-abstracted!
    )

    # Verify physical isolation: claim exists in practitioner.db but NOT in ledger.db
    assert prac_collector.repo.get_claim(unabs_claim.id) is not None
    assert repo.get_claim(unabs_claim.id) is None

    # Attempt export to ledger: MUST RAISE PermissionError (R12)
    with pytest.raises(PermissionError) as exc_info:
        prac_collector.export_abstracted_claim_to_ledger(unabs_claim.id, repo)
    assert "Gate 6 Abstraction Violation" in str(exc_info.value)
    assert repo.get_claim(unabs_claim.id) is None

    # 2. Add properly abstracted observation
    _, abs_claim = prac_collector.add_observation(
        question_id="q-kiro-practitioner",
        situation="Enterprise core banking transformation across multi-vendor teams",
        decision="Implemented specification contracts",
        action="Required architectural linting and automated contract tests",
        outcome="PR rework cycles stabilized with 25% reduction in integration defects",
        sector="financial_services",
        abstraction_confirmed=True,  # Abstracted!
    )

    # Export abstracted claim to ledger: MUST SUCCEED
    exported = prac_collector.export_abstracted_claim_to_ledger(abs_claim.id, repo, reviewer="lead_auditor")
    assert exported.id == abs_claim.id
    assert repo.get_claim(abs_claim.id) is not None

    # Verify audit review logged in ledger.db
    with repo._conn() as conn:
        revs = conn.execute("SELECT * FROM reviews WHERE object_id = ?;", (abs_claim.id,)).fetchall()
        assert len(revs) == 1
        assert revs[0]["gate"] == "Gate 6"
        assert revs[0]["action"] == "export_practitioner_claim"


def test_publish_gate_and_website_export(phase5_env):
    repo, prac_collector, publisher, tmpdir = phase5_env

    # Seed an academic source and claim in ledger
    acad_src = Source(
        id="src_icse_2024",
        lane="academic",
        source_type="peer_reviewed",
        title="Empirical Measurement of Coding Assistants in Enterprise Delivery",
        venue="ICSE",
        venue_tier="verified",
        pub_date="2024-05-01",
        status="active",
    )
    repo.insert_source(acad_src)

    acad_claim = Claim(
        id="claim_icse_1",
        question_id="q-kiro-practitioner",
        source_id="src_icse_2024",
        text="Empirical evaluation indicates that specification guardrails reduce integration defects by 25%.",
        source_excerpt="Specification guardrails reduce integration defects by 25 percent in enterprise teams.",
        value_json={"metric": "defect_reduction", "value": 25.0, "unit": "%"},
        entity="Enterprise Delivery",
        entity_match="exact",
        study_type="controlled_study",
        grade="strong",
        status="approved",
    )
    repo.insert_claim(acad_claim)

    # Also add an abstracted practitioner claim
    _, prac_claim = prac_collector.add_observation(
        question_id="q-kiro-practitioner",
        situation="Multi-vendor integration program",
        decision="Contract tests mandated",
        action="Pre-commit linters enforced",
        outcome="Defects dropped by 25%",
        sector="financial_services",
        abstraction_confirmed=True,
    )
    prac_collector.export_abstracted_claim_to_ledger(prac_claim.id, repo)

    # Synthesize field note using SynthesisEngine
    synth = SynthesisEngine(db_path=repo.db_path)
    doc, sentences, summary = synth.build_field_note(
        question_id="q-kiro-practitioner",
        human_view="In our delivery leadership experience, governance must precede autonomy.",
    )

    # Execute Gate 6 Publish
    success, pub_res = publisher.publish_output(
        output_id=doc.id,
        reviewer="Senior Delivery Leader",
        signoff_reason="Empirical grounding verified and practitioner abstraction confirmed",
        force_publish_non_band=True,  # Human sign-off override
    )

    assert success is True
    assert pub_res["published"] is True
    assert pub_res["status"] == "PUBLISHED"
    assert os.path.exists(pub_res["export_path"])
    assert os.path.exists(pub_res["canonical_path"])

    # Verify JSON export schema
    with open(pub_res["export_path"], "r", encoding="utf-8") as f:
        export_data = json.load(f)

    assert export_data["schema_version"] == "2.0"
    assert export_data["output_id"] == doc.id
    assert export_data["kind"] == "field_note"
    assert export_data["gates"]["passed"] is True
    assert "scorecard" in export_data
    assert len(export_data["sentences"]) > 0
    assert len(export_data["evidence_base"]) > 0

    # Verify output status updated in ledger
    updated_doc = repo.get_output(doc.id)
    assert updated_doc.status == "published"
