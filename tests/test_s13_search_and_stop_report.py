"""Tests for Slice S13: search queries stay on the question's subject; a stopped run exports a stop report.

A Cloud Run run of the platform-teams question stopped at Check A with 0 of 26 sources on topic (the
same question kept 3 of 10 before S11). S11's condensed query kept only the first 8 key terms
("architectural frameworks workflow transformations adoption practices required platform"), dropping
"code generation" and "AI", so the searches returned building-design and workflow-management papers.
The draft download for that stopped run was 14 empty section headings.

Requirements:
1. condense() drops generic wording (required, progress, strategically, differentiated, standalone,
   specialized, ...), writes common phrases short ("artificial intelligence" -> AI, "large language
   models" -> LLM), and keeps up to 10 terms, so the subject words survive.
2. Each sub-question query carries the main question's anchor terms (configured technology terms it
   mentions) when the sub-question lacks them, so it searches the same subject.
3. The search query that worked before S11 (the cleaned full question) stays within the first queries
   Deep runs (query_limit 4).
4. The anchor terms are configured (research.query_anchor_terms).
5. A run stopped by Check A or B downloads a stop report: status, why, every source judged with its
   verdict and reason, and what to do next; never empty section headings.
"""

from __future__ import annotations

from pathlib import Path

from src.analysis.queries import condense, research_queries
from src.app import build_topic_queries
from src.ui.brief_view import stopped_run_markdown

Q = ("What architectural frameworks, workflow transformations, and adoption practices are required for platform "
     "development teams to progress from standalone code generation tools to specialized, strategically "
     "differentiated artificial intelligence systems?")


# ------------------------------------------------------------------------------
# Test 1: The subject survives condensing
# ------------------------------------------------------------------------------
def test_condense_keeps_the_subject():
    words = condense(Q).split()
    assert len(words) <= 10
    for keep in ("code", "generation", "AI", "platform"):
        assert keep in words, keep
    for drop in ("required", "progress", "strategically", "differentiated", "standalone", "specialized", "artificial"):
        assert drop not in words, drop
    assert condense("How do large language models change code review?") == "LLM change code review"


# ------------------------------------------------------------------------------
# Tests 2-4: Sub-questions search the same subject; the proven query stays early
# ------------------------------------------------------------------------------
def test_sub_question_queries_carry_anchor_terms():
    pkg = {"refined_question": Q, "sub_questions": [
        "Which orchestration architectures do enterprises use for multi-agent delivery?",
        "How do teams measure business outcomes of AI coding tools?",
    ]}
    qs = research_queries(Q, pkg)
    orch = next(q for q in qs if "orchestration" in q)
    assert "AI" in orch.split() and "code" in orch.split()
    measure = next(q for q in qs if "measure" in q)
    assert measure.split().count("AI") == 1, "anchors are added only when missing"


def test_proven_query_stays_within_deep_limit():
    pkg = {"refined_question": Q, "sub_questions": ["Which orchestration architectures do enterprises use?",
                                                    "How do teams measure outcomes?", "What adoption barriers exist?"]}
    assert build_topic_queries(Q)[0] in research_queries(Q, pkg)[:4]


def test_anchor_terms_configured():
    import yaml

    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    anchors = cfg["research"]["query_anchor_terms"]
    for t in ("ai", "llm", "code", "software", "agent"):
        assert t in anchors


# ------------------------------------------------------------------------------
# Test 5: A stopped run exports a stop report
# ------------------------------------------------------------------------------
STOPPED = {
    "status": "NOT_PUBLISHABLE",
    "stopped_at": "check_a",
    "stop_reason": "Only 0 of 26 sources are on-topic for the approved question; at least 1 on-topic source is needed.",
    "strategic_question": Q,
    "check_a": {"sources": [
        {"title": "Synergizing BIM and RIBA in architectural practice", "lane": "academic", "verdict": "off_topic",
         "reason": "About building design | not software."},
        {"title": "Agile Adoption Process Framework", "lane": "academic", "verdict": "off_topic", "reason": "No AI systems."},
    ]},
    "publish_res": {"reasons": ["Stopped at Check A: Only 0 of 26 sources are on-topic."]},
}


def test_stopped_run_downloads_a_stop_report():
    md = stopped_run_markdown(STOPPED)
    assert md.startswith("# Run stopped: not enough on-topic evidence")
    assert Q in md and "NOT_PUBLISHABLE" in md and "0 of 26" in md
    assert "| Synergizing BIM and RIBA in architectural practice | Academic | Off-topic | About building design \\| not software. |" in md
    assert "## What to do next" in md
    assert "Not specified" not in md and "## 5. Papers Reviewed" not in md
    b = stopped_run_markdown({**STOPPED, "stopped_at": "check_b", "stop_reason": "Only 2 usable claims from 1 source."})
    assert b.startswith("# Run stopped: too few usable claims") and "Only 2 usable claims" in b


def test_web_app_uses_stop_report_for_stopped_runs():
    src = Path("web_app.py").read_text(encoding="utf-8")
    assert "stopped_run_markdown(results)" in src
    block = src[src.index("stopped_run_markdown(results)") - 400:src.index("stopped_run_markdown(results)")]
    assert 'results.get("stopped_at")' in block


# ------------------------------------------------------------------------------
# Tests 6-8: Check A judges relevance to the subject, not a full answer
# ------------------------------------------------------------------------------
# Requirements (added after reading run job_3cd226217fd8's Check A table):
# 6. Check A's live prompt (v3) asks whether a source is about the question's subject and could inform
#    at least one part or sub-question; it does not have to answer the whole question. It keeps the
#    compound-subject rule (the sourdough canary) and the out-of-scope rule.
# 7. The labelled bake-off set (v2) includes that run's 26 sources, and the bake-off expects the
#    platform-teams question to pass and the sourdough canary to stop.
# 8. The run's own reasons read "not the transition to specialized ... systems": a source that covers one
#    part of a compound question is the case the prompt names as on_topic.
def test_check_a_live_prompt_is_v3():
    import src.engine.check_a_on_topic as check_a

    assert check_a.PROMPT_FILE_PATH == "prompts/check_a_on_topic_v3.md"
    text = Path(check_a.PROMPT_FILE_PATH).read_text(encoding="utf-8")
    for needed in ("{context}", "{items}", "at least one part", "does not need to answer the whole question",
                   "solar-powered irrigation pumps", "out of scope"):
        assert needed in text, needed


def test_bakeoff_set_v2_has_the_failing_run():
    import json
    import sys

    data = json.loads(Path("evals/data/check_a_labelled_v2.json").read_text(encoding="utf-8"))
    platform = [i for i in data["items"] if i["question_key"] == "platform"]
    assert len(platform) == 26 and sum(i["label"] == "on_topic" for i in platform) >= 5
    assert {i["question_key"] for i in data["items"]} >= {"kiro", "hospital", "assistants", "sourdough", "platform"}
    sys.path.insert(0, "evals")
    import bakeoff_check_a

    assert bakeoff_check_a.DATA.name == "check_a_labelled_v2.json"
    assert bakeoff_check_a.EXPECTED_RUN_PASS["platform"] is True and bakeoff_check_a.EXPECTED_RUN_PASS["sourdough"] is False
