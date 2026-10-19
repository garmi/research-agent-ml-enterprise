"""Tests for Slice S10: findings cite the claims that support them; the bottom line and roadmap are tied to evidence.

Requirements:
1. A [P#] tag binds the claims from that paper that support the sentence (at least two shared content
   terms, the same rule G2 uses), claims holding the sentence's own numbers first, at most three per tag.
2. When no claim from the paper qualifies, the tag binds its single closest claim, so G2 still reports
   the weak support instead of the sentence silently passing or going unbound.
3. Explicit [c_...] tags and grouped tags still resolve; G2 and the binder share one term rule.
4. A finding bound this way passes G2 where binding every claim of the paper failed it.
5. The bottom line is a gated sentence (type "summary"): bound by its own tags and checked by G1-G4;
   an untagged bottom line fails G1. The run payload's verdict is that sentence.
6. The analysis prompt asks for a short, cited, hedged bottom line with no directives.
7. Each roadmap step records the findings it builds on, the KPI proposed for its phase, and any figure
   that is not in the evidence it cites; the boilerplate outcome line is gone.
8. The roadmap view shows those three things, escaped; the roadmap prompt keeps evidence tags per step.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, Question, Run, Source
from src.ledger.repository import LedgerRepository
from src.score.checker import GROUNDED_TYPES, GateChecker
from src.synth.generator import SynthesisEngine, resolve_citations
from src.ui.brief_view import roadmap_html

PAPERS = [{"id": "pa"}, {"id": "pb"}]
CA1 = Claim(id="c_pa_1", source_id="pa", text="Orchestration improves workflow adaptability by 41%.",
            source_excerpt="orchestration improved workflow adaptability by 41% over static pipelines", grade="moderate")
CA2 = Claim(id="c_pa_2", source_id="pa", text="Skill reuse ratio rose 36% with a skill registry.",
            source_excerpt="skill reuse ratio rose 36% with a shared skill registry", grade="moderate")
CA3 = Claim(id="c_pa_3", source_id="pa", text="The framework supports multi-level outcome tracking.",
            source_excerpt="framework supports multi-level organizational outcome tracking", grade="moderate")
CA4 = Claim(id="c_pa_4", source_id="pa", text="Orchestration workflow adaptability measured in pilots.",
            source_excerpt="orchestration workflow adaptability was measured across enterprise pilots", grade="moderate")
CB1 = Claim(id="c_pb_1", source_id="pb", text="Testing dominates AI use in software engineering.",
            source_excerpt="testing dominates the application of AI across software engineering phases", grade="strong")
ALL = [CA1, CA2, CA3, CA4, CB1]
BY_ID = {c.id: c for c in ALL}


def _bind(text):
    return resolve_citations(text, PAPERS, ALL, BY_ID)


# ------------------------------------------------------------------------------
# Tests 1-3: Binding
# ------------------------------------------------------------------------------
def test_paper_tag_binds_supporting_claims_only():
    assert _bind("A shared skill registry raised the skill reuse ratio [P1].") == ["c_pa_2"]


def test_claims_with_the_sentences_numbers_come_first():
    cids = _bind("Orchestration lifts workflow adaptability by 41% [P1].")
    assert cids[0] == "c_pa_1" and "c_pa_4" in cids and "c_pa_2" not in cids


def test_at_most_three_claims_per_tag():
    many = [Claim(id=f"c_pa_{i}", source_id="pa", text="workflow adaptability orchestration",
                  source_excerpt="workflow adaptability orchestration gains", grade="moderate") for i in range(10, 16)]
    by_id = {c.id: c for c in many}
    assert len(resolve_citations("Orchestration raises workflow adaptability [P1].", PAPERS, many, by_id)) == 3


def test_no_supporting_claim_binds_closest_one():
    cids = _bind("Leaders should rethink budgeting entirely [P1].")
    assert len(cids) == 1 and cids[0].startswith("c_pa_")


def test_explicit_and_grouped_tags():
    assert _bind("Testing dominates AI use [c_pb_1].") == ["c_pb_1"]
    assert _bind("Skill reuse ratio rose and testing dominates software engineering [P1, P2].") == ["c_pa_2", "c_pb_1"]
    assert _bind("No tag here.") == []
    src = Path("src/score/checker.py").read_text(encoding="utf-8")
    assert "support_terms(" in src


# ------------------------------------------------------------------------------
# Test 4: G2 passes with specific binding
# ------------------------------------------------------------------------------
def test_specific_binding_passes_g2_where_all_claims_failed():
    from src.ledger.models import OutputSentence

    text = "A shared skill registry raised the skill reuse ratio by 36% [P1]."
    q = Question(id="q", text="How do skill registries affect skill reuse in orchestration platforms?")
    srcs = {"pa": Source(id="pa", lane="academic", source_type="peer_reviewed", title="Skill reuse in orchestration platforms")}

    def g2(cids):
        s = OutputSentence(id="s1", output_id="o", ordinal=1, text=text, type="assertive", claim_ids_json=cids)
        return GateChecker().check_output(sentences=[s], ledger_claims=BY_ID, source_texts={"pa": srcs["pa"].title},
                                          sources=srcs, question=q, papers=PAPERS).state("G2")

    assert g2(["c_pa_1", "c_pa_2", "c_pa_3", "c_pa_4"]) == "FAIL"
    assert g2(_bind(text)) == "PASS"


# ------------------------------------------------------------------------------
# Tests 5 and 7: Bottom line and roadmap in the field note
# ------------------------------------------------------------------------------
@pytest.fixture()
def engine(tmp_path):
    db = str(tmp_path / "l.db")
    apply_migrations(db_path=db)
    repo = LedgerRepository(db_path=db)
    repo.insert_question(Question(id="q", text="How do orchestration platforms affect skill reuse?"))
    repo.insert_run(Run(id="r", question_ids=["q"]))
    for sid in ("pa", "pb"):
        repo.insert_source(Source(id=sid, lane="academic", source_type="peer_reviewed", title=f"Orchestration study {sid}"))
    for c in ALL:
        repo.insert_claim(c.model_copy(update={"question_id": "q"}))
    return SynthesisEngine(db_path=db), repo


def _note(engine, synth):
    eng, repo = engine
    claims = [repo.get_claim(c.id) for c in ALL]
    return eng.build_field_note(question_id="q", run_id="r", executive_synthesis=synth, papers=PAPERS,
                                claims_override=claims)


SYNTH = {
    "executive_summary": "A shared skill registry may raise the skill reuse ratio [P1].",
    "key_findings": ["A shared skill registry raised the skill reuse ratio by 36% [P1].",
                     "Testing dominates the application of AI across software engineering [P2]."],
    "strategic_roadmap": [{"stage": "0-6 months", "actions": [
        "Stand up a shared skill registry for pilot teams [Head of Platform] [P1]",
        "Enforce a 93.1% SLA target across all pipelines [CTO]",
    ], "kpis": ["Skill reuse ratio (up)"]}],
}


def test_bottom_line_is_a_gated_sentence(engine):
    assert "summary" in GROUNDED_TYPES
    _, sentences, _ = _note(engine, SYNTH)
    summary = [s for s in sentences if s.type == "summary"]
    assert len(summary) == 1 and summary[0].claim_ids_json == ["c_pa_2"]
    assert summary[0].ordinal < min(s.ordinal for s in sentences if s.type == "assertive")

    _, sentences, info = _note(engine, {**SYNTH, "executive_summary": "Leaders must transform their platforms now."})
    summary = [s for s in sentences if s.type == "summary"][0]
    assert not summary.claim_ids_json and (summary.checks_json or {}).get("binding") == "unbound"
    assert info["gate_results"]["hard_gates"]["G1"]["state"] == "FAIL"


def test_roadmap_steps_record_findings_kpis_and_unsupported_figures(engine):
    _, sentences, _ = _note(engine, SYNTH)
    steps = [s for s in sentences if s.type == "roadmap"]
    tied, untied = steps[0].checks_json, steps[1].checks_json
    assert tied["builds_on"] == [1] and tied["kpis"] == ["Skill reuse ratio (up)"] and tied["unsupported_numbers"] == []
    # G2's numeral rule reads "93.1%" as 93.1; the binder uses the same rule.
    assert untied["builds_on"] == [] and untied["unsupported_numbers"] == ["93.1"]


def test_runner_payload_uses_gated_bottom_line_and_roadmap_checks():
    src = Path("src/analysis/multilane_runner.py").read_text(encoding="utf-8")
    assert "Empirical governance target verified" not in src
    assert '"builds_on"' in src and '"unsupported_numbers"' in src and '"measure"' in src
    assert 'summary_sentence' in src


# ------------------------------------------------------------------------------
# Tests 6 and 8: Prompts and roadmap view
# ------------------------------------------------------------------------------
def test_prompts_ask_for_cited_bottom_line_and_tagged_steps():
    from src.prompts.research_prompts import ResearchPromptLibrary as L

    analysis = L.analysis("t", [{"paper_id": "P1"}])
    assert "executive_summary" in analysis and "2-3 sentences" in analysis and "[P#]" in analysis
    assert 'Do not use "must"' in analysis
    roadmap = L.roadmap("t", ["Stand up a registry (Owner: CTO) - reuse is low [P1]"])
    assert "Keep the [P#] tags" in roadmap and "40 words" in roadmap


def test_roadmap_view_shows_basis_kpi_and_flags():
    out = roadmap_html([
        {"phase": "0-6 months", "action": "Stand up a registry [P1]", "builds_on": [1, 3], "measure": "Skill reuse ratio (up)",
         "unsupported_numbers": []},
        {"phase": "0-6 months", "action": "Enforce a 93.1% SLA <b>", "builds_on": [], "measure": "", "unsupported_numbers": ["93.1%"]},
    ])
    assert "Builds on findings 1, 3" in out and "Measure: Skill reuse ratio (up)" in out
    assert "Not tied to a finding" in out and "93.1% is not a figure from the cited evidence" in out
    assert "<b>" not in out and "Expected outcome" not in out
