"""Unit and regression tests for UI polish of the intake screen (Slice S1 Round 3).

Verifies:
1. Components: status_badge, disabled_reason, info_box return expected text and color constants.
2. Exact copy:
   - Banner title: "Frame your question"
   - Banner subtitle: "Type your question, pick the angle you want researched, approve it, then run."
   - Step 1 button: "Show framings"
   - Approval message: "Framing approved. You can now run the research."
   - Disabled reasons:
     - no question -> "Type a question in Step 1."
     - not approved -> "Approve a framing in Step 2 to unlock Run."
     - edited after approval -> "You changed the question after approving. Approve a framing again."
3. Glossary test (forbidden terms on intake screen):
   - "Gate", "sha", question id pattern like q-xxxx, "Agent", "hash" must never appear
     in visible text across empty, framings shown, approved, and edited-after-approval states.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List
import pytest
from streamlit.testing.v1 import AppTest

from src.ui.theme import (
    COLOR_PRIMARY,
    COLOR_TEXT_PRIMARY,
    COLOR_STATUS_PUBLISH_READY_TEXT,
    COLOR_STATUS_PUBLISH_READY_BG,
    COLOR_STATUS_REVISE_TEXT,
    COLOR_STATUS_REVISE_BG,
    COLOR_STATUS_BLOCKED_TEXT,
    COLOR_STATUS_BLOCKED_BG,
    COLOR_STATUS_NOT_PUBLISHABLE_TEXT,
    COLOR_STATUS_NOT_PUBLISHABLE_BG,
    COLOR_DISABLED_BOX_BG,
    COLOR_DISABLED_BOX_TEXT,
    COLOR_INFO_BOX_BG,
    COLOR_INFO_BOX_TEXT,
)
from src.ui.components import (
    status_badge,
    disabled_reason,
    info_box,
)


# ==============================================================================
# 1. Component Tests
# ==============================================================================

def test_status_badge_publish_ready():
    html = status_badge("PUBLISH_READY", "Verified empirical evidence across 3 lanes")
    assert "PUBLISH READY" in html
    assert COLOR_STATUS_PUBLISH_READY_TEXT in html
    assert COLOR_STATUS_PUBLISH_READY_BG in html
    assert "Verified empirical evidence across 3 lanes" in html


def test_status_badge_revise():
    html = status_badge("REVISE", "Missing enterprise telemetry")
    assert "REVISE" in html
    assert COLOR_STATUS_REVISE_TEXT in html
    assert COLOR_STATUS_REVISE_BG in html
    assert "Missing enterprise telemetry" in html


def test_status_badge_blocked():
    html = status_badge("BLOCKED", "Enterprise vendor claim contradiction")
    assert "BLOCKED" in html
    assert COLOR_STATUS_BLOCKED_TEXT in html
    assert COLOR_STATUS_BLOCKED_BG in html
    assert "Enterprise vendor claim contradiction" in html


def test_status_badge_not_publishable():
    html = status_badge("NOT_PUBLISHABLE", "Zero peer-reviewed literature found")
    assert "NOT PUBLISHABLE" in html
    assert COLOR_STATUS_NOT_PUBLISHABLE_TEXT in html
    assert COLOR_STATUS_NOT_PUBLISHABLE_BG in html
    assert "Zero peer-reviewed literature found" in html


def test_disabled_reason_component():
    msg = "Type a question in Step 1."
    html = disabled_reason(msg)
    assert msg in html
    assert COLOR_DISABLED_BOX_BG in html
    assert COLOR_DISABLED_BOX_TEXT in html


def test_info_box_component():
    msg = "Enter your question to inspect candidate angles."
    html = info_box(msg)
    assert msg in html
    assert COLOR_INFO_BOX_BG in html
    assert COLOR_INFO_BOX_TEXT in html


# ==============================================================================
# 2. Exact Copy & Lifecycle Tests
# ==============================================================================

APP_SCRIPT = """
import streamlit as st
from src.ui.intake_view import render_intake_view

