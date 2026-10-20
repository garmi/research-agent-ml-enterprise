"""Tests for the PR #17 review findings on Slice S19 (question-shaped report).

Requirements (one per review finding):
1. Derived anchors are the question's subject: terms that recur in two or more of the package's texts
   (sub-questions, scope), plus configured anchors present. The condensed main query keeps them.
2. Every search query stays condensed (at most 10 terms); a sub-question query adds at most the three
   most-recurring subject terms it lacks.
3. A report reply with no usable content falls back to the extractive report and says why.
4. An implication without a section number gets the section whose cited papers it shares most; only an
   implication sharing no papers with any section stays unassigned (and fails G1).
5. The answer's confidence is computed from the papers the answer itself cites.
"""

from __future__ import annotations

import json

from src.ledger.models import Claim, OutputSentence

Q = ("What architectural frameworks, workflow transformations, and adoption practices help platform teams move "
     "from code generation tools to specialised AI systems?")
PKG = {"refined_question": Q, "sub_questions": [
    "Which architectural frameworks support specialised AI systems for platform teams?",
    "How do platform teams change workflows when code generation tools arrive?",
    "Which adoption practices help platform teams scale AI systems?",
]}


# ------------------------------------------------------------------------------
# Tests 1-2: Focused anchors, condensed queries
# ------------------------------------------------------------------------------
def test_anchors_are_the_subject():
    from src.analysis.queries import subject_terms

    anchors = [a.lower() for a in subject_terms(Q, PKG)]
    assert {"platform", "teams", "ai", "systems"} <= set(anchors)
    assert "help" not in anchors and "architectural" not in anchors


def test_queries_stay_condensed():
    from src.analysis.queries import research_queries

    qs = research_queries(Q, PKG)
    assert "AI" in qs[0].split() and "platform" in qs[0].split()
    for q in qs[:1] + qs[2:2 + len(PKG["sub_questions"])]:
        assert len(q.split()) <= 10, q


# ------------------------------------------------------------------------------
# Test 3: Empty report reply falls back
# ------------------------------------------------------------------------------
def test_empty_report_reply_falls_back(tmp_path, monkeypatch):
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.ledger.migrations import apply_migrations

    class Prose:
        model = "fake"

        def generate(self, prompt, system_prompt=None, temperature=0.3, json_mode=False):
            if "Evaluate the following paper" in prompt:
                return json.dumps({"title": "T", "key_findings": "Teams adopted AI systems.", "research_method": "survey"})
            return "Here is my answer in prose, not JSON."

    import src.llm.factory as factory

    monkeypatch.setattr(factory, "build_llm", lambda provider, cfg: Prose())
    db, prac = str(tmp_path / "l.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    r = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    r._harvest_enterprise_lane = lambda **kwargs: []
    r._build_check_llm = lambda provider: None
    r.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1}
    papers = [{"id": f"p{i}", "title": f"Platform teams adopting AI systems with code generation tools, study {i}",
               "abstract": "Platform teams adopting AI systems changed workflows around code generation tools. Adoption practices varied.",
               "year": 2025, "venue": "Empirical Software Engineering", "url": f"https://doi.org/10.1/{i}"} for i in range(3)]
    res = r.run_workflow(topic=Q, approved_question=Q, approved_package=PKG, map_provider="gemini",
                         reduce_provider="gemini", academic_papers_override=papers)
    assert res["is_fallback"] is True
    assert "report" in str((res.get("error_details") or {}).get("error_message", "")).lower()
    assert len(res["report"]["sections"]) == 3


# ------------------------------------------------------------------------------
# Test 4: Implication sections inferred
# ------------------------------------------------------------------------------
def test_implication_section_inferred(tmp_path):
    from src.ledger.migrations import apply_migrations
    from src.ledger.models import Question, Run, Source
    from src.ledger.repository import LedgerRepository
    from src.synth.generator import SynthesisEngine

    db = str(tmp_path / "l.db")
    apply_migrations(db_path=db)
    repo = LedgerRepository(db_path=db)
    repo.insert_question(Question(id="q", text=Q))
    repo.insert_run(Run(id="r", question_ids=["q"]))
    claims = []
    for sid in ("sa", "sb", "sc"):
        repo.insert_source(Source(id=sid, lane="academic", source_type="preprint", title=f"Platform AI systems {sid}"))
        c = Claim(id=f"c_{sid}", question_id="q", source_id=sid, text=f"The study reports that platform teams adopted AI systems ({sid}).",
                  source_excerpt=f"platform teams adopted AI systems {sid}", grade="moderate")
        repo.insert_claim(c)
        claims.append(c)
    synth = {
        "executive_summary": "Platform teams adopted AI systems [P1][P2].",
        "sections": [
            {"sub_question": PKG["sub_questions"][0], "synthesis": [], "evidence": ["One study reports platform teams adopted AI systems [P1]."]},
            {"sub_question": PKG["sub_questions"][1], "synthesis": [], "evidence": ["One study reports platform teams adopted AI systems [P2]."]},
        ],
        "implications": [{"text": "Leaders could pilot platform AI systems [P2].", "section": None},
                         {"text": "Leaders could pilot platform AI systems [P3].", "section": None}],
    }
    _, sentences, _ = SynthesisEngine(db_path=db).build_field_note(
        question_id="q", run_id="r", executive_synthesis=synth, papers=[{"id": "sa"}, {"id": "sb"}, {"id": "sc"}],
        claims_override=[repo.get_claim(c.id) for c in claims])
    imps = [s for s in sentences if s.type == "implication"]
    assert imps[0].checks_json["section"] == 2
    assert not (imps[1].checks_json or {}).get("section")


# ------------------------------------------------------------------------------
# Test 5: Answer confidence from the answer's own papers
# ------------------------------------------------------------------------------
def test_answer_confidence_uses_its_own_papers():
    from src.synth.report import build_report

    C = lambda i: Claim(id=f"c{i}", source_id=f"s{i}", text="t", source_excerpt="e", grade="moderate")
    claims = {f"c{i}": C(i) for i in range(1, 5)}
    S = lambda i, typ, cids, sec=None: OutputSentence(id=f"x{i}", output_id="o", ordinal=i, text=f"t{i}", type=typ,
                                                      claim_ids_json=cids, checks_json={"section": sec} if sec else None)
    sentences = [
        S(1, "summary", ["c1"]),
        OutputSentence(id="h", output_id="o", ordinal=2, text="Sub-question", type="heading", checks_json={"section": 1}),
        S(3, "assertive", ["c1"], 1), S(4, "assertive", ["c2"], 1), S(5, "assertive", ["c3"], 1), S(6, "assertive", ["c4"], 1),
    ]
    papers = [{"id": f"s{i}", "key": f"P{i}", "title": f"T{i}"} for i in range(1, 5)]
    summaries = [{"paper_id": f"P{i}", "research_method": "survey of teams"} for i in range(1, 5)]
    rep = build_report(sentences, papers, claims, summaries, lambda p: "unverified")
    assert rep["answer"]["confidence"]["papers"] == 1
    assert rep["sections"][0]["confidence"]["papers"] == 4
