"""Tests for the PR #6 review findings on Slice S8 (step rail and status banner).

Requirements (one per review finding):
1. A run stopped by Check A or B shows every reason recorded for it, including an unconfirmed
   practitioner abstraction (G6), not only the check's own reason.
2. The banner never says to publish when the Publish step cannot: stub mode, hosted demo, or no draft.
3. A Check A stop points to the Evidence tab, where the per-source verdicts are.
4. The page derives a run's status once (status_code), for the banner, the rail and the exports.
5. Tab variables and section comments use the step names, not the old phase numbers.
"""

from __future__ import annotations

from pathlib import Path

from src.ui.run_status import run_status, status_code, step_rail

G6 = "Gate 6: Practitioner abstraction not confirmed by operator."


def _res(**kw):
    out = {"papers": [], "claims": [], "enterprise_sources": [], "doc_id": "out_1"}
    out.update(kw)
    return out


# ------------------------------------------------------------------------------
# Test 1: Stopped runs keep every reason
# ------------------------------------------------------------------------------
def test_stopped_run_shows_practitioner_reason():
    stop = "0 of 3 sources are on-topic."
    s = run_status(_res(status="BLOCKED", stopped_at="check_a", stop_reason=stop,
                        publish_res={"status": "BLOCKED", "reasons": [G6, stop]}))
    assert s["why"] == [G6, stop]
    s = run_status(_res(status="NOT_PUBLISHABLE", stopped_at="check_b", stop_reason=stop))
    assert s["why"] == [stop]


# ------------------------------------------------------------------------------
# Test 2: Banner agrees with the Publish step
# ------------------------------------------------------------------------------
def test_banner_does_not_offer_publish_when_it_cannot(monkeypatch):
    ready = run_status(_res(status="PUBLISH_READY"))
    assert ready["level"] == "ok" and "publish" in ready["next_step"].lower()

    stub = run_status(_res(status="PUBLISH_READY", is_stub_mode=True))
    assert stub["level"] == "warn" and "test mode" in stub["next_step"].lower()

    no_doc = run_status(_res(status="REVISE", doc_id=None))
    assert no_doc["level"] == "warn" and "nothing was drafted" in no_doc["next_step"].lower()

    monkeypatch.setenv("HOSTED_DEMO", "1")
    demo = run_status(_res(status="PUBLISH_READY"))
    assert demo["level"] == "warn" and "hosted demo" in demo["next_step"].lower()


# ------------------------------------------------------------------------------
# Test 3: Check A stop points to the Evidence tab
# ------------------------------------------------------------------------------
def test_check_a_stop_points_to_evidence_tab():
    s = run_status(_res(status="NOT_PUBLISHABLE", stopped_at="check_a", stop_reason="x"))
    assert "Evidence tab" in s["next_step"]


# ------------------------------------------------------------------------------
# Test 4: One status derivation
# ------------------------------------------------------------------------------
def test_status_derived_once():
    assert status_code(_res(status="published")) == "PUBLISHED"
    assert status_code(_res(publish_res={"status": "REVISE"})) == "REVISE"
    assert status_code(_res(quality_scorecard={"band": "REVISE"})) == "REVISE"
    assert status_code(_res()) == "NOT_PUBLISHABLE"
    assert step_rail(_res(status="PUBLISHED"))[-1]["state"] == "done"
    src = Path("web_app.py").read_text(encoding="utf-8")
    assert "    status = status_code(results)\n" in src
    assert 'status = (results.get("publish_res", {}).get("status")' not in src


# ------------------------------------------------------------------------------
# Test 5: Step names in code too
# ------------------------------------------------------------------------------
def test_no_old_phase_names_in_tab_code():
    src = Path("web_app.py").read_text(encoding="utf-8")
    for old in ("phase_tab4", "phase_tab2", "phase_tab3", "phase_tab_gov", "TAB 1 (PHASE 4)", "(PHASE 4B)",
                "# 3. SYSTEM STATUS POD", "Phase-organized Tabs"):
        assert old not in src, old
