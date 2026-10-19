"""Tests for Slice S8: a simpler step flow, one status banner, a readable brief, phone-friendly layout.

Requirements:
1. One helper turns a run's results into a single status: headline, why (plain words) and next step.
2. Each stop and status has its own headline and next step (Check A, Check B, fallback, BLOCKED,
   NOT_PUBLISHABLE, REVISE, PUBLISH_READY, PUBLISHED).
3. The step rail shows Question -> Evidence -> Claims -> Brief -> Checks & publish, each done,
   stopped, waiting on you, or not reached, matching where the run stopped.
4. The status banner and step rail escape model and source text.
5. The brief's summary line replaces the four metric tiles; signals that repeat a finding are dropped.
6. Recommendations, evidence boundaries and the gap rationale are escaped.
7. web_app.py shows one status banner, tabs named after the steps in pipeline order, no feedback-loop
   pod or phase radio, and a phone-width layout rule.
"""

from __future__ import annotations

from pathlib import Path

from src.ui.brief_view import brief_meta_line, distinct_signals, plain_html, roadmap_html
from src.ui.run_status import STEPS, run_status, status_banner_html, step_rail, step_rail_html

BASE = {"papers": [{"key": "P1"}, {"key": "P2"}], "claims": [{"id": "c1"}] * 4, "enterprise_sources": [],
        "duration": "42s", "doc_id": "out_1"}


def _res(**kw):
    out = dict(BASE)
    out.update(kw)
    return out


# ------------------------------------------------------------------------------
# Tests 1-2: One status per run, with a next step
# ------------------------------------------------------------------------------
def test_no_results_has_no_status():
    assert run_status(None) is None


def test_each_stop_has_headline_and_next_step():
    cases = {
        "check_a": _res(status="NOT_PUBLISHABLE", stopped_at="check_a", stop_reason="0 of 3 sources are on-topic."),
        "check_b": _res(status="BLOCKED", stopped_at="check_b", stop_reason="Only 2 usable claims from 1 source."),
        "fallback": _res(status="NOT_PUBLISHABLE", is_fallback=True, blocking_banner="Primary model unavailable."),
        "blocked": _res(status="BLOCKED", publish_res={"status": "BLOCKED", "reasons": ["G5: Add denylist.txt."]}),
        "low": _res(status="NOT_PUBLISHABLE", publish_res={"reasons": ["All gates passed but the score is too low to publish."]}),
        "revise": _res(status="REVISE"),
        "ready": _res(status="PUBLISH_READY"),
        "published": _res(status="PUBLISHED"),
    }
    seen = set()
    for name, results in cases.items():
        s = run_status(results)
        assert s["headline"] and s["next_step"] and s["level"] in ("error", "warn", "ok"), name
        seen.add(s["headline"])
    assert len(seen) == len(cases), "every case reads differently"
    assert "on-topic" in run_status(cases["check_a"])["why"][0]
    assert run_status(cases["blocked"])["why"] == ["G5: Add denylist.txt."]
    assert run_status(cases["check_a"])["level"] == "error"
    assert run_status(cases["ready"])["level"] == "ok"
    assert "reason" in run_status(cases["revise"])["next_step"].lower()


def test_fallback_wins_over_its_status():
    s = run_status(_res(status="BLOCKED", is_fallback=True, blocking_banner="Model offline."))
    assert "model" in s["headline"].lower() and "Model offline." in s["why"]


# ------------------------------------------------------------------------------
# Test 3: Step rail
# ------------------------------------------------------------------------------
def test_step_rail_labels_and_states():
    assert [s for s in STEPS] == ["Question", "Evidence", "Claims", "Brief", "Checks & publish"]
    states = lambda r: [s["state"] for s in step_rail(r)]
    assert states(None) == ["current", "pending", "pending", "pending", "pending"]
    assert states(_res(status="NOT_PUBLISHABLE", stopped_at="check_a")) == ["done", "stopped", "pending", "pending", "pending"]
    assert states(_res(status="BLOCKED", stopped_at="check_b")) == ["done", "done", "stopped", "pending", "pending"]
    assert states(_res(status="BLOCKED")) == ["done", "done", "done", "done", "stopped"]
    assert states(_res(status="PUBLISH_READY")) == ["done", "done", "done", "done", "current"]
    assert states(_res(status="REVISE")) == ["done", "done", "done", "done", "current"]
    assert states(_res(status="PUBLISHED")) == ["done", "done", "done", "done", "done"]
    assert step_rail(_res(status="BLOCKED"))[1]["detail"] == "2 papers · 0 enterprise"
    assert step_rail(_res(status="BLOCKED"))[2]["detail"] == "4 claims"


# ------------------------------------------------------------------------------
# Test 4: Banner and rail escape text
# ------------------------------------------------------------------------------
def test_banner_and_rail_escape():
    s = run_status(_res(status="BLOCKED", publish_res={"reasons": ["G1: <img src=x onerror=alert(1)>"]}))
    out = status_banner_html(s)
    assert "<img" not in out and "&lt;img" in out and s["next_step"].split()[0] in out
    rail = step_rail_html(step_rail(_res(status="BLOCKED")))
    assert all(label.replace("&", "&amp;") in rail for label in STEPS)


# ------------------------------------------------------------------------------
# Tests 5-6: Readable brief
# ------------------------------------------------------------------------------
def test_brief_meta_line():
    line = brief_meta_line(_res(metrics={"horizon": "2022–2024", "quality": "65.0/100 (BLOCKED)"},
                                practitioner_observations=[]))
    assert line == "2 papers · 0 enterprise sources · 0 field notes · 4 claims · 2022–2024 · Score 65.0/100"


def test_signals_that_repeat_findings_are_dropped():
    findings = [{"text": "Assistants cut cycle time 14% [P1]."}]
    signals = [{"text": "Assistants cut cycle time 14% [P1].", "tag": "S1"}, {"text": "Adoption is uneven [P2].", "tag": "S2"}]
    assert [s["tag"] for s in distinct_signals(signals, findings)] == ["S2"]


def test_brief_text_is_escaped():
    assert plain_html("<b>x</b> & y") == "&lt;b&gt;x&lt;/b&gt; &amp; y"
    out = roadmap_html([{"phase": "<i>Now</i>", "action": "Pilot <script>", "impact": "Faster"}])
    assert "<script>" not in out and "<i>" not in out and "Recommendation" in out


# ------------------------------------------------------------------------------
# Test 7: web_app.py layout
# ------------------------------------------------------------------------------
def test_web_app_uses_one_banner_and_step_tabs():
    src = Path("web_app.py").read_text(encoding="utf-8")
    assert src.count("status_banner_html(") == 1
    assert "step_rail_html(" in src
    for gone in ("Active Feedback Loops", "sidebar_phase_selector", "PUBLICATION BLOCKED (G1–G6", "Phase 4B:",
                 "Phase 4 • Active Output", "Draft Mode — Below Publication Threshold"):
        assert gone not in src, gone
    tabs = src[src.index("st.tabs(["):src.index("])", src.index("st.tabs(["))]
    order = [tabs.index(t) for t in ('"Brief"', '"Evidence"', '"Claims & gaps"', '"Checks & publish"')]
    assert order == sorted(order)
    assert "@media (max-width: 640px)" in src
    assert "brief_meta_line(results)" in src and "stat_cols = st.columns(4)" not in src
