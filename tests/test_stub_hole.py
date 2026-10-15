"""Tests for closing the stub mode loophole (Slice S1 Round 4).

Verifies:
1. is_stub_mode(env):
   - STUB_LLM=1 -> True
   - env unset -> False
   - STUB_LLM=1 with HOSTED_DEMO=1 -> False
2. Query-param activation removed:
   - Opening with ?stub=1 or ?mock=1 and no STUB_LLM env var shows NO stub banner
     and does not activate stub mode.
3. Persistent red banner:
   - With STUB_LLM=1 and HOSTED_DEMO unset, persistent banner:
     "TEST MODE: synthetic data. Results are not real and cannot be published."
     is displayed at the top of the page.
4. Run in stub mode cannot return a publishable status:
   - Execution in stub mode marks result as non-publishable and carries stub marker.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
import pytest
from streamlit.testing.v1 import AppTest

from src.engine.stub_mode import is_stub_mode
from src.engine.entry import start_run
from src.engine.approvals import save_gate1_approval
from src.engine.ids import resolve_question_id


# ==============================================================================
# 1. Unit Tests for is_stub_mode
# ==============================================================================

def test_is_stub_mode_env_truthy():
    assert is_stub_mode({"STUB_LLM": "1"}) is True


def test_is_stub_mode_env_unset():
    assert is_stub_mode({}) is False
    assert is_stub_mode({"STUB_LLM": "0"}) is False


def test_is_stub_mode_disabled_when_hosted_demo_active():
    assert is_stub_mode({"STUB_LLM": "1", "HOSTED_DEMO": "1"}) is False
    assert is_stub_mode({"STUB_LLM": "1", "HOSTED_DEMO": "true"}) is False
    assert is_stub_mode({"HOSTED_DEMO": "1"}) is False


def test_is_stub_mode_reads_os_environ_when_arg_none(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STUB_LLM", "1")
    monkeypatch.delenv("HOSTED_DEMO", raising=False)
    assert is_stub_mode() is True

    monkeypatch.setenv("HOSTED_DEMO", "1")
    assert is_stub_mode() is False


# ==============================================================================
# 2. AppTest: Query Params Ignored (No Stub Activation)
# ==============================================================================

def test_query_params_do_not_activate_stub_mode(monkeypatch: pytest.MonkeyPatch):
    """Query params ?stub=1 and ?mock=1 do not activate stub mode when STUB_LLM is unset."""
    monkeypatch.delenv("STUB_LLM", raising=False)
    monkeypatch.delenv("HOSTED_DEMO", raising=False)

    app_script = """
import streamlit as st
import os
from src.engine.stub_mode import is_stub_mode
from web_app import render_stub_banner_if_active

st.query_params["stub"] = "1"
st.query_params["mock"] = "1"

stub_active = is_stub_mode()
render_stub_banner_if_active()
st.write(f"STUB_ACTIVE={stub_active}")
"""
    at = AppTest.from_string(app_script).run()
    visible_texts = [m.value for m in at.markdown] + [e.value for e in at.error] + [t.value for t in at.text]
    combined = " ".join(visible_texts)

    assert "TEST MODE: synthetic data" not in combined
    assert "STUB_ACTIVE=False" in combined


# ==============================================================================
# 3. AppTest: Persistent Banner When STUB_LLM=1
# ==============================================================================

def test_persistent_red_banner_when_stub_llm_active(monkeypatch: pytest.MonkeyPatch):
    """Persistent red banner is present at top of page when STUB_LLM=1 and HOSTED_DEMO is unset."""
    monkeypatch.setenv("STUB_LLM", "1")
    monkeypatch.delenv("HOSTED_DEMO", raising=False)

    app_script = """
import streamlit as st
from web_app import render_stub_banner_if_active

render_stub_banner_if_active()
"""
    at = AppTest.from_string(app_script).run()
    visible_texts = [m.value for m in at.markdown] + [e.value for e in at.error]
    combined = " ".join(visible_texts)

    expected_banner = "TEST MODE: synthetic data. Results are not real and cannot be published."
    assert expected_banner in combined


# ==============================================================================
# 4. Run in Stub Mode Cannot Return Publishable Status
# ==============================================================================

def test_stub_mode_run_cannot_return_publishable_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A run executed while stub mode is active is marked unpublishable."""
    monkeypatch.setenv("STUB_LLM", "1")
    monkeypatch.delenv("HOSTED_DEMO", raising=False)

    approvals_dir = tmp_path / "approvals"
    q_text = "What empirical evidence exists regarding software testing?"
    q_id = resolve_question_id(q_text)

    save_gate1_approval(
        question_id=q_id,
        question_text=q_text,
        framing_id="empirical-effect",
        framing_title="Empirical effect",
        framing_question=q_text,
        approvals_dir=approvals_dir,
    )

    # Stub runner that tries to return PUBLISH_READY
    def stub_runner(**kwargs):
        return {
            "run_id": "run-stub-test",
            "status": "PUBLISH_READY",
            "can_publish": True,
            "quality_scorecard": {"total_score": 95, "band": "PUBLISH_READY"},
        }

    result = start_run(
        question_id=q_id,
        question_text=q_text,
        runner=stub_runner,
        approvals_dir=approvals_dir,
    )

    assert result["is_stub_mode"] is True
    assert result["can_publish"] is False
    assert result["status"] == "NOT_PUBLISHABLE"
    assert "TEST MODE: synthetic data. Results are not real and cannot be published." in result["stub_marker"]
    assert result["quality_scorecard"]["band"] == "NOT_PUBLISHABLE"


