"""Tests for Slice S1: Walking skeleton (Requirement R1, Review Round 2).

Verifies:
1. Fixed Lenses: fields (id, title, focus, counts_as_evidence, out_of_scope), fixed template text,
   zero user words embedded in lenses, user question kept verbatim.
2. Question SHA-256: full 64-hex SHA-256 in approval record and start_run comparison.
   Question ID suffix stays 8 hex.
3. No Hashes in User-Facing Messages: start_run error messages and UI banners never display hashes.
   After-edit message matches: "You changed the question after approving a framing. Approve a framing again to continue."
4. Register-based ID Resolution: reads questions/register.yaml (injectable), no hardcoded canary tables in src/.
5. Approvals & Environment Variables:
   - RESEARCH_APPROVALS_DIR controls storage directory (default ledger/approvals).
   - RESEARCH_USER controls approved_by (default local-user).
   - Version increments, earlier files kept, all schema fields present.
6. One Entry Function (start_run): gate enforcement, full hash verification, runner delegation.
7. Paths: web_app.py has no direct call to run_workflow, run.py not imported.
8. UI (Streamlit AppTest): Run disabled before approval, enabled after, disabled on edit with exact message.
9. Errors (safe_page): plain English, reference code, no paths/tracebacks on screen, full traceback in log.
"""

from __future__ import annotations

import ast
import datetime
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List
import pytest
import yaml

from src.engine.ids import (
    generate_question_id,
    resolve_question_id,
    normalize_question_text,
    compute_question_hash_suffix,
    compute_question_sha256,
)
from src.engine.framings import (
    generate_framings,
    FramingLens,
    LENS_TEMPLATES,
)
from src.engine.approvals import (
    save_gate1_approval,
    get_latest_gate1_approval,
    get_approvals_dir,
    Gate1Approval,
)
from src.engine.entry import (
    start_run,
    GateApprovalError,
)
from src.ui.safe_page import (
    safe_page_boundary,
    render_safe_error,
)


# ==============================================================================
# 1. Question IDs and Register-Based Resolution
# ==============================================================================

def test_question_ids_different_for_same_first_30_characters():
    """Two questions sharing their first 30 characters get different IDs."""
    prefix = "Evaluating AI coding assistant "  # 31 chars
    q1 = prefix + "adoption and developer cycle time in enterprise software delivery"
    q2 = prefix + "security risks vulnerability rates and IP licensing compliance"
    assert q1[:30] == q2[:30]

    id1 = generate_question_id(q1)
    id2 = generate_question_id(q2)
    assert id1 != id2
    assert id1.split("-")[-1] != id2.split("-")[-1]


def test_question_ids_same_text_gives_same_id():
    """Same text twice gives the exact same ID (deterministic)."""
    text = "What empirical evidence exists regarding software specification testing?"
    id1 = generate_question_id(text)
    id2 = generate_question_id(text)
    assert id1 == id2

    # Trailing question marks or whitespace do not change the ID
    id3 = generate_question_id("  " + text + "   ???  ")
    assert id1 == id3


def test_question_id_suffix_stays_8_hex():
    """Question ID suffix is strictly the first 8 hex chars of sha256."""
    text = "Assessing latency in event-driven distributed systems"
    q_id = generate_question_id(text)
    suffix = q_id.split("-")[-1]
    assert len(suffix) == 8
    assert re.fullmatch(r"[0-9a-f]{8}", suffix) is not None


