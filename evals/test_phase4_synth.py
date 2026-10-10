"""Phase 4 Synthesis and Gap Matrix evaluation tests.

Verifies:
1. Gap Matrix builder evaluates Academic, Enterprise, and Field evidence states.
2. Field Note synthesis reads claims strictly from the ledger.
3. Sentence-level traceability (every assertive sentence has valid claim IDs).
4. Strength verbs match grading limits.
5. Scorer computes S1-S7 and hard gate checks pass.
6. R14 linting catches boilerplate and raw topic interpolation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.gaps.matrix_builder import GapMatrixBuilder
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, OutputSentence, Question, Run, Source
from src.ledger.repository import LedgerRepository
from src.synth.generator import SynthesisEngine, lint_output_text


@pytest.fixture
def test_env():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_synth.db")
        apply_migrations(db_path=db_path)
        repo = LedgerRepository(db_path=db_path)

        # Seed test question
        q = Question(
            id="q-kiro-empirical",
            text="How is Kiro being used for development by enterprise engineering teams?",
            scope="enterprise AI coding assistants",
            time_window_months=24,
            status="active",
            version=1,
        )
        repo.insert_question(q)

        # Seed run
        run = Run(
            id="run-phase4-test",
            config_json={},
            code_version="v2.0",
            model_ids={"map": "ollama-test", "reduce": "ollama-test"},
            question_ids=["q-kiro-empirical"],
            seed=42,
        )
        repo.insert_run(run)

        # Seed sources
        src_acad = Source(
            id="src-acad-icse",
            lane="academic",
            source_type="peer_reviewed",
            org="ACM/IEEE",
            title="Controlled Study of Developer Productivity with AI Tools",
            doi="10.1145/test.123",
            venue="ICSE",
            venue_tier="verified",
            pub_date="2024-05-15",
            status="active",
        )
        repo.insert_source(src_acad)

        src_ent = Source(
            id="src-ent-aws",
            lane="enterprise",
            source_type="vendor_blog",
            org="AWS Dev",
            title="AWS Developer Experience Report",
            url="https://aws.amazon.com/blogs/dev/kiro-eval",
            venue_tier="vendor",
            pub_date="2024-06-01",
            commercial_stake="vendor",
            status="active",
        )
        repo.insert_source(src_ent)

        # Seed approved claims
        c1 = Claim(
            id="claim-acad-strong",
            question_id="q-kiro-empirical",
            source_id="src-acad-icse",
            text="The controlled study demonstrates that developers complete tasks 21% faster with paired AI assistance.",
            source_excerpt="Developers completed assigned programming tasks 21 percent faster in the paired condition.",
            value_json={"metric": "completion_speed", "value": 21.0, "unit": "percent"},
            entity="Kiro",
            entity_match="exact",
            study_type="controlled_study",
            extraction_confidence=0.92,
            grade="strong",
            grade_reasons_json=["verified venue", "controlled study"],
            status="approved",
        )
        repo.insert_claim(c1)

        c2 = Claim(
            id="claim-ent-vendor",
            question_id="q-kiro-empirical",
            source_id="src-ent-aws",
            text="The vendor blog reports telemetry showing an increase in daily PR submissions among early adopters.",
            source_excerpt="Early adopter engineering teams increased daily PR volume across target repositories.",
            entity="Kiro",
            entity_match="exact",
            study_type="vendor_assertion",
            extraction_confidence=0.88,
            grade="vendor_claim",
            grade_reasons_json=["vendor blog", "commercial stake"],
            status="approved",
        )
        repo.insert_claim(c2)

        yield db_path, repo


def test_gap_matrix_evaluation(test_env):
    db_path, repo = test_env
    builder = GapMatrixBuilder(db_path=db_path)

    entry = builder.evaluate_question_lanes(question_id="q-kiro-empirical", run_id="run-phase4-test")
    assert entry.question_id == "q-kiro-empirical"
    assert entry.academic_state == "supported"
    assert entry.enterprise_state == "partial"
    assert entry.field_state == "none found"
    # Both Academic and Enterprise are active/partial -> Outcome 1 (Supported)
    assert entry.outcome == 1
    assert "Outcome 1: Supported" in entry.rationale


def test_synthesis_field_note_end_to_end(test_env):
    db_path, repo = test_env
    synth = SynthesisEngine(db_path=db_path)

    doc, sentences, summary = synth.build_field_note(
        question_id="q-kiro-empirical",
        human_view="In our enterprise multi-vendor delivery, automated tools require clear architectural review.",
        run_id="run-phase4-test",
    )

    assert doc.id == summary["output_id"]
    assert doc.kind == "field_note"
    assert len(sentences) >= 5

    # Check sentence types
    has_heading = any(s.type == "heading" for s in sentences)
    has_assertive = any(s.type == "assertive" for s in sentences)
    has_opinion = any(s.type == "opinion" for s in sentences)

    assert has_heading
    assert has_assertive
    assert has_opinion

    # Traceability check: All assertive sentences must have valid claim IDs in ledger
    for s in sentences:
        if s.type == "assertive":
            assert s.claim_ids_json is not None
            assert len(s.claim_ids_json) > 0
            for cid in s.claim_ids_json:
                assert repo.get_claim(cid) is not None

    # Gate results check
    gate_res = summary["gate_results"]
    assert gate_res["passed"] is True
    assert gate_res["gates"]["G1_traceability"]["pass"] is True
    assert gate_res["gates"]["G2_numeric_fidelity"]["pass"] is True
    assert gate_res["gates"]["G3_entity_fidelity"]["pass"] is True
    assert gate_res["gates"]["G4_language_honesty"]["pass"] is True

    # Scorer results check
    score_res = summary["score_results"]
    assert score_res["total_score"] >= 70.0
    assert "S1_evidence_strength" in score_res["components"]
    assert "S2_corroboration_diversity" in score_res["components"]
    assert "S3_question_coverage" in score_res["components"]
    assert "S4_gap_disclosure" in score_res["components"]
    assert "S5_freshness_scope" in score_res["components"]
    assert "S6_human_review" in score_res["components"]
    assert "S7_reproducibility" in score_res["components"]


def test_r14_lint_rules():
    # 1. Clean sentences
    clean_s = [
        OutputSentence(id="s1", output_id="o1", ordinal=1, text="Controlled evaluation shows speed gain.", type="assertive"),
        OutputSentence(id="s2", output_id="o1", ordinal=2, text="Vendor metrics suggest increased PR volume.", type="assertive"),
    ]
    clean_ok, clean_viols = lint_output_text(clean_s, raw_topic="Enterprise AI Assistant Evaluation")
    assert clean_ok is True
    assert len(clean_viols) == 0

    # 2. Raw topic string interpolation violation
    topic = "how Kiro is being used for development by engineering teams"
    topic_interpolated = [
        OutputSentence(
            id="s1",
            output_id="o1",
            ordinal=1,
            text=f"Our analysis explores {topic} across multiple companies.",
            type="assertive",
        )
    ]
    t_ok, t_viols = lint_output_text(topic_interpolated, raw_topic=topic)
    assert t_ok is False
    assert any("Raw topic string" in v for v in t_viols)

    # 3. Repeated boilerplate sentence violation
    repeated_s = [
        OutputSentence(id="s1", output_id="o1", ordinal=1, text="AI tools improve delivery velocity.", type="assertive"),
        OutputSentence(id="s2", output_id="o1", ordinal=2, text="AI tools improve delivery velocity.", type="assertive"),
    ]
    r_ok, r_viols = lint_output_text(repeated_s)
    assert r_ok is False
    assert any("Repeated boilerplate sentence" in v for v in r_viols)
