"""Tests for Slice S19: a question-shaped report, with synthesis sentences that may reason across papers.

Requirements:
1. Generality: search anchors are derived from each approved question and its package (terms the question
   shares with its sub-questions or scope), not only from a configured word list; topic-specific query
   expansions (Kiro, Cursor) and software-only suffixes are gone.
2. The approved package reaches the writer: the report prompt lists every sub-question as a section, asks for
   an answer, synthesis and evidence sentences, tensions, gaps and implications, and carries no topic example.
3. Synthesis-like sentences (summary, synthesis, tension, gap, implication) must cite; must cite claims from
   two or more sources or say they rest on one study; may not add a figure absent from the cited claims; are
   not failed for low word overlap; and keep the verb cap and intensifier rule. An implication must name its
   section.
4. The generator turns sections into a heading, synthesis sentences and evidence sentences, all tagged with
   their section; tensions, gaps and implications get their own types.
5. The report model (rule-built) gives each section its sentences, an evidence table (paper, method, finding,
   grade) and a confidence badge; it adds a gap line for a section resting on one paper.
6. The Brief tab renders the report when present (saved runs without one keep the old layout), and the brief
   download follows the same structure.
7. Without a model, the extractive fallback still produces one section per sub-question, evidence only.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.ledger.models import Claim, OutputSentence

PLATFORM_Q = ("What architectural frameworks, workflow transformations, and adoption practices help platform teams move "
              "from code generation tools to specialised AI systems?")
PLATFORM_PKG = {"refined_question": PLATFORM_Q, "sub_questions": [
    "Which architectural frameworks support specialised AI systems for platform teams?",
    "How do platform teams change workflows when code generation tools arrive?",
    "Which adoption practices help platform teams scale AI systems?",
]}
WEEK_Q = "What evidence exists on four-day work weeks and employee productivity?"
WEEK_PKG = {"refined_question": WEEK_Q, "sub_questions": [
    "How does a four-day work week change measured employee productivity?",
    "What happens to employee wellbeing under four-day work weeks?",
], "in_scope": ["four-day work week trials in companies"]}


# ------------------------------------------------------------------------------
# Test 1: Generality of search anchors
# ------------------------------------------------------------------------------
def test_anchors_derived_from_the_question():
    from src.analysis.queries import research_queries, subject_terms

    week = [t.lower() for t in subject_terms(WEEK_Q, WEEK_PKG)]
    assert any(t.startswith("week") for t in week) and "employee" in week
    assert not {"ai", "code", "software", "llm"} & set(week)
    plat = [t.lower() for t in subject_terms(PLATFORM_Q, PLATFORM_PKG)]
    assert {"platform", "ai"} <= set(plat)
    qs = research_queries(WEEK_Q, WEEK_PKG)
    wellbeing = next(q for q in qs if "wellbeing" in q)
    assert any(w.startswith("week") for w in wellbeing.lower().split())


def test_no_topic_specific_query_expansions():
    from src.app import build_topic_queries

    src = Path("src/app.py").read_text(encoding="utf-8")
    assert '"kiro" in lower' not in src and '"cursor"' not in src
    qs = build_topic_queries(WEEK_Q)
    assert not any("software engineering" in q or "developer productivity" in q for q in qs)


# ------------------------------------------------------------------------------
# Test 2: The report prompt
# ------------------------------------------------------------------------------
def test_report_prompt_uses_sub_questions():
    from src.prompts.research_prompts import ResearchPromptLibrary as L

    p = L.report("t", [{"paper_id": "P1"}], WEEK_PKG["sub_questions"], question=WEEK_Q)
    for sq in WEEK_PKG["sub_questions"]:
        assert sq in p
    for key in ('"answer"', '"sections"', '"synthesis"', '"evidence"', '"tensions"', '"gaps"', '"implications"'):
        assert key in p, key
    assert "taken together" in p.lower() and "deployment frequency" not in p.lower()


def test_synthesizer_passes_the_package():
    from src.analysis.synthesizer import SynthesisEngine

    class Fake:
        model = "fake"

        def __init__(self):
            self.prompts = []

        def generate(self, prompt, system_prompt=None, temperature=0.3, json_mode=False):
            self.prompts.append(prompt)
            if "Evaluate the following paper" in prompt:
                return json.dumps({"title": "T", "key_findings": "Teams worked fewer days.", "research_method": "survey"})
            if '"sections"' in prompt:
                return json.dumps({"answer": ["A [P1]."], "sections": [{"sub_question": WEEK_PKG["sub_questions"][0],
                                   "synthesis": [], "evidence": ["One study reports X [P1]."]}],
                                   "tensions": [], "gaps": [], "implications": []})
            return json.dumps({})

    llm = Fake()
    out = SynthesisEngine(llm, llm).analyze(WEEK_Q, [{"title": "T", "abstract": "x" * 80}], package=WEEK_PKG)
    assert any(WEEK_PKG["sub_questions"][1] in p for p in llm.prompts)
    assert out["sections"][0]["evidence"] == ["One study reports X [P1]."]
    assert out["executive_summary"] == "A [P1]."


# ------------------------------------------------------------------------------
# Test 3: Gate rules for synthesis sentences
# ------------------------------------------------------------------------------
CA = Claim(id="c_a", source_id="sa", text="The study reports that trial firms kept output stable with a four-day week.",
           source_excerpt="trial firms kept output stable with a four-day week", grade="moderate")
CB = Claim(id="c_b", source_id="sb", text="The study reports that employees reported less burnout after the trial.",
           source_excerpt="employees reported less burnout after the trial", grade="moderate")


def _gate(text, type_, cids, checks=None):
    from src.score.checker import GateChecker

    s = OutputSentence(id="s1", output_id="o", ordinal=1, text=text, type=type_, claim_ids_json=cids, checks_json=checks)
    return GateChecker().check_output(sentences=[s], ledger_claims={"c_a": CA, "c_b": CB})


def test_synthesis_rules():
    from src.score.checker import SYNTHESIS_TYPES

    assert {"summary", "synthesis", "tension", "gap", "implication"} <= set(SYNTHESIS_TYPES)
    two = _gate("Taken together, the trials suggest shorter weeks need not cost output or wellbeing [P1][P2].",
                "synthesis", ["c_a", "c_b"])
    assert two.state("G2") == "PASS" and not two.violations["G4"]
    one = _gate("Taken together, shorter weeks need not cost output [P1].", "synthesis", ["c_a"])
    assert any("two or more sources" in v for v in one.violations["G4"])
    one_ok = _gate("One study suggests shorter weeks need not cost output [P1].", "synthesis", ["c_a"])
    assert not any("two or more sources" in v for v in one_ok.violations["G4"])
    fig = _gate("Taken together, output rose 12% under shorter weeks [P1][P2].", "synthesis", ["c_a", "c_b"])
    assert any("ungrounded numeral" in v for v in fig.violations["G2"])
    uncited = _gate("Shorter weeks seem to work.", "synthesis", [])
    assert uncited.state("G1") == "FAIL"
    imp = _gate("Leaders could pilot a four-day week with measurement [P1][P2].", "implication", ["c_a", "c_b"])
    assert any("names no section" in v for v in imp.violations["G1"])
    imp_ok = _gate("Leaders could pilot a four-day week with measurement [P1][P2].", "implication", ["c_a", "c_b"],
                   checks={"section": 1})
    assert not any("names no section" in v for v in imp_ok.violations["G1"])


# ------------------------------------------------------------------------------
# Test 4: Generator sections
# ------------------------------------------------------------------------------
def test_generator_emits_sections(tmp_path):
    from src.ledger.migrations import apply_migrations
    from src.ledger.models import Question, Run, Source
    from src.ledger.repository import LedgerRepository
    from src.synth.generator import SynthesisEngine

    db = str(tmp_path / "l.db")
    apply_migrations(db_path=db)
    repo = LedgerRepository(db_path=db)
    repo.insert_question(Question(id="q", text=WEEK_Q))
    repo.insert_run(Run(id="r", question_ids=["q"]))
    for sid in ("sa", "sb"):
        repo.insert_source(Source(id=sid, lane="academic", source_type="preprint", title=f"Four-day week trial {sid}"))
    for c in (CA, CB):
        repo.insert_claim(c.model_copy(update={"question_id": "q"}))
    synth = {
        "executive_summary": "Taken together, the trials suggest output held [P1][P2].",
        "sections": [
            {"sub_question": WEEK_PKG["sub_questions"][0],
             "synthesis": ["Taken together, the trials suggest output held with a four-day week [P1][P2]."],
             "evidence": ["One study reports trial firms kept output stable [P1]."]},
            {"sub_question": WEEK_PKG["sub_questions"][1], "synthesis": [],
             "evidence": ["One study reports employees reported less burnout [P2]."]},
        ],
        "tensions": ["The trials differ on whether output held in every firm [P1][P2]."],
        "gaps": ["Neither study follows firms beyond one year [P1][P2]."],
        "implications": [{"text": "Leaders could pilot with measurement [P1][P2].", "section": 1}],
    }
    claims = [repo.get_claim("c_a"), repo.get_claim("c_b")]
    _, sentences, _ = SynthesisEngine(db_path=db).build_field_note(
        question_id="q", run_id="r", executive_synthesis=synth, papers=[{"id": "sa"}, {"id": "sb"}], claims_override=claims)
    by_type = {}
    for s in sentences:
        by_type.setdefault(s.type, []).append(s)
    sec_heads = [s for s in by_type["heading"] if (s.checks_json or {}).get("section")]
    assert [h.checks_json["section"] for h in sec_heads] == [1, 2]
    assert by_type["synthesis"][0].checks_json["section"] == 1
    assert {s.checks_json["section"] for s in by_type["assertive"]} == {1, 2}
    assert by_type["tension"] and by_type["gap"] and by_type["implication"][0].checks_json["section"] == 1
    assert not by_type.get("signal"), "signals would repeat the evidence"


# ------------------------------------------------------------------------------
# Test 5: Report model
# ------------------------------------------------------------------------------
def test_report_model_tables_and_confidence():
    from src.synth.report import build_report, classify_method

    assert classify_method("A controlled experiment with 40 teams") == "empirical"
    assert classify_method("We propose a conceptual framework") == "conceptual"
    assert classify_method("not stated") == "not stated"
    S = lambda i, t, typ, cids, sec: OutputSentence(id=f"s{i}", output_id="o", ordinal=i, text=t, type=typ,
                                                    claim_ids_json=cids, checks_json={"section": sec} if sec else None)
    sentences = [
        S(1, "Taken together, output held [P1][P2].", "summary", ["c_a", "c_b"], None),
        OutputSentence(id="h1", output_id="o", ordinal=2, text=WEEK_PKG["sub_questions"][0], type="heading", checks_json={"section": 1}),
        S(3, "Taken together, output held [P1][P2].", "synthesis", ["c_a", "c_b"], 1),
        S(4, "One study reports output stable [P1].", "assertive", ["c_a"], 1),
        OutputSentence(id="h2", output_id="o", ordinal=5, text=WEEK_PKG["sub_questions"][1], type="heading", checks_json={"section": 2}),
        S(6, "One study reports less burnout [P2].", "assertive", ["c_b"], 2),
        S(7, "Leaders could pilot [P1][P2].", "implication", ["c_a", "c_b"], 1),
    ]
    papers = [{"id": "sa", "key": "P1", "title": "Trial A", "type": "Preprint", "venue": "SSRN"},
              {"id": "sb", "key": "P2", "title": "Trial B", "type": "Peer-Reviewed Journal", "venue": "Nature Human Behaviour"}]
    summaries = [{"paper_id": "P1", "research_method": "Controlled trial across 30 firms"},
                 {"paper_id": "P2", "research_method": "Survey of 2,000 employees"}]
    tiers = {"sa": "reputable_preprint", "sb": "verified"}
    rep = build_report(sentences, papers, {"c_a": CA, "c_b": CB}, summaries, lambda p: tiers[p["id"]])
    assert rep["answer"]["text"].startswith("Taken together")
    s1, s2 = rep["sections"]
    assert s1["sub_question"] == WEEK_PKG["sub_questions"][0]
    assert [x["type"] for x in s1["sentences"]] == ["synthesis", "assertive"]
    assert [r["paper"] for r in s1["table"]] == ["P1", "P2"] and s1["table"][0]["method"] == "empirical"
    assert s1["confidence"]["papers"] == 2 and s1["confidence"]["empirical"] == 2 and s1["confidence"]["level"] in ("moderate", "high")
    assert s2["confidence"]["papers"] == 1
    assert any("rests on one paper" in g["text"] for g in rep["gaps"])
    assert rep["implications"][0]["section"] == 1


# ------------------------------------------------------------------------------
# Tests 6-7: UI, export, fallback
# ------------------------------------------------------------------------------
def test_web_app_renders_report_and_export():
    web = Path("web_app.py").read_text(encoding="utf-8")
    # One st.markdown per block: finding cards hold blank lines, which end a shared Markdown HTML block.
    assert 'results.get("report")' in web and "report_blocks(" in web
    from src.ui.brief_view import report_markdown

    rep = {"answer": {"text": "Output held [P1][P2].", "confidence": {"level": "moderate", "papers": 2, "empirical": 2, "conceptual": 0}},
           "sections": [{"index": 1, "sub_question": "Does output hold?", "sentences": [{"type": "synthesis", "text": "Taken together [P1][P2]."}],
                         "table": [{"paper": "P1", "title": "Trial A", "method": "empirical", "finding": "Output stable", "grade": "moderate"}],
                         "confidence": {"level": "moderate", "papers": 2, "empirical": 2, "conceptual": 0}}],
           "tensions": [], "gaps": [{"text": "Section 2 rests on one paper."}], "implications": [{"text": "Pilot it [P1].", "section": 1}]}
    md = report_markdown(rep, question=WEEK_Q)
    assert md.index("## Answer in brief") < md.index("## 1. Does output hold?") < md.index("## Implications")
    assert "| P1 | Trial A | empirical | Output stable | moderate |" in md


def test_fallback_has_a_section_per_sub_question(tmp_path):
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.ledger.migrations import apply_migrations

    db, prac = str(tmp_path / "l.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    r = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    r._harvest_enterprise_lane = lambda **kwargs: []
    r.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1}
    papers = [{"id": f"p{i}", "title": f"Four-day work week trial and employee productivity, study {i}",
               "abstract": "Firms in a four-day work week trial kept employee productivity stable. Employees reported less burnout.",
               "year": 2024, "venue": "Nature Human Behaviour", "url": f"https://doi.org/10.1/{i}"} for i in range(3)]
    res = r.run_workflow(topic=WEEK_Q, approved_question=WEEK_Q, approved_package=WEEK_PKG, map_provider="stub",
                         reduce_provider="stub", academic_papers_override=papers)
    rep = res["report"]
    assert [s["sub_question"] for s in rep["sections"]] == WEEK_PKG["sub_questions"]
    assert all(x["type"] == "assertive" for s in rep["sections"] for x in s["sentences"])