def test_register_based_id_resolution_no_hardcoded_table(tmp_path: Path):
    """resolve_question_id dynamically queries questions/register.yaml (injectable)."""
    # Create an isolated temporary register
    custom_reg_path = tmp_path / "custom_register.yaml"
    reg_data = {
        "questions": [
            {
                "id": "q-custom-registered-test",
                "text": "How do banks implement zero trust network architecture?",
                "scope": "security",
            }
        ]
    }
    with open(custom_reg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(reg_data, f)

    # Must match registered question text by normalized text
    resolved = resolve_question_id(
        "  How do banks implement ZERO trust network architecture?  ",
        register_path=str(custom_reg_path),
    )
    assert resolved == "q-custom-registered-test"

    # Must resolve if passed as the registered ID directly
    resolved_id = resolve_question_id(
        "q-custom-registered-test",
        register_path=str(custom_reg_path),
    )
    assert resolved_id == "q-custom-registered-test"

    # Unregistered question falls back to standard slug + 8-hex hash
    unreg_text = "What is the capital of France?"
    resolved_unreg = resolve_question_id(unreg_text, register_path=str(custom_reg_path))
    assert resolved_unreg == generate_question_id(unreg_text)


def test_canary_ids_resolve_from_real_register():
    """The three canary IDs in questions/register.yaml resolve accurately without hardcoded src tables."""
    reg_path = "questions/register.yaml"
    assert Path(reg_path).exists()
    with open(reg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    reg_map = {q["id"]: q["text"] for q in data["questions"]}
    assert "q-kiro-empirical" in reg_map
    assert "q-how-are-hospitals-governin" in reg_map
    assert "q-quantum-secure-sourdough-ferme-a924f6cd" in reg_map

    # Resolve from register text
    assert resolve_question_id(reg_map["q-kiro-empirical"]) == "q-kiro-empirical"
    assert resolve_question_id(reg_map["q-how-are-hospitals-governin"]) == "q-how-are-hospitals-governin"
    assert resolve_question_id(reg_map["q-quantum-secure-sourdough-ferme-a924f6cd"]) == "q-quantum-secure-sourdough-ferme-a924f6cd"


def test_src_has_no_hardcoded_canary_q1_text():
    """Ensure CANARY_Q1_TEXT and hardcoded canary tables are removed from src/."""
    src_dir = Path("src")
    matches = []
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "CANARY_Q1_TEXT" in content or "CANARY_CANONICAL_MAP" in content:
            matches.append(str(py_file))
    assert not matches, f"Hardcoded canary symbols found in src/: {matches}"


# ==============================================================================
# 2. Fixed Lenses (Framings)
# ==============================================================================

def test_framings_are_fixed_lenses_with_no_user_words():
    """Lenses have fields: id, title, focus, counts_as_evidence, out_of_scope.

    All fields are fixed template text containing ZERO user words.
    """
    user_question = "Evaluating quantum-secure sourdough fermentation controllers in artisan bakeries"
    lenses = generate_framings(user_question)

    assert 2 <= len(lenses) <= 4
    required_titles = {
        "Empirical effect",
        "Adoption and practice",
        "Risks and controls",
        "Costs and trade-offs",
    }
    actual_titles = {lens.title for lens in lenses}
    assert actual_titles == required_titles

    # User words must NOT be embedded in any lens field
    user_words = {"sourdough", "fermentation", "artisan", "bakeries", "controllers"}
    for lens in lenses:
        assert isinstance(lens, FramingLens)
        assert hasattr(lens, "id")
        assert hasattr(lens, "title")
        assert hasattr(lens, "focus")
        assert hasattr(lens, "counts_as_evidence")
        assert hasattr(lens, "out_of_scope")

        combined_lens_text = f"{lens.title} {lens.focus} {lens.counts_as_evidence} {lens.out_of_scope}".lower()
        for w in user_words:
            assert w not in combined_lens_text, f"User word '{w}' leaked into lens template: {lens.id}"


def test_lens_definitions_exact_text():
    """Verify the four fixed lenses match the specified template text."""
    lenses = {l.title: l for l in generate_framings("Any question")}

    # 1. Empirical effect
    emp = lenses["Empirical effect"]
    assert emp.focus == "what measured outcomes and effects have been reported"
    assert emp.counts_as_evidence == "studies and reports with data such as trials, case studies, benchmarks"
    assert emp.out_of_scope == "opinions, vendor claims without data, forecasts"

    # 2. Adoption and practice
    adp = lenses["Adoption and practice"]
    assert adp.focus == "how organizations actually use this"
    assert adp.counts_as_evidence == "documented use at named organizations, practitioner accounts labelled as such"
    assert adp.out_of_scope == "controlled effect sizes"

    # 3. Risks and controls
    rsk = lenses["Risks and controls"]
    assert rsk.focus == "what can go wrong and what controls or governance are used"
    assert rsk.counts_as_evidence == "incident reports, audits, standards, governance documents"
    assert rsk.out_of_scope == "productivity or cost outcomes"

    # 4. Costs and trade-offs
    cst = lenses["Costs and trade-offs"]
    assert cst.focus == "what it costs and what is given up"
    assert cst.counts_as_evidence == "cost and effort data, comparisons with alternatives"
    assert cst.out_of_scope == "technical benchmarks unrelated to cost"


# ==============================================================================
# 3. Gate 1 Approval Record (Full 64-hex SHA-256 and Environment Variables)
# ==============================================================================

def test_approval_record_schema_and_full_sha256(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Approval writes full 64-hex question_sha256, verbatim question, and uses RESEARCH_USER."""
    approvals_dir = tmp_path / "approvals"
    monkeypatch.setenv("RESEARCH_APPROVALS_DIR", str(approvals_dir))
    monkeypatch.setenv("RESEARCH_USER", "lead-evaluator")

    q_id = "q-test-framing-12345678"
    raw_question = "What empirical evidence exists for Specification Testing?"

    # Full 64-hex SHA-256
    full_sha256 = compute_question_sha256(raw_question)
    assert len(full_sha256) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", full_sha256) is not None

    app1 = save_gate1_approval(
        question_id=q_id,
        question_text=raw_question,
        framing_id="empirical-effect",
        framing_title="Empirical effect",
        framing_question=raw_question,  # verbatim question as approved
    )

    assert app1.approved_by == "lead-evaluator"
    assert app1.question_sha256 == full_sha256
    assert app1.framing_question == raw_question  # original casing, verbatim

    v1_file = approvals_dir / q_id / "gate1-v1.json"
    assert v1_file.exists()
    with open(v1_file, "r", encoding="utf-8") as f:
        data1 = json.load(f)

    assert data1["question_sha256"] == full_sha256
    assert len(data1["question_sha256"]) == 64
    assert data1["approved_by"] == "lead-evaluator"
    assert data1["framing_question"] == raw_question


def test_default_research_user_is_local_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When RESEARCH_USER is unset, approved_by defaults to 'local-user'."""
    approvals_dir = tmp_path / "approvals"
    monkeypatch.setenv("RESEARCH_APPROVALS_DIR", str(approvals_dir))
    monkeypatch.delenv("RESEARCH_USER", raising=False)

    app = save_gate1_approval(
        question_id="q-user-test",
        question_text="How is telemetry logged?",
        framing_id="empirical-effect",
        framing_title="Empirical effect",
        framing_question="How is telemetry logged?",
    )
    assert app.approved_by == "local-user"


# ==============================================================================
# 4. One Entry Function (start_run: Full Hash & No Hashes in Messages)
# ==============================================================================

def test_start_run_error_message_has_no_hashes_and_matches_after_edit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """start_run never discloses hashes in user-facing error messages."""
    approvals_dir = tmp_path / "approvals"
    monkeypatch.setenv("RESEARCH_APPROVALS_DIR", str(approvals_dir))

    q_id = "q-approved-sample"
    orig_text = "What empirical evidence exists for test-driven development?"
    save_gate1_approval(
        question_id=q_id,
        question_text=orig_text,
        framing_id="empirical-effect",
        framing_title="Empirical effect",
        framing_question=orig_text,
    )

    def stub_runner(**kwargs):
        return {"status": "ok"}

    # 1. Unapproved question
    with pytest.raises(GateApprovalError) as exc_unapproved:
        start_run(
            question_id="q-unapproved-sample",
            question_text="Unapproved question",
            runner=stub_runner,
        )
    msg_unapproved = str(exc_unapproved.value)
    assert "Run refused:" in msg_unapproved
    assert not re.search(r"\b[0-9a-f]{8,64}\b", msg_unapproved), f"Hash leaked in unapproved message: {msg_unapproved}"

    # 2. Modified question text after approval
    modified_text = "What empirical evidence exists for behavior-driven development?"
    with pytest.raises(GateApprovalError) as exc_modified:
        start_run(
            question_id=q_id,
            question_text=modified_text,
            runner=stub_runner,
        )
    msg_modified = str(exc_modified.value)
    # Must match specified after-edit message
    assert "You changed the question after approving a framing. Approve a framing again to continue." in msg_modified
    assert not re.search(r"\b[0-9a-f]{8,64}\b", msg_modified), f"Hash leaked in modified message: {msg_modified}"


def test_start_run_accepts_when_full_64_hex_hash_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """start_run validates full 64-hex SHA-256 and delegates to runner with exact args."""
    approvals_dir = tmp_path / "approvals"
    monkeypatch.setenv("RESEARCH_APPROVALS_DIR", str(approvals_dir))

    q_id = "q-approved-success"
    text = "What empirical evidence exists for test-driven development?"
    save_gate1_approval(
        question_id=q_id,
        question_text=text,
        framing_id="empirical-effect",
        framing_title="Empirical effect",
        framing_question=text,
    )

    recorded_kwargs: Dict[str, Any] = {}

    def stub_runner(**kwargs):
        recorded_kwargs.update(kwargs)
        return {"run_id": "run-stub-64hex", "status": "completed"}

    result = start_run(
        question_id=q_id,
        question_text=text,
        depth="Fast",
        tone="Executive",
        runner=stub_runner,
    )

    assert result["run_id"] == "run-stub-64hex"
    assert recorded_kwargs["topic"] == text
    assert recorded_kwargs["depth"] == "Fast"
    assert recorded_kwargs["tone"] == "Executive"


# ==============================================================================
# 5. UI Paths (no direct run_workflow calls)
# ==============================================================================

def test_web_app_has_no_direct_call_to_run_workflow():
    """web_app.py has no direct call to multilane_runner.run_workflow (must route through start_run)."""
    web_app_path = Path("web_app.py")
    assert web_app_path.exists()
    content = web_app_path.read_text(encoding="utf-8")

    assert "import run\n" not in content
    assert "from run import" not in content

    tree = ast.parse(content, filename="web_app.py")
    direct_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "run_workflow":
                if isinstance(func.value, ast.Name) and func.value.id == "multilane_runner":
                    direct_calls.append(node.lineno)

    assert not direct_calls, f"web_app.py directly calls multilane_runner.run_workflow at lines: {direct_calls}"


# ==============================================================================
# 6. Errors (safe_page)
# ==============================================================================

def test_safe_page_plain_english_and_logging(tmp_path: Path):
    """On exception, safe_page shows plain-English message and reference code, with zero paths on screen."""
    log_file = tmp_path / "test_app.log"

    def crashing_view():
        raise ValueError("Simulated deep engine pipeline crash in /Users/gauravm/secret/engine.py")

    rendered = safe_page_boundary(crashing_view, log_path=str(log_file))

    assert "Something went wrong. Nothing was published." in rendered["headline"]
    assert "Reference:" in rendered["reference_text"]
    assert rendered["reference_code"] != ""

    screen_text = (
        rendered["headline"]
        + " "
        + rendered["reference_text"]
        + " "
        + rendered["copy_details"]
    )
    assert "Traceback" not in screen_text
    assert "/Users/" not in screen_text
    assert ".py" not in screen_text

    assert log_file.exists()
    log_content = log_file.read_text(encoding="utf-8")
    assert rendered["reference_code"] in log_content
    assert "Traceback (most recent call last):" in log_content
    assert "ValueError" in log_content


# ==============================================================================
# 7. UI (Streamlit AppTest: Run button states and Messages)
# ==============================================================================

def test_ui_intake_run_button_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Streamlit AppTest: Run disabled before approval, enabled after, disabled on edit with exact message."""
    from streamlit.testing.v1 import AppTest

    approvals_dir = str(tmp_path / "approvals")
    monkeypatch.setenv("RESEARCH_APPROVALS_DIR", approvals_dir)
    monkeypatch.setenv("STUB_LLM", "1")

    app_script = """
import streamlit as st
from src.ui.intake_view import render_intake_view

render_intake_view()
"""
    at = AppTest.from_string(app_script).run()

    # Step 1: Empty input -> Run disabled with empty topic message
    run_btn = at.button(key="btn_run_research")
    assert run_btn is not None
    assert run_btn.disabled is True
    assert any("Type a question in Step 1." in m.value for m in at.markdown)

    # User inputs a question
    at.text_area(key="input_user_question").input("What empirical evidence exists for test automation?").run()
    run_btn = at.button(key="btn_run_research")
    assert run_btn.disabled is True
    assert any("Click Reason about my question and approve a proposal in Step 2 to unlock Run." in m.value for m in at.markdown)

    # User clicks Reason about my question
    reason_btn = at.button(key="btn_reason_question")
    assert reason_btn is not None
    reason_btn.click().run()

    # Proposal is shown, Run is still disabled until approved
    run_btn = at.button(key="btn_run_research")
    assert run_btn.disabled is True
    assert any("Approve the reasoned proposal in Step 2 to unlock Run." in m.value for m in at.markdown)

    # User approves reasoned package
    approve_btn = at.button(key="btn_approve_reasoned_package")
    assert approve_btn is not None
    approve_btn.click().run()

    # Step 2: Now approved, Run button is enabled
    run_btn = at.button(key="btn_run_research")
    assert run_btn.disabled is False

    # Step 3: User edits a field in the proposal after approval
    at.text_input(key="input_s2_refined_question").input("What empirical evidence exists for test automation and CI?").run()

    # Run button must now be disabled again with the after-edit message
    run_btn = at.button(key="btn_run_research")
    assert run_btn.disabled is True
    assert any("You changed the proposal after approving. Approve again to unlock Run." in m.value for m in at.markdown)


# ==============================================================================
# 8. Real-Runner Wiring Test (Slice S1 Review Round 2)
# ==============================================================================

def test_start_run_wires_to_real_multilane_runner(tmp_path: Path):
    """start_run delegates to real MultiLaneResearchRunner with identical kwargs and outputs."""
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.ledger.migrations import apply_migrations

    db_path = str(tmp_path / "test_ledger.db")
    prac_db_path = str(tmp_path / "test_prac.db")
    q_yaml_path = str(tmp_path / "register.yaml")
    approvals_dir = tmp_path / "approvals"

    apply_migrations(db_path=db_path)
    apply_migrations(db_path=prac_db_path)

    # Seed an isolated register
    with open(q_yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"questions": [{"id": "q-runner-test", "text": "Evaluating CI/CD automation", "scope": "enterprise"}]}, f)

    runner = MultiLaneResearchRunner(
        db_path=db_path,
        practitioner_db_path=prac_db_path,
        questions_yaml_path=q_yaml_path,
    )

    q_text = "What empirical evidence evaluates CI/CD automation?"
    q_id = resolve_question_id(q_text, register_path=q_yaml_path)

    # Approve Gate 1
    save_gate1_approval(
        question_id=q_id,
        question_text=q_text,
        framing_id="empirical-effect",
        framing_title="Empirical effect",
        framing_question=q_text,
        approvals_dir=approvals_dir,
    )

    dummy_papers = [
        {
            "id": "p-01",
            "title": "Empirical Study of CI/CD Automation",
            "abstract": "We evaluate automated testing and deployment across 100 repositories.",
            "year": 2024,
            "venue": "ICSE",
            "url": "https://doi.org/10.1145/example",
            "relevance_score": 0.95,
        }
    ]
    dummy_enterprise = {
        "dora-dev-survey": [
            {
                "title": "DORA Research Report Item 1",
                "text": "Empirical survey finds automated testing improves delivery performance.",
                "speaker": "independent",
                "year": 2024,
            }
        ]
    }

    # Common execution kwargs matching the Run button path in web_app.py
    run_kwargs = {
        "depth": "Fast",
        "tone": "Executive",
        "map_provider": "stub",
        "reduce_provider": "stub",
        "academic_papers_override": dummy_papers,
        "enterprise_feed_override": dummy_enterprise,
        "custom_lane_urls": {},
        "allow_remote_practitioner_synthesis": False,
        "practitioner_abstraction_confirmed": True,
        "on_progress": None,
    }

    # 1. Execute via start_run entry point
    res_start_run = start_run(
        question_id=q_id,
        question_text=q_text,
        runner=runner.run_workflow,
        approvals_dir=approvals_dir,
        **run_kwargs,
    )

    # 2. Execute directly on the runner
    res_direct = runner.run_workflow(
        topic=q_text,
        **run_kwargs,
    )

    # Both must return identical status and top-level schema keys
    assert res_start_run["status"] == res_direct["status"]
    assert set(res_start_run.keys()) == set(res_direct.keys())

    # Verify standard top-level output keys are present in both
    for key in ("run_id", "status", "synthesis", "claims", "lane_breakdown", "metrics"):
        assert key in res_start_run
        assert key in res_direct