# ==============================================================================
# 5. Type Error on Non-Dict Runner Result in Stub Mode
# ==============================================================================

def test_stub_mode_raises_type_error_if_result_not_dict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """start_run raises TypeError if runner returns non-dict in stub mode."""
    monkeypatch.setenv("STUB_LLM", "1")
    monkeypatch.delenv("HOSTED_DEMO", raising=False)

    approvals_dir = tmp_path / "approvals"
    q_text = "What empirical evidence exists regarding software testing?"
    q_id = resolve_question_id(q_text)

    save_gate1_approval(
        question_id=q_id,
        question_text=q_text,
        framing_id="empirical-effect",
        framing_title="Empirical effect",
        framing_question=q_text,
        approvals_dir=approvals_dir,
    )

    def invalid_runner(**kwargs):
        return "not-a-dict"

    with pytest.raises(TypeError, match="Runner in stub mode must return a dict"):
        start_run(
            question_id=q_id,
            question_text=q_text,
            runner=invalid_runner,
            approvals_dir=approvals_dir,
        )


# ==============================================================================
# 6. Publisher Refuses at Point of Writing in Stub Mode
# ==============================================================================

def test_publisher_publish_output_refuses_when_stub_mode_active(monkeypatch: pytest.MonkeyPatch):
    """Publisher.publish_output immediately refuses with NOT_PUBLISHABLE in stub mode."""
    from src.publish.publisher import Publisher
    monkeypatch.setenv("STUB_LLM", "1")
    monkeypatch.delenv("HOSTED_DEMO", raising=False)

    pub = Publisher(db_path="ledger/ledger.db")
    success, res = pub.publish_output("any_output_id")
    assert success is False
    assert res["status"] == "NOT_PUBLISHABLE"
    assert "TEST MODE: synthetic data" in res["reason"]


# ==============================================================================
# 7. Production Ledger and outputs/ are Byte-Identical Before and After Stub Run
# ==============================================================================

def test_stub_run_leaves_production_ledger_and_outputs_byte_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Executing in stub mode leaves production ledger and outputs/ byte-identical to before."""
    monkeypatch.setenv("STUB_LLM", "1")
    monkeypatch.delenv("HOSTED_DEMO", raising=False)

    def file_bytes(p: Path) -> bytes:
        return p.read_bytes() if p.exists() else b""

    def dir_snapshot(d: Path) -> dict[str, bytes]:
        if not d.exists():
            return {}
        return {str(f.relative_to(d)): f.read_bytes() for f in d.rglob("*") if f.is_file()}

    prod_ledger = Path("ledger/ledger.db")
    prod_prac = Path("ledger/practitioner.db")
    outputs_dir = Path("outputs")

    before_ledger = file_bytes(prod_ledger)
    before_prac = file_bytes(prod_prac)
    before_outputs = dir_snapshot(outputs_dir)

    approvals_dir = tmp_path / "approvals"
    q_text = "What empirical evidence exists regarding software testing?"
    q_id = resolve_question_id(q_text)

    save_gate1_approval(
        question_id=q_id,
        question_text=q_text,
        framing_id="empirical-effect",
        framing_title="Empirical effect",
        framing_question=q_text,
        approvals_dir=approvals_dir,
    )

    # Call start_run without passing runner (using default MultiLaneResearchRunner)
    res = start_run(
        question_id=q_id,
        question_text=q_text,
        approvals_dir=approvals_dir,
        depth="Fast",
        tone="Executive",
        map_provider="stub",
        reduce_provider="stub",
        academic_papers_override=[{
            "id": "synthetic_p1",
            "title": "Mock Paper",
            "abstract": "Abstract",
            "year": 2024,
            "venue": "ICSE",
            "url": "https://example.com",
            "relevance_score": 0.9,
        }],
        enterprise_feed_override={},
        allow_remote_practitioner_synthesis=False,
        practitioner_abstraction_confirmed=True,
    )

    assert res["is_stub_mode"] is True
    assert res["status"] == "NOT_PUBLISHABLE"

    after_ledger = file_bytes(prod_ledger)
    after_prac = file_bytes(prod_prac)
    after_outputs = dir_snapshot(outputs_dir)

    assert after_ledger == before_ledger, "Production ledger/ledger.db was modified during stub run!"
    assert after_prac == before_prac, "Production ledger/practitioner.db was modified during stub run!"
    assert after_outputs == before_outputs, "outputs/ directory was modified during stub run!"

