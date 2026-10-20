"""Tests for Slice S17: tags link by their own sentence; figure-holding claims count; roadmap KPIs once.

Run job_d796557c22fc failed G2 sixteen times. The bottom line's last sentence said "...from D = 0.61 to
D = 0.97 ... 74% [P12]", but [P12] was linked to three claims without those figures: the binder ranked
claims against the whole paragraph, and the claim holding the figures shared only one word with its
25-word quote, so it did not qualify. The roadmap repeated each phase's KPI on every step, and a
"Literature search ... for '<the whole question>' returned 0 matching records" line repeated the question.

Requirements:
1. Each [P#] tag is linked using the sentence that contains it, not the whole paragraph.
2. A claim that holds one of the sentence's figures qualifies as support even with little word overlap.
3. Support terms (binder and G2) come from the claim's quote and its full source sentence, with the
   extractor's "The study reports that" prefix stripped so it cannot inflate overlap. One prefix list,
   owned by the extractor.
4. The roadmap shows each phase once with its KPI, then that phase's steps (basis and flags per step).
5. Searches that returned nothing are one line per lane, naming each source and the question's key terms.
"""

from __future__ import annotations

from pathlib import Path

from src.ledger.models import Claim, OutputSentence, SearchLog
from src.score.checker import GateChecker
from src.synth.generator import best_supporting_claims, resolve_citations, search_log_negative_findings
from src.ui.brief_view import roadmap_html

FIG = Claim(id="c_p12_5", source_id="p12",
            text="The study reports that (5) A prototype evaluation over 40 agent runs yielding D = 0.97 under EA-GKS "
                 "versus D = 0.61 under unmanaged retrieval, 74% audit-effort reduction, and 100% false-composition prevention.",
            source_excerpt="(5) A prototype evaluation over 40 agent runs yielding D = 0.97 under EA-GKS versus D = 0.61 "
                           "under unmanaged retrieval, 74% audit-effort reduction, and",
            grade="weak")
GEN = [Claim(id=f"c_p12_{i}", source_id="p12", text=f"The study reports that enterprise architecture patterns are governance layers {i}.",
             source_excerpt=f"enterprise architecture patterns are the governance layer of software engineering platforms {i}", grade="weak")
       for i in range(1, 4)]
CLAIMS = GEN + [FIG]
BY_ID = {c.id: c for c in CLAIMS}
PAPERS = [{"id": f"p{i}"} for i in range(1, 13)]  # P12 -> p12

PARAGRAPH = ("Platform transitions ground autonomous agents in formal enterprise architecture frameworks and governance "
             "layers [P12]. One study reports that formalized enterprise knowledge improved code determinism from "
             "D = 0.61 to D = 0.97 while reducing audit effort by 74% [P12].")


# ------------------------------------------------------------------------------
# Tests 1-2: Link by sentence; figure claims qualify
# ------------------------------------------------------------------------------
def test_figure_claim_qualifies_with_low_overlap():
    sentence = "One study reports that formalized enterprise knowledge improved code determinism from D = 0.61 to D = 0.97 [P12]."
    assert best_supporting_claims(sentence, CLAIMS)[0] == "c_p12_5"


def test_tags_link_by_their_own_sentence():
    cids = resolve_citations(PARAGRAPH, PAPERS, CLAIMS, BY_ID)
    assert "c_p12_5" in cids and any(c in cids for c in ("c_p12_1", "c_p12_2", "c_p12_3"))


def test_bottom_line_figures_pass_g2():
    cids = resolve_citations(PARAGRAPH, PAPERS, CLAIMS, BY_ID)
    s = OutputSentence(id="s2", output_id="o", ordinal=2, text=PARAGRAPH, type="summary", claim_ids_json=cids)
    res = GateChecker().check_output(sentences=[s], ledger_claims=BY_ID)
    assert not any("ungrounded numeral" in v for v in res.violations["G2"]), res.violations["G2"]


# ------------------------------------------------------------------------------
# Test 3: Support terms use the full sentence, prefix stripped
# ------------------------------------------------------------------------------
def test_support_terms_use_source_sentence_without_prefix():
    from src.extract.claim_extractor import CLAIM_PREFIXES, strip_claim_prefix
    from src.score.checker import claim_support_terms

    assert strip_claim_prefix("The study reports that teams adopt agents.") == "teams adopt agents."
    assert "the study reports that " in CLAIM_PREFIXES
    terms = claim_support_terms(FIG)
    assert {"unmanaged", "retrieval", "prevention"} <= terms
    assert not {"study", "reports"} & claim_support_terms(GEN[0])

    only_prefix = Claim(id="c_x", source_id="px", text="The study reports that latency fell.", source_excerpt="latency fell", grade="weak")
    s = OutputSentence(id="s1", output_id="o", ordinal=1, text="One study reports that budgets rose [P1].", type="assertive",
                       claim_ids_json=["c_x"])
    res = GateChecker().check_output(sentences=[s], ledger_claims={"c_x": only_prefix})
    assert any("Insufficient excerpt overlap" in v for v in res.violations["G2"])

    for path in ("src/synth/generator.py", "src/analysis/multilane_runner.py"):
        assert '("the study reports that ", "the study finds that "' not in Path(path).read_text(encoding="utf-8"), path


# ------------------------------------------------------------------------------
# Test 4: Each phase's KPI once
# ------------------------------------------------------------------------------
def test_roadmap_shows_each_phase_kpi_once():
    steps = [
        {"phase": "0-6 months", "action": "Gateway [P6]", "builds_on": [2], "measure": "PII leakage: 0%", "unsupported_numbers": []},
        {"phase": "0-6 months", "action": "Command center [P7]", "builds_on": [6], "measure": "PII leakage: 0%", "unsupported_numbers": []},
        {"phase": "6-18 months", "action": "EA-GKS in CI [P9]", "builds_on": [1], "measure": "Violation escapes < 5%", "unsupported_numbers": []},
    ]
    out = roadmap_html(steps)
    assert out.count("PII leakage: 0%") == 1 and out.count("Violation escapes &lt; 5%") == 1
    assert out.count('class="roadmap-phase-head"') == 2
    assert out.index("0-6 months") < out.index("Gateway") < out.index("Command center") < out.index("6-18 months")
    assert out.count("Builds on finding") == 3


# ------------------------------------------------------------------------------
# Test 5: Empty searches, one line per lane
# ------------------------------------------------------------------------------
def test_empty_searches_one_line_per_lane():
    q = "How do architectural frameworks and workflow transformations help platform teams adopt AI code generation?"
    logs = [SearchLog(id=f"a{i}", run_id="r", question_id="q", lane="academic", query=q, source_api=api,
                      result_count=0, status="searched_ok", executed_at="x") for i, api in enumerate(["Crossref", "arXiv"])]
    out = search_log_negative_findings(logs)
    assert len(out) == 1
    text, checks = out[0]
    assert text.startswith("Academic searches that returned no records for '") and "Crossref, arXiv" in text
    assert q not in text and checks["search_log_ids"] == ["a0", "a1"]
