"""Tests for Slice S29a: one step per page instead of one long landing page.

Requirements:
1. Six steps: Ask, Scope, Sources & run, Brief, Evidence, Checks & share. Scope opens once a proposal exists, Sources &
   run once it is approved (or a run exists), the three result steps once results exist. A requested step that is not
   open falls back to Brief when results exist, else to the furthest open step.
2. The app moves on by itself: Reason -> Scope, Approve -> Sources & run, a finished or loaded run -> Brief,
   Start new research -> Ask. The step is kept in the URL (?step=).
3. render_intake_view(step=...) renders one block ("ask", "scope", "run"); step=None renders all three as before.
   Scope edits survive leaving the page and coming back; the Run page checks the package saved by the Scope page.
4. A fresh app shows only the Ask page. With results it opens on Brief, and Next walks Evidence then Checks & share
   (checks first, then the summary and share pack), each without errors.
5. Each page ends with Back and Next; the stepper marks the current, done and locked steps.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path("tests/fixtures/s18_saved_run.json")


# ------------------------------------------------------------------------------
# Test 1: Which steps are open
# ------------------------------------------------------------------------------
def test_available_steps_and_fallback():
    from src.ui.stepper import STEP_KEYS, available_steps, resolve_step

    assert STEP_KEYS == ["ask", "scope", "run", "brief", "evidence", "checks"]
    assert available_steps(False, False, False) == ["ask"]
    assert available_steps(True, False, False) == ["ask", "scope"]
    assert available_steps(True, True, False) == ["ask", "scope", "run"]
    assert available_steps(False, False, False, has_job=True) == ["ask", "scope", "run"]
    assert available_steps(False, False, True) == STEP_KEYS
    assert resolve_step("brief", ["ask"]) == "ask"
    assert resolve_step("checks", ["ask", "scope"]) == "scope"
    assert resolve_step(None, STEP_KEYS) == "brief"
    assert resolve_step("evidence", STEP_KEYS) == "evidence"
    assert resolve_step("nonsense", ["ask", "scope", "run"]) == "run"


def test_next_and_prev():
    from src.ui.stepper import next_step, prev_step

    avail = ["ask", "scope", "run"]
    assert next_step("scope", avail) == "run" and next_step("run", avail) is None
    assert prev_step("ask", avail) is None and prev_step("run", avail) == "scope"


def test_stepper_items_mark_states():
    from src.ui.stepper import stepper_items

    items = stepper_items("scope", ["ask", "scope", "run"])
    states = {i["key"]: i["state"] for i in items}
    assert states == {"ask": "done", "scope": "current", "run": "open", "brief": "locked",
                      "evidence": "locked", "checks": "locked"}
    labels = [i["label"] for i in items]
    assert labels[0].startswith("1") and "Ask" in labels[0] and "✓" in labels[0]
    assert "Checks & share" in labels[5]


# ------------------------------------------------------------------------------
# Test 2: Moving on by itself
# ------------------------------------------------------------------------------
def test_auto_advance_hooks_in_source():
    web = Path("web_app.py").read_text(encoding="utf-8")
    intake = Path("src/ui/intake_view.py").read_text(encoding="utf-8")
    assert 'go_to("scope")' in intake and 'go_to("run")' in intake
    assert 'go_to("brief")' in web and 'go_to("ask")' in web
    assert 'st.query_params["step"]' in Path("src/ui/stepper.py").read_text(encoding="utf-8")


# ------------------------------------------------------------------------------
# Test 3: One intake block per page
# ------------------------------------------------------------------------------
_SCRIPT = """
import streamlit as st
from src.ui.intake_view import render_intake_view
render_intake_view(step=st.session_state.get("_t_step"))
"""


def _intake_app(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("RESEARCH_APPROVALS_DIR", str(tmp_path / "approvals"))
    monkeypatch.setenv("STUB_LLM", "1")
    return AppTest.from_string(_SCRIPT)


def test_intake_steps_render_one_block(monkeypatch, tmp_path):
    at = _intake_app(monkeypatch, tmp_path)
    at.session_state["_t_step"] = "ask"
    at.run()
    keys = {b.key for b in at.button}
    assert "btn_reason_question" in keys and "btn_run_research" not in keys
    at.text_area(key="input_user_question").input("What evidence exists on four-day work weeks and productivity?").run()
    at.button(key="btn_reason_question").click().run()
    assert not at.exception, at.exception
    assert at.session_state["page"] == "scope"

    at.session_state["_t_step"] = "scope"
    at.run()
    keys = {b.key for b in at.button}
    assert "btn_approve_reasoned_package" in keys and "btn_reason_question" not in keys
    assert not any(t.key == "input_user_question" for t in at.text_area)
    at.button(key="btn_approve_reasoned_package").click().run()
    assert at.session_state["page"] == "run"

    at.session_state["_t_step"] = "run"
    at.run()
    assert at.button(key="btn_run_research").disabled is False, "the Run page checks the package the Scope page saved"


def test_scope_edits_survive_leaving_the_page(monkeypatch, tmp_path):
    at = _intake_app(monkeypatch, tmp_path)
    at.session_state["_t_step"] = "ask"
    at.run()
    at.text_area(key="input_user_question").input("What evidence exists on four-day work weeks and productivity?").run()
    at.button(key="btn_reason_question").click().run()
    at.session_state["_t_step"] = "scope"
    at.run()
    at.button(key="btn_approve_reasoned_package").click().run()
    at.session_state["_t_step"] = "scope"
    at.run()
    at.text_input(key="input_s2_refined_question").input("Edited question about four-day weeks?").run()
    at.session_state["_t_step"] = "run"
    at.run()
    assert at.button(key="btn_run_research").disabled is True
    assert any("Approve again" in m.value for m in at.markdown)
    at.session_state["_t_step"] = "scope"
    at.run()
    assert at.text_input(key="input_s2_refined_question").value == "Edited question about four-day weeks?"


# ------------------------------------------------------------------------------
# Test 4: The whole app
# ------------------------------------------------------------------------------
def test_fresh_app_shows_only_ask():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("web_app.py")
    at.run(timeout=30)
    assert not at.exception, at.exception
    assert any(t.key == "input_user_question" for t in at.text_area)
    keys = {b.key for b in at.button}
    assert "btn_run_research" not in keys and "btn_approve_reasoned_package" not in keys
    assert at.session_state["page"] == "ask"


def test_results_open_on_brief_and_next_walks_the_pages():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("web_app.py")
    at.session_state["research_results"] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    at.run(timeout=30)
    assert not at.exception, at.exception
    assert at.session_state["page"] == "brief"
    assert not any(t.key == "input_user_question" for t in at.text_area)

    at.button(key="nav_next").click().run(timeout=30)
    assert not at.exception, at.exception
    assert at.session_state["page"] == "evidence"
    md = " ".join(m.value for m in at.markdown)
    assert "### Evidence" in md and "### Claims & gaps" in md and "### Checks & publish" not in md

    at.button(key="nav_next").click().run(timeout=30)
    assert not at.exception, at.exception
    assert at.session_state["page"] == "checks"
    md = " ".join(m.value for m in at.markdown)
    assert "### Checks & publish" in md and "### Evidence" not in md
    assert not any(b.key == "nav_next" for b in at.button), "last step has no Next"

    at.button(key="nav_back").click().run(timeout=30)
    assert at.session_state["page"] == "evidence"


def test_checks_page_puts_summary_after_checks():
    web = Path("web_app.py").read_text(encoding="utf-8")
    checks = web.index('if page == "checks":')
    summary = web.index("SUMMARY & SHARE")
    assert summary > checks, "the summary and share pack follow the checks"
    assert "st.tabs([" not in web and "with tab_" not in web
