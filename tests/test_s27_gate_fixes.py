"""Tests for Slice S27: fixes from live run job_baba65e28a2d (G4 verb blocks, G2 figures, outcome wording,
claims from protocol and background sentences, a nine-minute search stage).

Requirements:
1. Each paper gets evidence limits by rule: the verbs it may take (every verb at or below the rank its weakest
   claim allows, from synth/strength_verbs.yaml) and the figures its claims hold. A paper with no claims gets none.
2. The report and summary prompts carry those limits per paper and tell the model to use only those verbs and
   figures (the weakest paper's verbs when a sentence cites several). The report prompt no longer recommends
   "indicates", a level-4 verb that weak evidence does not allow. The gates are unchanged.
3. When the only practice evidence comes from vendors, the outcome reads "Only vendors describe practice",
   not "Practice ahead of research".
4. The claim extractor skips study-protocol sentences (what a study "will" do) and background sentences (a
   field "is a significant challenge", "is increasingly used"); findings are kept.
5. The academic sources are searched in parallel (one worker per source, queries in order within a source),
   with results in the same order as before; missing abstracts are looked up in parallel within a time budget,
   and papers not reached in time are set aside with that reason.
"""

from __future__ import annotations

import json
import time

from src.ledger.models import Claim


def _claim(cid, sid, text, grade):
    return Claim(id=cid, source_id=sid, text=text, source_excerpt=text[:60], grade=grade)


PAPERS = [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}]
CLAIMS = [_claim("a", "s1", "AI review cut defects by 30% in a field study.", "moderate"),
          _claim("b", "s1", "Teams merged pull requests 2.1x faster.", "weak"),
          _claim("c", "s2", "Our reviewer bot catches more bugs.", "vendor_claim")]


# ------------------------------------------------------------------------------
# Tests 1-2: Evidence limits and prompts
# ------------------------------------------------------------------------------
def test_paper_evidence_limits():
    from src.score.checker import GateChecker
    from src.synth.limits import paper_evidence_limits

    lim = paper_evidence_limits(PAPERS, CLAIMS, GateChecker())
    assert set(lim) == {"P1", "P2"}
    assert "reports" in lim["P1"]["allowed_verbs"] and "describes" in lim["P1"]["allowed_verbs"]
    for strong in ("indicates", "suggests", "shows", "demonstrates"):
        assert strong not in lim["P1"]["allowed_verbs"], strong
    assert sorted(lim["P1"]["figures"]) == ["2.1x", "30%"]
    assert "according to" in lim["P2"]["allowed_verbs"] and "reports" not in lim["P2"]["allowed_verbs"]
    assert lim["P2"]["figures"] == []


def test_report_prompt_carries_limits_and_drops_indicates():
    from src.prompts.research_prompts import ResearchPromptLibrary

    compact = [{"paper_id": "P1", "title": "T", "allowed_verbs": ["reports", "describes"], "figures": ["30%"]}]
    p = ResearchPromptLibrary.report("t", compact, ["Q1?"], question="Q?")
    assert '"allowed_verbs"' in p and "figures" in p
    assert "weakest" in p
    assert 'prefer "suggests", "reports", "indicates"' not in p


def test_limits_reach_report_and_summary_prompts(tmp_path, monkeypatch):
    from tests.test_s20_visuals import FakeLLM, _run, _spec

    llm = FakeLLM(_spec())
    _run(tmp_path, monkeypatch, llm)
    report_prompt = next(p for p in llm.prompts if "Answer each sub-question" in p)
    assert '"allowed_verbs"' in report_prompt and '"figures"' in report_prompt
    summary_prompt = next((p for p in llm.prompts if "thought-leadership" in p.lower()), "")
    assert "Allowed verbs" in summary_prompt


# ------------------------------------------------------------------------------
# Test 3: Outcome wording
# ------------------------------------------------------------------------------
def test_vendor_only_outcome_wording():
    from src.ui.claims_view import claims_overview_html, outcome_plain

    rationale = "Outcome 2: Practice without evidence — Enterprise claims originate solely from vendor sources without independent empirical corroboration."
    title, meaning = outcome_plain(2, rationale)
    assert title == "Only vendors describe practice" and "vendor" in meaning
    assert outcome_plain(2)[0] == "Practice ahead of research"
    html = claims_overview_html({"gap_matrix": {"outcome": 2, "rationale": rationale}, "claims": [], "report": None})
    assert "Only vendors describe practice" in html


# ------------------------------------------------------------------------------
# Test 4: Protocol and background sentences
# ------------------------------------------------------------------------------
def test_extractor_skips_protocol_and_background():
    from src.extract.claim_extractor import extract_claims_from_paper

    abstract = ("Maintaining high code quality in large enterprise repositories is a significant challenge due to rapid growth. "
                "Artificial intelligence is increasingly used for code review and refactoring. "
                "Failed transformations and test regressions will remain in the analytical dataset to prevent survivorship bias. "
                "In a field study of 40 teams, AI-assisted review cut post-merge defects by 20%.")
    claims = extract_claims_from_paper({"id": "p", "title": "T", "abstract": abstract}, question_id="q")
    texts = " ".join(c.text for c in claims)
    assert len(claims) == 1 and "20%" in texts


# ------------------------------------------------------------------------------
# Test 5: Parallel search and abstract budget
# ------------------------------------------------------------------------------
class SlowSource:
    def __init__(self, name, delay=0.2):
        self.name, self.delay = name, delay

    def search(self, q, max_results=10):
        time.sleep(self.delay)
        return [{"title": f"{self.name}:{q}"}]


def test_sources_searched_in_parallel_same_order():
    from src.analysis.harvest import search_sources

    srcs = [SlowSource("a"), SlowSource("b"), SlowSource("c"), SlowSource("d")]
    t0 = time.time()
    batches = search_sources(srcs, ["q1", "q2", "q3"], max_per_query=5)
    assert time.time() - t0 < 1.2, "4 sources x 3 queries x 0.2s run in about 0.6s, not 2.4s"
    assert [b[0]["title"] for b in batches] == [f"{s}:{q}" for q in ("q1", "q2", "q3") for s in "abcd"]


def test_abstract_lookup_budget():
    from src.analysis.abstracts import fill_abstracts

    class SlowFetcher:
        name = "openalex"

        def fetch_abstract(self, doi):
            time.sleep(0.3)
            return "A real abstract about AI-assisted code review outcomes in enterprise teams, long enough to keep." * 2

    papers = [{"title": f"T{i}", "doi": f"10.1/{i}"} for i in range(12)]
    t0 = time.time()
    kept, aside = fill_abstracts(papers, [SlowFetcher()], time_budget=0.5, workers=4)
    assert time.time() - t0 < 1.5
    assert kept and aside and len(kept) + len(aside) == 12
    assert any("time" in a["reason"].lower() for a in aside)
    assert [p["title"] for p in kept] == sorted((p["title"] for p in kept), key=lambda t: int(t[1:]))
