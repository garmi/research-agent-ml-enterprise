"""Test A2-5: Evidence-based scoring metrics for S4, S6, and S7.

Verifies:
1. S6 (Human review) counts claims actually reviewed by a human and human gates completed. Changing human review state changes S6.
2. S7 (Reproducibility) re-runs extraction and grading from cached sources to compute agreement; two runs with same cache give measured S7.
3. Unmeasured S7 marks component 'not measured' and caps quality band at 'REVISE'.
4. S4 (Gap disclosure) is computed from gap outcomes stated and ledger contradictions mentioned (not hardcoded 1.0/0.5 flag).
"""

from __future__ import annotations

import pytest
from src.ledger.models import Claim, OutputSentence, Question, Source
from src.score.checker import GateCheckResult
from src.score.scorer import QualityScorer


def test_human_review_state_changes_s6():
    """Verify that changing human review state changes S6."""
    scorer = QualityScorer()
    gate_ok = GateCheckResult()

    q = Question(id="q1", text="Enterprise AI adoption")
    c1 = Claim(
        id="c1",
        question_id="q1",
        source_id="src1",
        text="Delivery velocity improved by 25%.",
        source_excerpt="Velocity improved by 25%.",
        grade="strong",
        status="auto",  # Not reviewed by human
    )
    sent = OutputSentence(
        id="s1",
        output_id="out1",
        ordinal=1,
        text="Empirical literature demonstrates 25% velocity improvement.",
        type="assertive",
        claim_ids_json=["c1"],
    )

    # State 1: Zero human review (auto extracted only, 0 human gates completed)
    score_unreviewed = scorer.calculate_score(
        gate_result=gate_ok,
        sentences=[sent],
        ledger_claims={"c1": c1},
        sources={"src1": Source(id="src1", lane="academic", source_type="peer_reviewed", title="Study 1")},
        questions=[q],
        reviewed_claim_ids=set(),
        human_gates_completed_count=0,
        reproducibility_agreement=1.0,
    )

    # State 2: Human reviewed the cited claim and completed human gates (e.g. Gate 1 + Gate 3)
    score_reviewed = scorer.calculate_score(
        gate_result=gate_ok,
        sentences=[sent],
        ledger_claims={"c1": c1},
        sources={"src1": Source(id="src1", lane="academic", source_type="peer_reviewed", title="Study 1")},
        questions=[q],
        reviewed_claim_ids={"c1"},
        human_gates_completed_count=2,
        reproducibility_agreement=1.0,
    )

    s6_unreviewed = score_unreviewed["components"]["S6_human_review"]
    s6_reviewed = score_reviewed["components"]["S6_human_review"]

    assert s6_unreviewed == 0.0, f"Expected 0.0 for zero human review, got {s6_unreviewed}"
    assert s6_reviewed > s6_unreviewed, "Human review must strictly increase S6"
    assert s6_reviewed > 5.0, f"Expected S6 > 5.0 when human reviewed, got {s6_reviewed}"


def test_two_runs_with_same_cache_give_measured_s7():
    """Verify that two runs with the same cached sources give a measured S7 score."""
    scorer = QualityScorer()
    gate_ok = GateCheckResult()

    cached_papers = [
        {
            "id": "paper_cached_1",
            "title": "Empirical Evaluation of Spec-Driven Agentic Engineering",
            "abstract": "We conduct an industrial evaluation of agentic coding. Developers experienced 30% reduction in delivery defects across 50 sprints.",
            "year": 2024,
            "venue": "IEEE Transactions on Software Engineering",
            "doi": "10.1109/tse.2024.123",
        }
    ]

    # Run 1 extraction
    from src.extract.claim_extractor import extract_claims_from_paper
    from src.grade.grader import Grader
    grader = Grader()
    claims_run1 = extract_claims_from_paper(cached_papers[0], question_id="q1")
    for c in claims_run1:
        c.grade = "strong"
    ledger_claims_1 = {c.id: c for c in claims_run1}

    # Run 1 score with cached papers
    score1 = scorer.calculate_score(
        gate_result=gate_ok,
        sentences=[],
        ledger_claims=ledger_claims_1,
        sources={},
        questions=[],
        cached_papers=cached_papers,
    )

    # Run 2 score with same cached papers
    score2 = scorer.calculate_score(
        gate_result=gate_ok,
        sentences=[],
        ledger_claims=ledger_claims_1,
        sources={},
        questions=[],
        cached_papers=cached_papers,
    )

    s7_run1 = score1["components"]["S7_reproducibility"]
    s7_run2 = score2["components"]["S7_reproducibility"]

    assert s7_run1 is not None and s7_run1 != "not measured"
    assert s7_run2 is not None and s7_run2 != "not measured"
    assert s7_run1 == s7_run2 == 10.0, f"Expected 10.0 reproducibility on identical cache, got {s7_run1}, {s7_run2}"


