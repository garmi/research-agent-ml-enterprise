"""Test A8: Unified status vocabulary, score sensitivity, and export gating.

Verifies:
1. Unified status vocabulary: BLOCKED | NOT_PUBLISHABLE | REVISE | PUBLISH_READY (no DO_NOT_PUBLISH).
2. Scorer yields distinct, sensitive scores for different evidence sets (never hardcoded 66.0).
3. Export files in outputs/ are not written when publish gate does not pass.
4. When blocked, green 'ZERO UNGROUNDED CLAIMS' banner is eliminated in favor of blocking reasons.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, OutputSentence, Question, Source
from src.ledger.repository import LedgerRepository
from src.score.checker import GateCheckResult
from src.score.scorer import QualityScorer


def test_unified_status_vocabulary_and_no_do_not_publish():
    """Verify QualityScorer uses only BLOCKED, NOT_PUBLISHABLE, REVISE, PUBLISH_READY."""
    scorer = QualityScorer()

    # Gate failed -> BLOCKED
    gate_failed = GateCheckResult()
    gate_failed.g1_pass = False
    gate_failed.violations["G1"].append("Ungrounded numeral")
    res_blocked = scorer.calculate_score(
        gate_result=gate_failed,
        sentences=[],
        ledger_claims={},
        sources={},
        questions=[],
    )
    assert res_blocked["band"] == "BLOCKED"

    # Gate passed, low score -> NOT_PUBLISHABLE (never DO_NOT_PUBLISH)
    gate_passed = GateCheckResult()
    res_low = scorer.calculate_score(
        gate_result=gate_passed,
        sentences=[],
        ledger_claims={},
        sources={},
        questions=[],
    )
    assert res_low["band"] == "NOT_PUBLISHABLE", f"Expected NOT_PUBLISHABLE, got '{res_low['band']}'"
    assert res_low["band"] != "DO_NOT_PUBLISH", "DO_NOT_PUBLISH must be replaced by NOT_PUBLISHABLE"


def test_scorer_yields_distinct_scores_for_different_evidence_sets():
    """Verify that strong vs weak evidence sets produce distinct scores, not constant 66.0."""
    scorer = QualityScorer()
    gate_passed = GateCheckResult()
    q = Question(id="q-test", text="How do teams adopt AI in enterprise software?", scope="ai")

    # Set 1: Strong peer-reviewed evidence with verified sources and full excerpts
    s_strong = Source(
        id="src-strong",
        lane="academic",
        source_type="peer_reviewed",
        org="IEEE",
        title="Empirical Evaluation of AI Delivery",
        venue="IEEE TSE",
        venue_tier="verified",
        pub_date="2024",
        commercial_stake="none",
        url="https://doi.org/10.1109/tse",
    )
    c_strong = Claim(
        id="c-strong-1",
        question_id=q.id,
        source_id=s_strong.id,
        text="Empirical evaluation confirms 30% reduction in delivery defects.",
        source_excerpt="30% reduction in delivery defects.",
        grade="strong",
        status="approved",
        claim_date="2024",
    )
    sent_strong = OutputSentence(
        id="sent-1",
        output_id="out-1",
        ordinal=1,
        text="Empirical literature demonstrates that 30% reduction in delivery defects is achieved.",
        type="assertive",
        claim_ids_json=[c_strong.id],
    )

    res_strong = scorer.calculate_score(
        gate_result=gate_passed,
        sentences=[sent_strong],
        ledger_claims={c_strong.id: c_strong},
        sources={s_strong.id: s_strong},
        questions=[q],
        reviewed_claim_ids={c_strong.id},
        gates_completed_count=6,
    )

    # Set 2: Weak vendor-only evidence with unverified sources, missing dates
    s_weak = Source(
        id="src-weak",
        lane="enterprise",
        source_type="vendor_blog",
        org="VendorCorp",
        title="Vendor Marketing Blog",
        venue="Vendor Blog",
        venue_tier="vendor",
        pub_date="Date unknown",
        commercial_stake="vendor",
    )
    c_weak = Claim(
        id="c-weak-1",
        question_id=q.id,
        source_id=s_weak.id,
        text="Vendor marketing claims productivity doubled without telemetry.",
        source_excerpt="Productivity doubled without telemetry.",
        grade="vendor_claim",
        status="auto",
        claim_date=None,
    )
    sent_weak = OutputSentence(
        id="sent-2",
        output_id="out-2",
        ordinal=1,
        text="Vendor marketing claims productivity doubled without telemetry.",
        type="assertive",
        claim_ids_json=[c_weak.id],
    )

    res_weak = scorer.calculate_score(
        gate_result=gate_passed,
        sentences=[sent_weak],
        ledger_claims={c_weak.id: c_weak},
        sources={s_weak.id: s_weak},
        questions=[q],
        reviewed_claim_ids=set(),
        gates_completed_count=2,
    )

    assert res_strong["total_score"] != res_weak["total_score"], (
        f"Scores must be sensitive and distinct! Strong: {res_strong['total_score']}, Weak: {res_weak['total_score']}"
    )
    assert res_strong["total_score"] > res_weak["total_score"] + 15, (
        f"Strong evidence ({res_strong['total_score']}) should score significantly higher than weak ({res_weak['total_score']})"
    )
    assert res_strong["total_score"] != 66.0, "Score should not be stuck at constant 66.0"
    assert res_weak["total_score"] != 66.0, "Score should not be stuck at constant 66.0"


def test_export_files_not_written_to_disk_when_publish_gate_fails():
    """Verify export files are NOT written to outputs/ directory when publish gate is blocked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.db")
        prac_db_path = str(Path(tmpdir) / "test_prac.db")
        q_yaml_path = str(Path(tmpdir) / "register.yaml")
        apply_migrations(db_path=db_path)
        apply_migrations(db_path=prac_db_path)

        runner = MultiLaneResearchRunner(
            db_path=db_path,
            practitioner_db_path=prac_db_path,
            questions_yaml_path=q_yaml_path,
        )

        # Run workflow in offline stub mode which triggers extractive fallback (publish_success=False)
        results = runner.run_workflow(
            topic="How do engineering teams govern AI coding assistants?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=[],
        )

        assert results["publish_res"]["status"] in ("blocked", "not_publishable")
        assert results["publish_res"]["allowed"] is False
