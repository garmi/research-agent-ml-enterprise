"""Test Improvement Phase: Architecture & Engine Enhancements.

Tests for:
1. Lens lookup and criteria binding (get_lens_by_id, start_run lens passing)
2. Run and Output ID generation (generate_run_id, generate_output_id)
3. Step 2 Scope model and invalidation upon question/framing modification
4. Explainable unused sources categorization (explain_unused_sources)
5. Spike 1 sentence-to-quote verification contract (verify_sentence_support)
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.engine.ids import (
    generate_question_id,
    generate_run_id,
    generate_output_id,
)
from src.engine.framings import get_lens_by_id, FIXED_LENSES
from src.engine.approvals import save_gate1_approval
from src.engine.entry import start_run
from src.engine.scoping import (
    ScopeConfig,
    validate_scope_against_framing,
    ScopeValidationError,
)
from src.engine.unused_sources import explain_unused_sources, UnusedSourceExplanation
from src.engine.spike1_eval import verify_sentence_support


# ------------------------------------------------------------------------------
# 1. Lens Lookup and Binding Tests
# ------------------------------------------------------------------------------
def test_get_lens_by_id_returns_exact_lens():
    lens = get_lens_by_id("empirical-effect")
    assert lens is not None
    assert lens.id == "empirical-effect"
    assert lens.title == "Empirical effect"
    assert "measured outcomes" in lens.focus

    non_existent = get_lens_by_id("non-existent-lens")
    assert non_existent is None


def test_start_run_binds_approved_lens_to_runner():
    with tempfile.TemporaryDirectory() as tmp_dir:
        approvals_dir = Path(tmp_dir) / "approvals"
        q_text = "What empirical evidence exists regarding Amazon Kiro adoption?"
        q_id = generate_question_id(q_text)

        save_gate1_approval(
            question_id=q_id,
            question_text=q_text,
            framing_id="empirical-effect",
            framing_title="Empirical effect",
            framing_question=q_text,
            approved_by="tester",
            approvals_dir=approvals_dir,
        )

        captured_args = {}

        def mock_runner(**kwargs):
            captured_args.update(kwargs)
            return {"status": "completed", "run_id": "test-run-123"}

        res = start_run(
            question_id=q_id,
            question_text=q_text,
            runner=mock_runner,
            approvals_dir=approvals_dir,
        )

        assert res["status"] == "completed"
        # Verify framing_id and framing_lens are passed into runner arguments
        assert captured_args.get("framing_id") == "empirical-effect"
        assert captured_args.get("framing_lens") is not None
        assert captured_args["framing_lens"]["title"] == "Empirical effect"
        assert "studies and reports" in captured_args["framing_lens"]["counts_as_evidence"]


# ------------------------------------------------------------------------------
# 2. Run and Output ID Generation Tests
# ------------------------------------------------------------------------------
def test_generate_run_id_deterministic_and_unique():
    q_id = "q-kiro-empirical"
    run_id_1 = generate_run_id(q_id)
    assert run_id_1.startswith(f"run-{q_id}-")
    assert len(run_id_1) > len(q_id) + 5


def test_generate_output_id_versioning():
    run_id = "run-q-kiro-empirical-20261017-010203"
    out_v1 = generate_output_id(run_id, version=1)
    out_v2 = generate_output_id(run_id, version=2)

    assert out_v1 == f"out-{run_id}-v1"
    assert out_v2 == f"out-{run_id}-v2"
    assert out_v1 != out_v2


# ------------------------------------------------------------------------------
# 3. Scope Model and Invalidation Tests (Step 2 Scope)
# ------------------------------------------------------------------------------
def test_validate_scope_against_framing_valid():
    with tempfile.TemporaryDirectory() as tmp_dir:
        approvals_dir = Path(tmp_dir) / "approvals"
        q_text = "What empirical evidence exists regarding Amazon Kiro adoption?"
        q_id = generate_question_id(q_text)

        approval = save_gate1_approval(
            question_id=q_id,
            question_text=q_text,
            framing_id="empirical-effect",
            framing_title="Empirical effect",
            framing_question=q_text,
            approved_by="tester",
            approvals_dir=approvals_dir,
        )

        scope = ScopeConfig(
            question_id=q_id,
            question_text=q_text,
            framing_id="empirical-effect",
            source_types=["academic", "enterprise"],
            time_window_months=24,
            depth="Fast",
            report_format="brief",
        )

        is_valid = validate_scope_against_framing(scope, approval)
        assert is_valid is True


def test_validate_scope_invalidated_when_question_text_changed():
    with tempfile.TemporaryDirectory() as tmp_dir:
        approvals_dir = Path(tmp_dir) / "approvals"
        q_text = "What empirical evidence exists regarding Amazon Kiro adoption?"
        q_id = generate_question_id(q_text)

        approval = save_gate1_approval(
            question_id=q_id,
            question_text=q_text,
            framing_id="empirical-effect",
            framing_title="Empirical effect",
            framing_question=q_text,
            approved_by="tester",
            approvals_dir=approvals_dir,
        )

        # User changed question text in Step 1
        scope = ScopeConfig(
            question_id=q_id,
            question_text=q_text + " (modified)",
            framing_id="empirical-effect",
            source_types=["academic", "enterprise"],
        )

        with pytest.raises(ScopeValidationError) as exc:
            validate_scope_against_framing(scope, approval)
        assert "Question text has changed" in str(exc.value)


def test_validate_scope_invalidated_when_framing_changed():
    with tempfile.TemporaryDirectory() as tmp_dir:
        approvals_dir = Path(tmp_dir) / "approvals"
        q_text = "What empirical evidence exists regarding Amazon Kiro adoption?"
        q_id = generate_question_id(q_text)

        approval = save_gate1_approval(
            question_id=q_id,
            question_text=q_text,
            framing_id="empirical-effect",
            framing_title="Empirical effect",
            framing_question=q_text,
            approved_by="tester",
            approvals_dir=approvals_dir,
        )

        # Scope was confirmed for empirical-effect, but user changed framing to risks-and-controls
        scope = ScopeConfig(
            question_id=q_id,
            question_text=q_text,
            framing_id="risks-and-controls",
            source_types=["academic"],
        )

        with pytest.raises(ScopeValidationError) as exc:
            validate_scope_against_framing(scope, approval)
        assert "Framing lens mismatch" in str(exc.value)


# ------------------------------------------------------------------------------
# 4. Explainable Unused Sources Tests
# ------------------------------------------------------------------------------
def test_explain_unused_sources_identifies_reasons():
    sources = [
        {"id": "src-1", "title": "Paper 1: Kiro Trial", "venue_tier": "verified"},
        {"id": "src-2", "title": "Paper 2: Unverified Blog", "venue_tier": "unverified"},
        {"id": "src-3", "title": "Vendor Flyer", "venue_tier": "vendor"},
        {"id": "src-4", "title": "User Deselected Paper", "venue_tier": "verified"},
    ]
    claims = [
        {"source_id": "src-1", "grade": "strong", "status": "approved"},
        {"source_id": "src-2", "grade": "weak", "status": "auto"},
        {"source_id": "src-3", "grade": "vendor_claim", "status": "auto"},
        {"source_id": "src-4", "grade": "moderate", "status": "rejected"},  # Rejected by user
    ]
    cited_source_ids = {"src-1"}

    explanations = explain_unused_sources(
        all_sources=sources,
        cited_source_ids=cited_source_ids,
        claims=claims,
    )

    assert len(explanations) == 3
    reasons = {e.source_id: e for e in explanations}

    assert reasons["src-2"].category == "unverified_venue"
    assert "unverified venue" in reasons["src-2"].plain_english_reason.lower()

    assert reasons["src-3"].category == "vendor_claim_unsupported"
    assert "vendor" in reasons["src-3"].plain_english_reason.lower()

    assert reasons["src-4"].category == "user_excluded"
    assert "excluded by user" in reasons["src-4"].plain_english_reason.lower()


# ------------------------------------------------------------------------------
# 5. Spike 1 Sentence-to-Quote Support Verification Tests
# ------------------------------------------------------------------------------
def test_verify_sentence_support_passing_grounded_sentence():
    sentence = "Engineers utilizing Amazon Kiro experienced a 24% reduction in cycle time."
    quote = "Our study measured a 24% reduction in development cycle time across participating teams."

    res = verify_sentence_support(sentence, quote)
    assert res["supported"] is True
    assert res["warning_badge"] is None
    assert res["confidence"] >= 0.70


def test_verify_sentence_support_flags_ungrounded_numeric_claim():
    sentence = "Teams reported a 75% increase in throughput with Kiro."
    quote = "Our study observed moderate qualitative satisfaction among surveyed developers."

    res = verify_sentence_support(sentence, quote)
    assert res["supported"] is False
    assert res["warning_badge"] is not None
    assert "numerical mismatch" in res["warning_badge"].lower() or "unsupported" in res["warning_badge"].lower()
    assert len(res["reasons"]) > 0