render_intake_view()
"""


def _extract_all_visible_text(at: AppTest) -> str:
    parts: List[str] = []
    for el in at.markdown:
        parts.append(el.value)
    for el in at.button:
        parts.append(el.label)
    for el in at.text_area:
        parts.append(el.label)
        if el.value:
            parts.append(el.value)
    for el in at.radio:
        parts.append(el.label)
    for el in at.info:
        parts.append(el.value)
    for el in at.success:
        parts.append(el.value)
    for el in at.warning:
        parts.append(el.value)
    for el in at.error:
        parts.append(el.value)
    return " ".join(parts)


def test_intake_screen_exact_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify exact copy strings defined in Task 2."""
    approvals_dir = str(tmp_path / "approvals")
    monkeypatch.setenv("RESEARCH_APPROVALS_DIR", approvals_dir)
    monkeypatch.setenv("STUB_LLM", "1")

    at = AppTest.from_string(APP_SCRIPT).run()

    # Banner title and subtitle
    all_text = _extract_all_visible_text(at)
    assert "Frame your question" in all_text
    assert "Type your question, pick the angle you want researched, approve it, then run." in all_text

    # Step 1 button label: "🧠 Reason about my question"
    reason_btn = at.button(key="btn_reason_question")
    assert reason_btn is not None
    assert "Reason about my question" in reason_btn.label

    # Step 3 disabled reason when empty
    assert "Type a question in Step 1." in all_text

    # Type question in Step 1
    q_text = "What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?"
    at.text_area(key="input_user_question").input(q_text).run()

    # Step 3 disabled reason when not reasoned yet
    all_text_typed = _extract_all_visible_text(at)
    assert "Click Reason about my question and approve a proposal in Step 2 to unlock Run." in all_text_typed

    # Click Reason about my question
    at.button(key="btn_reason_question").click().run()

    # Step 3 disabled reason when reasoned but not approved
    all_text_reasoned = _extract_all_visible_text(at)
    assert "Approve the reasoned proposal in Step 2 to unlock Run." in all_text_reasoned

    # Approve reasoned package in Step 2
    approve_btn = at.button(key="btn_approve_reasoned_package")
    assert approve_btn is not None
    approve_btn.click().run()

    # Approval message: "Reasoned question approved. You can now run the research." No ID.
    all_text_approved = _extract_all_visible_text(at)
    assert "Reasoned question approved. You can now run the research." in all_text_approved
    assert "q-" not in all_text_approved

    # Edit question after approval
    at.text_input(key="input_s2_refined_question").input(q_text + " and code quality").run()
    all_text_edited = _extract_all_visible_text(at)
    assert "You changed the proposal after approving. Approve again to unlock Run." in all_text_edited


# ==============================================================================
# 3. Glossary Test (Prohibited Terms)
# ==============================================================================

FORBIDDEN_PATTERNS = [
    re.compile(r"\b[Gg]ate\b"),
    re.compile(r"\bsha\b", re.IGNORECASE),
    re.compile(r"\bq-[a-z0-9-]+"),
    re.compile(r"\b[Aa]gent\b"),
    re.compile(r"\bhash\b", re.IGNORECASE),
]


def _assert_no_forbidden_terms(text: str, state_name: str):
    for pattern in FORBIDDEN_PATTERNS:
        match = pattern.search(text)
        assert match is None, (
            f"Forbidden term '{match.group(0)}' (matched {pattern.pattern}) "
            f"found on intake screen in state: {state_name}.\nText:\n{text}"
        )


def test_intake_screen_glossary_prohibitions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The intake screen must never display Gate, sha, q-xxxx, Agent, or hash across all 4 states."""
    approvals_dir = str(tmp_path / "approvals")
    monkeypatch.setenv("RESEARCH_APPROVALS_DIR", approvals_dir)
    monkeypatch.setenv("STUB_LLM", "1")

    at = AppTest.from_string(APP_SCRIPT).run()

    # State 1: Empty
    text_empty = _extract_all_visible_text(at)
    _assert_no_forbidden_terms(text_empty, "empty")

    # State 2: Reasoned proposal shown
    q_text = "What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?"
    at.text_area(key="input_user_question").input(q_text).run()
    at.button(key="btn_reason_question").click().run()
    text_proposal = _extract_all_visible_text(at)
    _assert_no_forbidden_terms(text_proposal, "proposal shown")

    # State 3: Approved
    at.button(key="btn_approve_reasoned_package").click().run()
    text_approved = _extract_all_visible_text(at)
    _assert_no_forbidden_terms(text_approved, "approved")

    # State 4: Edited after approval
    at.text_input(key="input_s2_refined_question").input(q_text + " and code review speed").run()
    text_edited = _extract_all_visible_text(at)
    _assert_no_forbidden_terms(text_edited, "edited after approval")


# ==============================================================================
# 4. Visual Styles: Card Padding & Disabled Button Styling
# ==============================================================================

def test_intake_view_card_padding_restored():
    """Padding on 'Frame your question' and lens card is 16px all round, with no broken single quotes."""
    intake_file = Path("src/ui/intake_view.py")
    content = intake_file.read_text(encoding="utf-8")
    assert "padding: 16px;" in content or "padding: 16px" in content
    # Ensure no broken single quotes inside style attributes
    assert "border-radius: 12px; '" not in content
    assert "border-radius: 8px; '" not in content


def test_disabled_button_css_has_flat_grey_and_no_gradient():
    """Disabled button has flat grey background and no gradient; enabled primary is solid blue."""
    web_app_file = Path("web_app.py")
    content = web_app_file.read_text(encoding="utf-8")

    # Disabled button must have background-image: none !important and #E2E8F0
    assert "button:disabled" in content or "button[disabled]" in content
    assert "background-image: none !important;" in content
    assert "#E2E8F0" in content

    # Enabled primary button must not apply gradient to disabled buttons
    assert 'button[kind="primary"]:not(:disabled)' in content

