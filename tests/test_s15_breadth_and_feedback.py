"""Tests for Slice S15: check more candidates, keep the best on-topic ones; feedback that you can see applied.

Requirements:
1. Depth sizes are configured (research.depth): Deep checks 30 candidates and keeps 15; Fast checks
   12 and keeps 5. The unused research.max_papers key is gone.
2. Check A judges every candidate; the papers carried into extraction are the best on-topic ones by
   relevance x venue-tier weight, at most `keep`. Off-topic papers are never used; custom URLs the
   operator added are always kept. The run records how many were checked, on topic and used.
3. The depth labels and the Evidence tab say how many papers were checked and used.
4. Quick adjustments and the free text become numbered feedback points sent to the model.
5. After re-reasoning, each point is reviewed by rule against the before/after proposal: Applied,
   Not applied (nothing that matches it changed) or Blocked by a rule (re-reasoning was refused).
   A dropped term must be gone; an added sub-question must be new and about the asked topic.
6. The before/after shows the question and the sub-questions added and removed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.ui.feedback_review import (
    QUICK_ADJUSTMENTS,
    compose_feedback,
    proposal_diff,
    review_feedback,
)

BEFORE = {
    "refined_question": "How do AI coding assistants affect cycle time in enterprise engineering teams?",
    "sub_questions": ["What cycle-time changes are measured?", "Which teams adopt assistants?", "What risks appear?"],
    "in_scope": ["enterprise engineering teams"],
    "out_of_scope": [],
}


# ------------------------------------------------------------------------------
# Tests 1-3: Breadth
# ------------------------------------------------------------------------------
def test_depth_sizes_configured():
    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    depth = cfg["research"]["depth"]
    assert depth["deep"]["candidates"] == 30 and depth["deep"]["keep"] == 15
    assert depth["fast"]["candidates"] == 12 and depth["fast"]["keep"] == 5
    assert "max_papers" not in cfg["research"]


def _runner(tmp_path):
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.ledger.migrations import apply_migrations

    db, prac = str(tmp_path / "l.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    r = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    r._harvest_enterprise_lane = lambda **kwargs: []
    r.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1}
    return r


ABSTRACT = "AI coding assistants shortened cycle time in enterprise engineering teams across forty repositories."


def _paper(i, score, weight, custom=False):
    return {"id": f"p{i}", "title": f"AI coding assistants and cycle time in engineering teams, study {i}",
            "abstract": ABSTRACT, "year": 2024, "venue": "Empirical Software Engineering",
            "url": f"https://doi.org/10.1/{i}", "relevance_score": score, "tier_weight": weight, "is_custom": custom}


def test_keeps_best_on_topic_papers(tmp_path):
    r = _runner(tmp_path)
    seen = {}

    def harvest(**kw):
        seen["max_papers"] = kw["max_papers"]
        papers = [_paper(i, score=float(i), weight=1.0) for i in range(30)]
        papers[0]["is_custom"] = True  # lowest score, but the operator added it
        papers[1]["title"] = "Sourdough starters at home"  # off topic by the key-term floor
        papers[1]["abstract"] = "Sourdough starters ferment flour and water over several days in home kitchens."
        return papers

    used = {}
    real_extract = r._extract_academic_claims

    def extract(papers, qid):
        used["ids"] = [p["id"] for p in papers]
        return real_extract(papers, qid)

    r._harvest_academic_lane = harvest
    r._extract_academic_claims = extract
    res = r.run_workflow(topic="How do AI coding assistants affect cycle time in engineering teams?", depth="Deep",
                         map_provider="stub", reduce_provider="stub")
    assert seen["max_papers"] == 30
    assert len(used["ids"]) == 15 and "p0" in used["ids"] and "p1" not in used["ids"]
    # The best 14 non-custom papers (scores 16-29), kept in harvest order so [P#] numbering is stable.
    assert used["ids"] == ["p0"] + [f"p{i}" for i in range(16, 30)]
    assert res["breadth"] == {"checked": 30, "on_topic": 29, "used": 15}


def test_labels_and_evidence_tab_report_breadth():
    intake = Path("src/ui/intake_view.py").read_text(encoding="utf-8")
    block = intake[intake.index('"Research Depth"'):intake.index('key="select_research_depth"')]
    assert "15 papers" in block and "30 checked" in block and "5 papers" in block and "12 checked" in block
    web = Path("web_app.py").read_text(encoding="utf-8")
    assert 'results.get("breadth")' in web


# ------------------------------------------------------------------------------
# Test 4: Quick adjustments become feedback points
# ------------------------------------------------------------------------------
def test_compose_feedback_points():
    assert "Narrow the scope" in QUICK_ADJUSTMENTS and "Broaden the scope" in QUICK_ADJUSTMENTS
    points = compose_feedback(["Narrow the scope", "Focus on measured outcomes"], add_sub_question="code review delays",
                              drop_terms="throughput, velocity", free_text="Mention regulated industries.\nKeep it neutral.")
    kinds = [p["kind"] for p in points]
    assert kinds == ["narrow", "measured", "add_sub_question", "drop_term", "drop_term", "free", "free"]
    assert points[2]["detail"] == "code review delays" and points[3]["detail"] == "throughput"
    assert all(p["text"] for p in points)
    assert compose_feedback([], "", "", "  ") == []


# ------------------------------------------------------------------------------
# Tests 5-6: Review and diff
# ------------------------------------------------------------------------------
def test_review_marks_applied_not_applied_and_blocked():
    after = {
        **BEFORE,
        "refined_question": "How do AI coding assistants affect cycle time in regulated enterprise engineering teams?",
        "sub_questions": BEFORE["sub_questions"] + ["How do code review delays change with assistants?"],
        "out_of_scope": ["consumer apps"],
    }
    points = compose_feedback(["Narrow the scope", "Fewer sub-questions"], add_sub_question="code review delays",
                              drop_terms="cycle time", free_text="Mention regulated industries.")
    rows = {p["text"]: r for p, r in zip(points, review_feedback(points, BEFORE, after))}
    by_kind = {p["kind"]: rows[p["text"]] for p in points}
    assert by_kind["narrow"]["result"] == "Applied" and "out of scope" in by_kind["narrow"]["what_changed"]
    assert by_kind["fewer_sub_questions"]["result"] == "Not applied"
    assert by_kind["add_sub_question"]["result"] == "Applied"
    assert by_kind["drop_term"]["result"] == "Not applied" and "still" in by_kind["drop_term"]["what_changed"]
    assert by_kind["free"]["result"] == "Applied"

    unchanged = review_feedback(compose_feedback([], "", "", "Mention regulated industries."), BEFORE, dict(BEFORE))
    assert unchanged[0]["result"] == "Not applied" and "nothing" in unchanged[0]["what_changed"].lower()

    blocked = review_feedback(points, BEFORE, None, blocked_reason="Proposal tried to answer the question.")
    assert {r["result"] for r in blocked} == {"Blocked by a rule"}
    assert all("answer the question" in r["what_changed"] for r in blocked)


def test_drop_term_applied_when_gone():
    after = {**BEFORE, "refined_question": "How do AI coding assistants affect delivery speed in enterprise engineering teams?",
             "sub_questions": ["What delivery-speed changes are measured?", "Which teams adopt assistants?", "What risks appear?"]}
    pts = compose_feedback([], "", "cycle time", "")
    assert review_feedback(pts, BEFORE, after)[0]["result"] == "Applied"


def test_proposal_diff():
    after = {**BEFORE, "sub_questions": BEFORE["sub_questions"][1:] + ["How do code review delays change?"]}
    d = proposal_diff(BEFORE, after)
    assert d["question_changed"] is False
    assert d["sub_questions_added"] == ["How do code review delays change?"]
    assert d["sub_questions_removed"] == ["What cycle-time changes are measured?"]


def test_intake_wires_adjustments_and_review():
    src = Path("src/ui/intake_view.py").read_text(encoding="utf-8")
    for needed in ("compose_feedback(", "review_feedback(", "proposal_diff(", "s2_feedback_review", "QUICK_ADJUSTMENTS"):
        assert needed in src, needed
