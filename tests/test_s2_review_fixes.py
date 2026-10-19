"""Tests for the PR #1 review findings on Slice S2.

Requirements (one per review finding):
1. The unlisted-terms confirmation does not carry over to a new proposal.
2. Reasoning uses the inference model the user selected, not always Ollama.
3. After "Re-reason with feedback", the editable fields show the new proposal.
4. An edited package that breaks the schema cannot be approved.
5. A re-run (Feedback Loop 1) runs the approved refined question, not the raw input text.
6. Faithfulness: a model-introduced number or term is not hidden by substring matches.
7. Coverage: a trivial coverage_map key does not mark every sentence as covered.
8. Validation returns schema errors, not a TypeError, when sub_questions is not a list.
9. The approval records the model that reasoned, not just the provider.
10. The reasoner builds its model client through src.llm.factory.build_llm.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest
from streamlit.testing.v1 import AppTest

from src.engine.reasoner import (
    _call_model_for_reasoning,
    find_unlisted_terms,
    reason_question,
    resolve_model_name,
    validate_reasoned_package,
)
from src.ui.intake_view import approval_blockers, approved_question_text, effective_provider

USER_TEXT = (
    "Our engineering org is adopting AI coding assistants like Copilot and Kiro. "
    "Leadership wants to know the measurable productivity impact on delivery teams."
)

BASE_PKG: Dict[str, Any] = {
    "refined_question": "What measurable productivity impact do AI coding assistants have on delivery teams?",
    "sub_questions": ["How does cycle time change?", "How does defect density change?", "What trade-offs appear?"],
    "premises_to_test": [],
    "in_scope": ["delivery teams"],
    "out_of_scope": ["consumer apps"],
    "evidence_needed": [],
    "ambiguities": [],
    "changes_and_reasons": [],
    "added_terms": [],
}


def _intake_app():
    from src.ui.intake_view import render_intake_view

    render_intake_view()


def _reasoned_intake(monkeypatch) -> AppTest:
    monkeypatch.setenv("STUB_LLM", "1")
    at = AppTest.from_function(_intake_app, default_timeout=60)
    at.run()
    at.text_area(key="input_user_question").input(USER_TEXT).run()
    at.button(key="btn_reason_question").click().run()
    return at


# ------------------------------------------------------------------------------
# Test 1: Terms confirmation does not carry over to a new proposal
# ------------------------------------------------------------------------------
def test_terms_confirmation_resets_for_a_new_proposal(monkeypatch):
    at = _reasoned_intake(monkeypatch)
    boxes = [c for c in at.checkbox if "I acknowledge" in str(c.label)]
    assert boxes, "stub proposal introduces terms, so the confirmation must show"
    boxes[0].check().run()
    assert not at.button(key="btn_approve_reasoned_package").disabled

    at.text_input(key="input_s2_user_feedback").input("Focus on code review bottlenecks.").run()
    at.button(key="btn_rereason_feedback").click().run()
    boxes = [c for c in at.checkbox if "I acknowledge" in str(c.label)]
    assert boxes and boxes[0].value is False, "v2 must be acknowledged on its own"
    assert at.button(key="btn_approve_reasoned_package").disabled


# ------------------------------------------------------------------------------
# Test 2: Reasoning uses the selected inference model
# ------------------------------------------------------------------------------
def test_effective_provider_and_web_app_wiring():
    assert effective_provider("gemini", has_gemini_key=True, ollama_ok=False) == "gemini"
    assert effective_provider("gemini", has_gemini_key=False, ollama_ok=True) == "ollama"
    assert effective_provider("gemini", has_gemini_key=False, ollama_ok=False) == "stub"
    assert effective_provider("stub", has_gemini_key=True, ollama_ok=True) == "stub"
    assert effective_provider("ollama", has_gemini_key=False, ollama_ok=True) == "ollama"
    src = Path("web_app.py").read_text(encoding="utf-8")
    assert 'st.session_state["selected_model_provider"] = effective_provider(' in src
    assert 'key="select_inference_model"' in src


# ------------------------------------------------------------------------------
# Test 3: Re-reasoned proposal replaces the editable fields
# ------------------------------------------------------------------------------
def test_rereason_replaces_editable_fields(monkeypatch):
    at = _reasoned_intake(monkeypatch)
    v1 = [t.value for t in at.text_input if "Refined Research Question" in str(t.label)][0]
    at.text_input(key="input_s2_user_feedback").input("Focus on code review bottlenecks.").run()
    at.button(key="btn_rereason_feedback").click().run()
    v2 = [t.value for t in at.text_input if "Refined Research Question" in str(t.label)][0]
    assert v2 != v1
    assert v2 == at.session_state["s2_active_package"]["refined_question"]


# ------------------------------------------------------------------------------
# Test 4: Edited packages that break the schema cannot be approved
# ------------------------------------------------------------------------------
def test_invalid_edits_block_approval(monkeypatch):
    assert approval_blockers(BASE_PKG) == []
    assert approval_blockers({**BASE_PKG, "refined_question": ""})
    assert approval_blockers({**BASE_PKG, "refined_question": "No question mark"})
    assert approval_blockers({**BASE_PKG, "sub_questions": ["Only one?"]})
    assert approval_blockers({**BASE_PKG, "sub_questions": [f"Q{i}?" for i in range(6)]})

    at = _reasoned_intake(monkeypatch)
    for c in at.checkbox:
        if "I acknowledge" in str(c.label):
            c.check()
    at.run()
    sub_box = [t for t in at.text_area if "Sub-Questions" in str(t.label)][0]
    sub_box.input("").run()
    assert at.button(key="btn_approve_reasoned_package").disabled


# ------------------------------------------------------------------------------
# Test 5: Re-runs use the approved refined question
# ------------------------------------------------------------------------------
def test_rerun_uses_approved_refined_question():
    pkg = {"refined_question": "What measurable productivity impact do AI coding assistants have?"}
    assert approved_question_text(pkg, {"strategic_question": "raw typed text"}) == pkg["refined_question"]
    assert approved_question_text(None, {"strategic_question": "Question the run used"}) == "Question the run used"
    src = Path("web_app.py").read_text(encoding="utf-8")
    assert 'topic=st.session_state["current_question"]' not in src


# ------------------------------------------------------------------------------
# Test 6: Substring matches do not hide model-introduced terms
# ------------------------------------------------------------------------------
def test_unlisted_terms_use_whole_word_matching():
    user = "Our 25 developers use Copilot. Is it worth it?"
    pkg = {"refined_question": "Does Copilot improve output within 5 sprints?", "added_terms": []}
    assert "5" in find_unlisted_terms(pkg, user)
    pkg2 = {"refined_question": "How does maintainability change with Copilot?", "added_terms": ["ai"]}
    assert any("maintainability" in t for t in find_unlisted_terms(pkg2, user))
    pkg3 = {"refined_question": "How do 25 developers use Copilot?", "added_terms": []}
    assert find_unlisted_terms(pkg3, user) == []
    pkg4 = {"refined_question": "How does GitLab Duo compare with Copilot?", "added_terms": ["GitLab Duo"]}
    assert not any("gitlab" in t.lower() for t in find_unlisted_terms(pkg4, user))


# ------------------------------------------------------------------------------
# Test 7: Trivial coverage keys do not cover every sentence
# ------------------------------------------------------------------------------
def test_trivial_coverage_keys_are_rejected():
    text = "The team ships weekly. Is the tool worth it?"
    for trivial in ({"the": "question"}, {"": "scope"}, {"is": "premise"}):
        ok, errs = validate_reasoned_package({**BASE_PKG, "coverage_map": trivial}, text)
        assert any("Coverage error" in e for e in errs), trivial
    ok, errs = validate_reasoned_package(
        {**BASE_PKG, "coverage_map": {"The team ships weekly": "scope", "is the tool worth it?": "question"}}, text
    )
    assert not any("Coverage error" in e for e in errs), errs


# ------------------------------------------------------------------------------
# Test 8: Non-list sub_questions gives schema errors, not a crash
# ------------------------------------------------------------------------------
def test_non_list_sub_questions_returns_errors():
    for bad in ("How does X affect Y?", {"q": "How?"}, None):
        ok, errs = validate_reasoned_package({**BASE_PKG, "sub_questions": bad, "coverage_map": {}}, "x.")
        assert not ok and any("sub_questions" in e for e in errs)


# ------------------------------------------------------------------------------
# Test 9: Approval records the model, not just the provider
# ------------------------------------------------------------------------------
def test_approval_records_model_name(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    assert resolve_model_name("ollama") == "qwen2.5:3b-instruct"
    assert resolve_model_name("gemini") == "gemini-2.5-flash"
    assert resolve_model_name("stub") == "stub"

    at = _reasoned_intake(monkeypatch)
    for c in at.checkbox:
        if "I acknowledge" in str(c.label):
            c.check()
    at.run()
    at.button(key="btn_approve_reasoned_package").click().run()
    approvals = list(Path(__import__("os").environ["RESEARCH_APPROVALS_DIR"]).rglob("gate1-v*.json"))
    assert approvals
    record = json.loads(approvals[-1].read_text())
    assert record["provider"] == "stub" or record["model_name"] != record["provider"]
    assert record["model_name"] == resolve_model_name(record["provider"])


# ------------------------------------------------------------------------------
# Test 10: Reasoner uses build_llm
# ------------------------------------------------------------------------------
def test_reasoner_builds_client_through_factory(monkeypatch):
    built: Dict[str, Any] = {}

    class FakeClient:
        model = "fake-model"

        def generate(self, prompt, system_prompt=None, temperature=0.3, json_mode=False):
            return json.dumps({**BASE_PKG, "coverage_map": {s: "question" for s in ["Is AI useful?"]}})

    def fake_build(provider, config):
        built["provider"] = provider
        built["config_keys"] = sorted(config)
        return FakeClient()

    monkeypatch.setattr("src.llm.factory.build_llm", fake_build)
    monkeypatch.setattr("src.llm.ollama_client.is_ollama_reachable", lambda *a, **k: True)
    monkeypatch.delenv("STUB_LLM", raising=False)
    out = _call_model_for_reasoning("Is AI useful?", None, "ollama", None, None, None)
    assert built["provider"] == "ollama"
    assert "Is AI useful?" in json.loads(out)["coverage_map"]