def test_unmeasured_s7_caps_band_at_revise():
    """Verify that when S7 is unmeasured, it is marked 'not measured' and caps band at REVISE."""
    scorer = QualityScorer()
    gate_ok = GateCheckResult()

    # Pass everything needed for a high score (> 85), but no S7 reproducibility measured
    q = Question(id="q1", text="Topic")
    s = Source(id="s1", lane="academic", source_type="peer_reviewed", title="Empirical Title", venue="IEEE TSE", pub_date="2025")
    c = Claim(id="c1", question_id="q1", source_id="s1", text="Fact", source_excerpt="Fact", grade="strong", claim_date="2025")
    sent = OutputSentence(id="sent1", output_id="o1", ordinal=1, text="Empirical literature demonstrates Fact.", type="assertive", claim_ids_json=["c1"])

    score_res = scorer.calculate_score(
        gate_result=gate_ok,
        sentences=[sent],
        ledger_claims={"c1": c},
        sources={"s1": s},
        questions=[q],
        reviewed_claim_ids={"c1"},
        human_gates_completed_count=3,
        gap_outcomes_disclosed=1.0,
        reproducibility_agreement=None,  # S7 unmeasured
        cached_papers=None,
    )

    s7_val = score_res["components"]["S7_reproducibility"]
    assert s7_val in (None, "not measured"), f"Expected unmeasured S7, got {s7_val}"
    assert score_res["band"] == "REVISE", f"Quality band must be capped at REVISE while unmeasured, got {score_res['band']}"
    assert any("reproducibility" in rec.lower() for rec in score_res["top_3_improvements"])


def test_s4_computed_from_gap_outcomes_and_contradictions():
    """Verify that S4 is dynamically computed from gap outcomes stated and ledger contradictions."""
    scorer = QualityScorer()
    gate_ok = GateCheckResult()
    q = Question(id="q1", text="Topic")

    # Case A: Sentences with zero gap outcomes and zero contradictions mentioned
    sent_none = [
        OutputSentence(id="s1", output_id="o1", ordinal=1, text="Everything is moving as expected.", type="assertive"),
    ]
    score_a = scorer.calculate_score(
        gate_result=gate_ok,
        sentences=sent_none,
        ledger_claims={},
        sources={},
        questions=[q],
    )

    # Case B: Sentences explicitly state a negative finding / Outcome 4
    sent_with_gap = [
        OutputSentence(id="s1", output_id="o1", ordinal=1, text="The evidence does not support full lifecycle displacement.", type="negative_finding"),
        OutputSentence(id="s2", output_id="o1", ordinal=2, text="Strategic Gap (Outcome 4): No empirical controller literature found.", type="assertive"),
    ]
    score_b = scorer.calculate_score(
        gate_result=gate_ok,
        sentences=sent_with_gap,
        ledger_claims={},
        sources={},
        questions=[q],
    )

    s4_a = score_a["components"]["S4_gap_disclosure"]
    s4_b = score_b["components"]["S4_gap_disclosure"]

    assert s4_b > s4_a, f"Expected higher S4 with explicit gap outcomes! A: {s4_a}, B: {s4_b}"
    assert s4_a not in (10.0, 5.0) or s4_b not in (10.0, 5.0), "S4 should not be a fixed binary 1.0/0.5 flag"
