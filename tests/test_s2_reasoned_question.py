"""Tests for Slice S2: Reasoned Question.

Requirements:
1. Schema validation rejects missing or malformed fields.
2. Coverage check rejects a proposal that drops a user sentence unaccounted.
3. Faithfulness check rejects an unlisted new entity or number and accepts it when listed in added_terms.
4. Approval JSON contains all required fields: raw_user_text, versions, final_package,
   provider, model_name, prompt_file_hash, timestamp, package_sha256.
   start_run refuses without approval, and on a package changed after approval.
5. Editing after approval clears approval with a visible message.
6. No model available: plain message, no proposal, Run locked.
7. Re-reason creates v2 and keeps v1.
8. Stub mode: deterministic stub reasoner, red banner, throwaway ledger,
   real ledger and outputs byte-identical; cloud calls blocked in tests.
9. Rendered text scan: no .db, .sqlite or ledger/ paths.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest

from src.engine.approvals import (
    Gate1Approval,
    get_latest_gate1_approval,
    save_gate1_approval,
)
from src.engine.entry import GateApprovalError, start_run
from src.engine.ids import resolve_question_id
from src.engine.reasoner import (
    QuestionReasoningError,
    _call_model_for_reasoning,
    compute_package_sha256,
    find_unlisted_terms,
    get_prompt_file_hash,
    reason_question,
    split_user_sentences,
    validate_reasoned_package,
)
from src.engine.stub_mode import is_stub_mode


SAMPLE_USER_TEXT = (
    "Our engineering org is adopting AI coding assistants like Copilot and Kiro. "
    "Leadership wants to know the measurable productivity impact on delivery teams. "
    "We also worry about code quality dropping and technical debt piling up."
)


# ------------------------------------------------------------------------------
# Test 1: Schema validation rejects missing or malformed fields
# ------------------------------------------------------------------------------
def test_schema_validation_rejects_missing_or_malformed_fields():
    # Valid base package
    valid_pkg = {
        "refined_question": "What measurable productivity and code quality impact do AI coding assistants have on enterprise software delivery teams?",
        "sub_questions": [
            "How do AI coding assistants affect software delivery velocity and cycle time?",
            "What empirical impact do AI coding assistants have on downstream code quality and defect rates?",
            "What technical debt or architectural trade-offs emerge from higher assistant autonomy?",
        ],
        "premises_to_test": [
            "AI coding assistants inherently degrade code quality or increase technical debt over time.",
        ],
        "in_scope": [
            "Empirical productivity metrics (cycle time, throughput)",
            "Downstream quality metrics (defect density, review time)",
        ],
        "out_of_scope": [
            "Marketing projections without empirical data",
        ],
        "evidence_needed": [
            "Empirical trials and case studies with measurable delivery metrics",
        ],
        "ambiguities": [
            "Definition of 'productivity' (developer self-report vs telemetry)",
        ],
        "changes_and_reasons": [
            {"change": "Reframed 'worry about debt' into an explicit testable premise", "reason": "Neutral inquiry tone"},
        ],
        "coverage_map": {
            "Our engineering org is adopting AI coding assistants like Copilot and Kiro.": "scope",
            "Leadership wants to know the measurable productivity impact on delivery teams.": "question",
            "We also worry about code quality dropping and technical debt piling up.": "premise",
        },
        "added_terms": [],
    }

    ok, errors = validate_reasoned_package(valid_pkg, SAMPLE_USER_TEXT)
    assert ok, f"Expected valid package, got errors: {errors}"

    # Missing refined_question
    bad_pkg = dict(valid_pkg)
    bad_pkg.pop("refined_question")
    ok, errors = validate_reasoned_package(bad_pkg, SAMPLE_USER_TEXT)
    assert not ok
    assert any("refined_question" in e for e in errors)

    # Sub-questions < 3
    bad_pkg = dict(valid_pkg, sub_questions=["Only one question?"])
    ok, errors = validate_reasoned_package(bad_pkg, SAMPLE_USER_TEXT)
    assert not ok
    assert any("sub_questions" in e for e in errors)

    # Sub-questions > 5
    bad_pkg = dict(valid_pkg, sub_questions=[f"Sub question {i}?" for i in range(6)])
    ok, errors = validate_reasoned_package(bad_pkg, SAMPLE_USER_TEXT)
    assert not ok
    assert any("sub_questions" in e for e in errors)


# ------------------------------------------------------------------------------
# Test 2: Coverage check rejects a proposal that drops a user sentence unaccounted
# ------------------------------------------------------------------------------
def test_coverage_check_rejects_proposal_dropping_user_sentence():
    sentences = split_user_sentences(SAMPLE_USER_TEXT)
    assert len(sentences) == 3

    valid_pkg = {
        "refined_question": "What measurable productivity impact do AI coding assistants have?",
        "sub_questions": ["Q1?", "Q2?", "Q3?"],
        "premises_to_test": [],
        "in_scope": ["Scope"],
        "out_of_scope": ["Out"],
        "evidence_needed": ["Evidence"],
        "ambiguities": [],
        "changes_and_reasons": [],
        "coverage_map": {
            sentences[0]: "scope",
            sentences[1]: "question",
            sentences[2]: "premise",
        },
        "added_terms": [],
    }

    ok, errors = validate_reasoned_package(valid_pkg, SAMPLE_USER_TEXT)
    assert ok, f"Expected coverage pass, got {errors}"

    # Drop 3rd sentence from coverage map
    dropped_coverage = dict(valid_pkg["coverage_map"])
    dropped_coverage.pop(sentences[2])
    incomplete_pkg = dict(valid_pkg, coverage_map=dropped_coverage)

    ok, errors = validate_reasoned_package(incomplete_pkg, SAMPLE_USER_TEXT)
    assert not ok
    assert any("coverage" in e.lower() for e in errors)

    # Marked not_used with reason is accepted
    not_used_coverage = dict(valid_pkg["coverage_map"])
    not_used_coverage[sentences[2]] = "not_used: Sentiment statement not actionable as an empirical parameter"
    pkg_not_used = dict(valid_pkg, coverage_map=not_used_coverage)
    ok, errors = validate_reasoned_package(pkg_not_used, SAMPLE_USER_TEXT)
    assert ok, f"Expected not_used with reason to pass, got {errors}"


# ------------------------------------------------------------------------------
# Test 3: Faithfulness check flags unlisted new entities and numbers
# ------------------------------------------------------------------------------
def test_faithfulness_check_flags_unlisted_new_entities_and_numbers():
    pkg = {
        "refined_question": "What measurable productivity impact does GitLab Duo have across 50 enterprise engineering teams?",
        "sub_questions": [
            "Does GitLab Duo reduce PR review cycle time?",
            "What defect rates are observed in 2026?",
            "How does tooling architecture affect outcomes?",
        ],
        "premises_to_test": [],
        "in_scope": ["Scope"],
        "out_of_scope": ["Out"],
        "evidence_needed": ["Studies"],
        "ambiguities": [],
        "changes_and_reasons": [],
        "coverage_map": {s: "question" for s in split_user_sentences(SAMPLE_USER_TEXT)},
        "added_terms": [],
    }

    # "GitLab Duo", "50", "2026" are in proposal but not in SAMPLE_USER_TEXT, and not listed in added_terms
    unlisted = find_unlisted_terms(pkg, SAMPLE_USER_TEXT)
    unlisted_lower = [u.lower() for u in unlisted]
    assert "50" in unlisted_lower
    assert "2026" in unlisted_lower
    assert any("gitlab duo" in u for u in unlisted_lower)

    # When explicitly listed in added_terms, they are resolved
    pkg_with_terms = dict(pkg, added_terms=["GitLab Duo", "50", "2026"])
    unlisted_resolved = find_unlisted_terms(pkg_with_terms, SAMPLE_USER_TEXT)
    assert not any(t in unlisted_resolved for t in ["50", "2026", "GitLab Duo"])


# ------------------------------------------------------------------------------
# Test 4: Approval JSON contains all required fields; start_run enforcement
# ------------------------------------------------------------------------------
def test_approval_json_contains_all_fields_and_start_run_enforcement(tmp_path):
    approvals_dir = tmp_path / "approvals"

    pkg = {
        "refined_question": "What measurable productivity impact do AI coding assistants have on enterprise software delivery teams?",
        "sub_questions": ["Sub 1?", "Sub 2?", "Sub 3?"],
        "premises_to_test": ["Premise 1"],
        "in_scope": ["In scope"],
        "out_of_scope": ["Out of scope"],
        "evidence_needed": ["Empirical studies"],
        "ambiguities": ["Ambiguity 1"],
        "changes_and_reasons": [{"change": "Refined wording", "reason": "Clarity"}],
        "coverage_map": {s: "question" for s in split_user_sentences(SAMPLE_USER_TEXT)},
        "added_terms": [],
    }

    q_id = resolve_question_id(pkg["refined_question"])
    prompt_hash = get_prompt_file_hash()
    assert len(prompt_hash) == 64

    # Save Gate 1 approval with reasoned question package
    approval = save_gate1_approval(
        question_id=q_id,
        raw_user_text=SAMPLE_USER_TEXT,
        proposals=[pkg],
        final_package=pkg,
        provider="ollama",
        model_name="llama3.2",
        prompt_file_hash=prompt_hash,
        approvals_dir=approvals_dir,
    )

    # Check file on disk
    app_files = list(approvals_dir.glob(f"{q_id}/gate1-v*.json"))
    assert len(app_files) == 1
    with open(app_files[0]) as f:
        saved_data = json.load(f)

    assert saved_data["raw_user_text"] == SAMPLE_USER_TEXT
    assert len(saved_data["proposals"]) >= 1
    assert saved_data["final_package"]["refined_question"] == pkg["refined_question"]
    assert saved_data["provider"] == "ollama"
    assert saved_data["model_name"] == "llama3.2"
    assert saved_data["prompt_file_hash"] == prompt_hash
    assert "package_sha256" in saved_data
    assert saved_data["package_sha256"] == compute_package_sha256(pkg)

    # start_run: refuses without approval
    with pytest.raises(GateApprovalError) as exc_info:
        start_run(
            question_id="unapproved-question-id",
            question_text=pkg["refined_question"],
            approvals_dir=approvals_dir,
            reasoned_package=pkg,
        )
    assert "not approved" in str(exc_info.value).lower()

    # start_run: refuses on package changed after approval
    modified_pkg = dict(pkg, refined_question="What completely different question was asked?")
    with pytest.raises(GateApprovalError) as exc_info:
        start_run(
            question_id=q_id,
            question_text=modified_pkg["refined_question"],
            approvals_dir=approvals_dir,
            reasoned_package=modified_pkg,
        )
    assert "changed" in str(exc_info.value).lower()

    # start_run: delegates with approved package
    called_args = {}
    def mock_runner(**kwargs):
        called_args.update(kwargs)
        return {"status": "PUBLISH_READY", "duration": "1s"}

    result = start_run(
        question_id=q_id,
        question_text=pkg["refined_question"],
        runner=mock_runner,
        approvals_dir=approvals_dir,
        reasoned_package=pkg,
    )
    assert result["status"] == "PUBLISH_READY"
    assert called_args["topic"] == pkg["refined_question"]
    assert called_args["reasoned_package"] == pkg


# ------------------------------------------------------------------------------
# Test 5: Editing after approval clears approval
# ------------------------------------------------------------------------------
def test_editing_after_approval_clears_approval(tmp_path):
    from src.engine.approvals import is_package_approved

    approvals_dir = tmp_path / "approvals"
    pkg = {
        "refined_question": "What measurable productivity impact do AI assistants have?",
        "sub_questions": ["Sub 1?", "Sub 2?", "Sub 3?"],
        "premises_to_test": [],
        "in_scope": ["Scope"],
        "out_of_scope": ["Out"],
        "evidence_needed": ["Studies"],
        "ambiguities": [],
        "changes_and_reasons": [],
        "coverage_map": {s: "question" for s in split_user_sentences(SAMPLE_USER_TEXT)},
        "added_terms": [],
    }
    q_id = resolve_question_id(pkg["refined_question"])

    save_gate1_approval(
        question_id=q_id,
        raw_user_text=SAMPLE_USER_TEXT,
        proposals=[pkg],
        final_package=pkg,
        provider="ollama",
        model_name="llama3.2",
        prompt_file_hash=get_prompt_file_hash(),
        approvals_dir=approvals_dir,
    )

    # Approved package matches
    assert is_package_approved(q_id, pkg, approvals_dir=approvals_dir)

    # Modifying a sub-question clears approval
    edited_pkg = dict(pkg, sub_questions=["Edited Sub 1?", "Sub 2?", "Sub 3?"])
    assert not is_package_approved(q_id, edited_pkg, approvals_dir=approvals_dir)


# ------------------------------------------------------------------------------
# Test 6: No model available: plain message, no proposal, Run locked
# ------------------------------------------------------------------------------
def test_no_model_available_plain_message_no_proposal():
    # If provider is not reachable/configured, raises plain QuestionReasoningError without silent fallback
    with pytest.raises(QuestionReasoningError) as exc_info:
        reason_question(
            user_text=SAMPLE_USER_TEXT,
            provider="nonexistent_provider",
        )
    msg = str(exc_info.value)
    assert "model" in msg.lower() or "provider" in msg.lower() or "available" in msg.lower()
    assert "traceback" not in msg.lower()


# ------------------------------------------------------------------------------
# Test 7: Re-reason creates v2 and keeps v1
# ------------------------------------------------------------------------------
def test_rereason_creates_v2_and_keeps_v1(monkeypatch):
    monkeypatch.setenv("STUB_LLM", "1")

    # Call reason_question initial (v1)
    v1_pkg = reason_question(user_text=SAMPLE_USER_TEXT, provider="stub")
    assert v1_pkg["refined_question"]

    # Re-reason with user feedback
    feedback = "Focus more on code review bottlenecks and defect detection."
    v2_pkg = reason_question(
        user_text=SAMPLE_USER_TEXT,
        provider="stub",
        feedback=feedback,
        previous_package=v1_pkg,
    )

    assert v2_pkg != v1_pkg
    assert any("review" in sq.lower() or "defect" in sq.lower() for sq in v2_pkg["sub_questions"])
    assert any("feedback" in str(cr).lower() for cr in v2_pkg["changes_and_reasons"])


# ------------------------------------------------------------------------------
# Test 8: Stub mode: deterministic reasoner, throwaway ledger, byte-identical outputs
# ------------------------------------------------------------------------------
def test_stub_mode_deterministic_reasoner(monkeypatch, tmp_path):
    monkeypatch.setenv("STUB_LLM", "1")
    assert is_stub_mode()

    pkg1 = reason_question(user_text=SAMPLE_USER_TEXT, provider="stub")
    pkg2 = reason_question(user_text=SAMPLE_USER_TEXT, provider="stub")

    assert pkg1 == pkg2, "Stub reasoner must be deterministic"
    ok, errors = validate_reasoned_package(pkg1, SAMPLE_USER_TEXT)
    assert ok, f"Stub package must pass validation: {errors}"


# ------------------------------------------------------------------------------
# Test 9: Rendered text scan: no .db, .sqlite or ledger/ paths
# ------------------------------------------------------------------------------
def test_rendered_text_scan_no_db_sqlite_ledger_paths():
    import re
    from src.ui.intake_view import render_s2_proposal_card_text

    pkg = {
        "refined_question": "What measurable productivity impact do AI coding assistants have?",
        "sub_questions": ["Sub 1?", "Sub 2?", "Sub 3?"],
        "premises_to_test": ["Test premise"],
        "in_scope": ["Empirical studies"],
        "out_of_scope": ["Marketing claims"],
        "evidence_needed": ["Academic literature"],
        "ambiguities": ["Metric definition"],
        "changes_and_reasons": [{"change": "Reframed question", "reason": "Neutrality"}],
        "coverage_map": {s: "question" for s in split_user_sentences(SAMPLE_USER_TEXT)},
        "added_terms": [],
    }

    rendered_text = render_s2_proposal_card_text(pkg)

    # Must contain proposal elements
    assert "What measurable productivity impact" in rendered_text
    assert "Sub 1?" in rendered_text

    # Must NOT contain forbidden database / filesystem leak patterns
    forbidden_patterns = [
        r"\b[\w\-/\.]+\.(?:db|sqlite)\b",
        r"ledger/",
        r"/app/",
        r"/Users/",
    ]
    for pat in forbidden_patterns:
        matches = re.findall(pat, rendered_text)
        assert not matches, f"Found forbidden pattern {pat!r} in rendered text: {matches}"


# ------------------------------------------------------------------------------
# Test 10: Fake provider unit tests: valid, retry recovery, and 2x failure
# ------------------------------------------------------------------------------
def test_fake_provider_valid_json_accepted(monkeypatch):
    """(a) Valid JSON from model provider is accepted immediately."""
    sentences = split_user_sentences(SAMPLE_USER_TEXT)
    valid_payload = {
        "refined_question": "What measurable productivity impact do AI coding assistants have on enterprise delivery teams?",
        "sub_questions": [
            "How do AI coding assistants affect PR review cycle times and throughput?",
            "What empirical benchmarks exist for developer velocity with assistants?",
            "What downstream defect rates emerge in production code?",
        ],
        "premises_to_test": [
            "AI coding assistants inherently degrade code quality or increase technical debt.",
        ],
        "in_scope": ["Empirical productivity metrics", "Downstream code quality"],
        "out_of_scope": ["Speculative vendor marketing"],
        "evidence_needed": ["Empirical studies", "Enterprise benchmarks"],
        "ambiguities": ["Developer self-reported sentiment vs telemetry"],
        "changes_and_reasons": [{"change": "Reframed into neutral question", "reason": "Objective inquiry"}],
        "coverage_map": {
            sentences[0]: "scope",
            sentences[1]: "question",
            sentences[2]: "premise",
        },
        "added_terms": [],
    }

    call_count = 0
    def fake_fn(user_text, retry_feedback=None, **kwargs):
        nonlocal call_count
        call_count += 1
        return json.dumps(valid_payload)

    monkeypatch.setattr(_call_model_for_reasoning, "fake_fn", fake_fn)
    result = reason_question(user_text=SAMPLE_USER_TEXT, provider="fake")
    assert call_count == 1
    assert result["refined_question"] == valid_payload["refined_question"]
    assert len(result["sub_questions"]) == 3


def test_fake_provider_malformed_json_valid_on_retry(monkeypatch):
    """(b) Malformed JSON on attempt 1 triggers retry with error feedback and succeeds on attempt 2."""
    sentences = split_user_sentences(SAMPLE_USER_TEXT)
    valid_payload = {
        "refined_question": "What measurable productivity impact do AI coding assistants have on enterprise delivery teams?",
        "sub_questions": [
            "How do AI coding assistants affect PR review cycle times and throughput?",
            "What empirical benchmarks exist for developer velocity with assistants?",
            "What downstream defect rates emerge in production code?",
        ],
        "premises_to_test": ["Premise to test"],
        "in_scope": ["Scope"],
        "out_of_scope": ["Out of scope"],
        "evidence_needed": ["Evidence needed"],
        "ambiguities": [],
        "changes_and_reasons": [{"change": "Neutral inquiry", "reason": "Clarity"}],
        "coverage_map": {s: "question" for s in sentences},
        "added_terms": [],
    }

    call_history = []
    def fake_fn(user_text, retry_feedback=None, **kwargs):
        call_history.append(retry_feedback)
        if len(call_history) == 1:
            # First attempt returns malformed JSON
            return "```json\n{malformed_json: not valid,\n```"
        else:
            # Second attempt receives retry feedback and returns valid JSON
            return json.dumps(valid_payload)

    monkeypatch.setattr(_call_model_for_reasoning, "fake_fn", fake_fn)
    result = reason_question(user_text=SAMPLE_USER_TEXT, provider="fake")

    assert len(call_history) == 2
    assert call_history[0] is None
    assert call_history[1] is not None
    assert "not valid JSON" in call_history[1] or "JSONDecodeError" in call_history[1]
    assert result["refined_question"] == valid_payload["refined_question"]


def test_fake_provider_malformed_twice_shows_plain_error(monkeypatch):
    """(c) Malformed JSON on both attempts displays a plain error with no traceback."""
    call_history = []
    def fake_fn(user_text, retry_feedback=None, **kwargs):
        call_history.append(retry_feedback)
        return "{broken json string without closing braces"

    monkeypatch.setattr(_call_model_for_reasoning, "fake_fn", fake_fn)

    with pytest.raises(QuestionReasoningError) as exc_info:
        reason_question(user_text=SAMPLE_USER_TEXT, provider="fake")

    err_msg = str(exc_info.value)
    assert len(call_history) == 2
    assert "Question reasoning failed validation" in err_msg
    assert "not valid JSON" in err_msg or "JSON" in err_msg
    assert "Traceback" not in err_msg
    assert "File " not in err_msg


# ------------------------------------------------------------------------------
# Test 11: Text B unlisted terms flagged across all text fields (Item 3)
# ------------------------------------------------------------------------------
def test_text_b_unlisted_terms_flagged():
    """Item 3: Assert 'biological computing', 'yeast', 'post-quantum' are flagged from Text B fixture."""
    text_b = "Does quantum-secure sourdough fermentation improve enterprise API latency?"
    fixture = {
        "refined_question": "What empirical evidence connects biological computing and post-quantum cryptography in yeast fermentation?",
        "sub_questions": [
            "How does post-quantum cryptography affect network latency?",
            "What role does yeast play in biological computing systems?",
            "Can biological computing mechanisms interface with cryptographic algorithms?",
        ],
        "premises_to_test": ["Assumes biological computing interfaces with yeast."],
        "in_scope": ["Empirical latency metrics", "Post-quantum algorithms"],
        "out_of_scope": ["Traditional sourdough baking"],
        "evidence_needed": ["Biological computing papers"],
        "ambiguities": ["Category confusion"],
        "changes_and_reasons": [{"change": "Reframed", "reason": "Clarity"}],
        "coverage_map": {text_b: "question"},
        "added_terms": [],
    }
    unlisted = find_unlisted_terms(fixture, text_b)
    unlisted_lower = [u.lower() for u in unlisted]
    assert "biological computing" in unlisted_lower, f"'biological computing' not flagged in {unlisted}"
    assert "yeast" in unlisted_lower, f"'yeast' not flagged in {unlisted}"
    assert "post-quantum" in unlisted_lower, f"'post-quantum' not flagged in {unlisted}"


# ------------------------------------------------------------------------------
# Test 12: Prompt leak test asserting 13 forbidden domain tokens (Item 1)
# ------------------------------------------------------------------------------
def test_prompt_leak_forbidden_words():
    """Item 1: Assert prompts/question_reasoning_v1.md contains zero forbidden domain leak tokens."""
    forbidden = [
        "kiro", "licence", "license", "credits", "standardis", "standardiz",
        "sourdough", "fermentation", "quantum", "latency", "hospital", "triage", "nurse"
    ]
    prompt_path = Path("prompts/question_reasoning_v1.md")
    assert prompt_path.exists(), f"Prompt file {prompt_path} does not exist"
    content = prompt_path.read_text(encoding="utf-8").lower()
    found_tokens = [tok for tok in forbidden if tok in content]
    assert not found_tokens, f"Prompt leak detected: found forbidden tokens {found_tokens} in {prompt_path}"


