"""Tests for Slice S11: deeper, honest evidence.

Requirements:
1. No source text is ever invented. A paper with a missing or short abstract gets its real abstract
   (OpenAlex, then Semantic Scholar, by DOI); with none found it is set aside with a reason, never
   given a stand-in abstract. Custom URLs that cannot be read get an empty excerpt and no made-up year;
   custom field notes record no invented decision or outcome.
2. Preprint servers and self-archives (SSRN, Zenodo, ResearchGate, OSF, Research Square, Preprints.org,
   TechRxiv) are labelled preprints with their own name as venue, whatever publisher the API reports;
   a DOI alone no longer makes a paper a peer-reviewed journal.
3. Venue tiers: SSRN is a reputable preprint; Zenodo, ResearchGate and similar self-archives are unverified.
4. Search queries come from the approved question and its sub-questions, condensed to their key terms,
   before the generic expansions; no duplicates.
5. When fewer on-topic papers than the depth's target survive Check A, the academic search is widened
   once (the same single retry Check A already has); never twice.
6. "Not searched" boundaries are one line per lane and reason, naming the sources, without repeating
   the question.
7. Evidence-tab paper cards render as HTML (no blank lines inside), with escaped text and safe links.
8. Deep is the default depth, and the depth labels state the real paper limits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analysis.abstracts import fill_abstracts
from src.analysis.multilane_runner import resolve_honest_venue_and_type
from src.analysis.queries import research_queries
from src.ledger.models import SearchLog
from src.synth.generator import search_log_negative_findings
from src.ui.evidence_view import paper_card_html

LONG = "Teams adopting AI coding assistants reported shorter cycle times across forty enterprise repositories."


class FakeFetcher:
    def __init__(self, name, found):
        self.name, self.found, self.calls = name, found, []

    def fetch_abstract(self, doi):
        self.calls.append(doi)
        return self.found.get(doi, "")


# ------------------------------------------------------------------------------
# Test 1: No invented text
# ------------------------------------------------------------------------------
def test_missing_abstracts_are_fetched_or_set_aside():
    papers = [
        {"title": "Has abstract", "abstract": LONG, "doi": "10.1/a"},
        {"title": "Short abstract", "abstract": "Too short.", "doi": "https://doi.org/10.1/b"},
        {"title": "Found second", "abstract": "", "doi": "10.1/c"},
        {"title": "Nothing anywhere", "abstract": "", "doi": "10.1/d"},
        {"title": "No DOI", "abstract": ""},
    ]
    oa = FakeFetcher("openalex", {"10.1/b": LONG})
    s2 = FakeFetcher("semantic_scholar", {"10.1/c": LONG + " More."})
    kept, set_aside = fill_abstracts(papers, [oa, s2])
    assert [p["title"] for p in kept] == ["Has abstract", "Short abstract", "Found second"]
    assert kept[1]["abstract"] == LONG and kept[1]["abstract_source"] == "openalex"
    assert kept[2]["abstract_source"] == "semantic_scholar"
    assert "abstract_source" not in kept[0]
    assert [(p["title"], p["reason"]) for p in set_aside] == [
        ("Nothing anywhere", "No abstract available from OpenAlex or Semantic Scholar."),
        ("No DOI", "No abstract and no DOI to look one up."),
    ]
    assert oa.calls == ["10.1/b", "10.1/c", "10.1/d"] and s2.calls == ["10.1/c", "10.1/d"]


def test_no_stand_in_text_in_the_runner():
    src = Path("src/analysis/multilane_runner.py").read_text(encoding="utf-8")
    for invented in (
        "Evaluates empirical impact, metrics, and technology findings",
        "Empirical findings and technology analysis from",
        "Empirical technical literature and verified findings from",
        "Maintained verified governance and zero ungrounded regression",
        "Integrated automated verification gates for custom stack",
    ):
        assert invented not in src, invented
    assert "fill_abstracts(" in src


def test_unreadable_url_gets_empty_excerpt(monkeypatch):
    import urllib.request

    from src.analysis.multilane_runner import fetch_url_metadata

    def boom(*a, **k):
        raise OSError("unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    title, excerpt, domain = fetch_url_metadata("https://example.org/some-report")
    assert excerpt == "" and domain == "example.org" and title


def test_fetchers_parse_abstracts(monkeypatch):
    import requests

    from src.fetchers.openalex_client import OpenAlexClient
    from src.fetchers.semantic_scholar_client import SemanticScholarClient

    class Resp:
        def __init__(self, status, payload):
            self.status_code, self._payload = status, payload

        def json(self):
            return self._payload

    seen = []

    def fake_get(url, **kw):
        seen.append(url)
        if "openalex" in url:
            return Resp(200, {"abstract_inverted_index": {"Cycle": [0], "times": [1], "fell": [2]}})
        return Resp(200, {"abstract": "Cycle times fell."})

    monkeypatch.setattr(requests, "get", fake_get)
    assert OpenAlexClient().fetch_abstract("https://doi.org/10.1/x") == "Cycle times fell"
    assert SemanticScholarClient().fetch_abstract("10.1/x") == "Cycle times fell."
    assert seen[0].endswith("/works/doi:10.1/x") and seen[1].endswith("/paper/DOI:10.1/x")
    monkeypatch.setattr(requests, "get", lambda url, **kw: Resp(404, {}))
    assert OpenAlexClient().fetch_abstract("10.1/x") == "" and SemanticScholarClient().fetch_abstract("10.1/x") == ""
    assert OpenAlexClient().fetch_abstract("") == ""


# ------------------------------------------------------------------------------
# Tests 2-3: Venue labels and tiers
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("paper,venue", [
    ({"doi": "10.2139/ssrn.5229019", "venue": "Elsevier BV"}, "SSRN"),
    ({"doi": "https://doi.org/10.5281/zenodo.21043500", "venue": "International Journal of X"}, "Zenodo"),
    ({"url": "https://www.researchgate.net/publication/123", "venue": ""}, "ResearchGate"),
    ({"doi": "10.21203/rs.3.rs-1/v1", "venue": "Research Square"}, "Research Square"),
])
def test_preprint_servers_are_preprints(paper, venue):
    v, s_type = resolve_honest_venue_and_type(paper)
    assert v == venue and s_type == "Preprint"


def test_doi_alone_is_not_peer_reviewed():
    _, s_type = resolve_honest_venue_and_type({"doi": "10.9999/abc", "venue": "Some Outlet"})
    assert s_type != "Peer-Reviewed Journal"
    _, s_type = resolve_honest_venue_and_type({"doi": "10.1109/TSE.2024.1", "venue": "IEEE Transactions on Software Engineering"})
    assert s_type == "Peer-Reviewed Journal"


def test_preprint_tiers():
    from src.grade.grader import Grader

    g = Grader()
    assert g.resolve_venue_tier("SSRN", "Preprint") == "reputable_preprint"
    for v in ("Zenodo", "ResearchGate", "OSF Preprints", "Preprints.org", "Research Square", "TechRxiv"):
        assert g.resolve_venue_tier(v, "Preprint") in ("unverified", "reputable_preprint"), v
    assert g.resolve_venue_tier("Zenodo", "Preprint") == "unverified"
    assert g.resolve_venue_tier("ResearchGate", "Preprint") == "unverified"


# ------------------------------------------------------------------------------
# Test 4: Queries from the approved question and sub-questions
# ------------------------------------------------------------------------------
def test_queries_come_from_question_and_sub_questions():
    q = ("What architectural frameworks, workflow transformations, and adoption practices are required for platform "
         "development teams to progress from standalone code generation tools to specialized AI systems?")
    pkg = {"refined_question": q, "sub_questions": [
        "Which orchestration architectures do enterprises use for multi-agent software delivery?",
        "How do platform teams measure the business outcomes of AI coding tools?",
    ]}
    qs = research_queries(q, pkg)
    assert len(qs) == len(set(q_.lower() for q_ in qs))
    assert all(len(x.split()) <= 8 for x in qs[:3])
    assert "orchestration" in qs[1] and "multi" in qs[1] and "agent" in qs[1]
    assert "measure" in qs[2] or "business" in qs[2]
    assert not qs[0].lower().startswith("what")
    assert any("software engineering" in x for x in qs[3:])
    assert research_queries("AI coding assistants and cycle time", None)[0] == "AI coding assistants cycle time"


# ------------------------------------------------------------------------------
# Test 5: Depth retry
# ------------------------------------------------------------------------------
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


def _paper(i):
    return {"id": f"p{i}", "title": f"AI coding assistants shorten cycle time in engineering teams study {i}",
            "abstract": LONG, "year": 2024, "venue": "Empirical Software Engineering", "url": f"https://doi.org/10.1/{i}"}


@pytest.mark.parametrize("first,expected_calls", [(1, 2), (6, 1)])
def test_widen_once_when_below_depth_target(tmp_path, first, expected_calls):
    r = _runner(tmp_path)
    calls = []

    def harvest(**kw):
        calls.append(kw["query_limit"])
        n = first if len(calls) == 1 else 8
        return [_paper(i) for i in range(n)]

    r._harvest_academic_lane = harvest
    r.run_workflow(topic="How do AI coding assistants affect cycle time in engineering teams?", depth="Deep",
                   map_provider="stub", reduce_provider="stub")
    assert len(calls) == expected_calls
    if expected_calls == 2:
        assert calls[1] == calls[0] * 2


def test_depth_targets_in_config():
    import yaml

    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    assert cfg["checks"]["check_a"]["target_on_topic_papers"] == {"fast": 3, "deep": 5}


# ------------------------------------------------------------------------------
# Test 6: One coverage line per lane and reason
# ------------------------------------------------------------------------------
def test_not_searched_is_one_line_per_lane():
    q = "What architectural frameworks are required for platform teams?"
    logs = [
        SearchLog(id=f"e{i}", run_id="r", question_id="q", lane="enterprise", query=q, source_api=api,
                  result_count=0, status="not_implemented", executed_at="x")
        for i, api in enumerate(["dora-dev-survey", "sec-edgar-filings", "aws-dev-blog"])
    ] + [SearchLog(id="p0", run_id="r", question_id="q", lane="practitioner", query=q, source_api="field_notes",
                   result_count=0, status="not_searched", executed_at="x")]
    out = search_log_negative_findings(logs)
    texts = [t for t, _ in out]
    # The question appears as its key terms only, so briefs for different questions never share the line (D1).
    assert texts == [
        "Enterprise sources not searched for 'architectural frameworks required platform teams' (no fetcher yet): "
        "dora-dev-survey, sec-edgar-filings, aws-dev-blog.",
        "Practitioner sources not searched for 'architectural frameworks required platform teams' (no observations recorded): field_notes.",
    ]
    assert all(q not in t for t in texts)
    assert out[0][1]["search_log_ids"] == ["e0", "e1", "e2"] and out[0][1]["search_log_id"] == "e0"


# ------------------------------------------------------------------------------
# Test 7: Evidence cards render
# ------------------------------------------------------------------------------
def test_paper_card_html():
    html = paper_card_html({"key": "P1", "url": "javascript:alert(1)", "title": 'Study <b>"A"</b>', "type": "Preprint",
                            "year": "2025", "venue": "SSRN", "doi": "10.2139/ssrn.1", "is_custom": False})
    assert "\n\n" not in html and "<b>" not in html and "javascript:" not in html
    assert "Preprint" in html and "SSRN" in html and "2025" in html
    no_year = paper_card_html({"key": "P2", "url": "https://x.org", "title": "T", "type": "Preprint",
                               "year": "Date unknown", "venue": "arXiv", "doi": "", "is_custom": True})
    assert "Date unknown" in no_year and "Custom URL" in no_year
    src = Path("web_app.py").read_text(encoding="utf-8")
    assert "paper_card_html(p)" in src


# ------------------------------------------------------------------------------
# Test 8: Deep by default, honest labels
# ------------------------------------------------------------------------------
def test_deep_is_default_and_labels_are_honest():
    src = Path("src/ui/intake_view.py").read_text(encoding="utf-8")
    block = src[src.index('"Research Depth"'):src.index('key="select_research_depth"')]
    assert "index=1" in block
    assert "up to 5 papers" in block and "up to 10 papers" in block
    assert "2 rounds" not in block and "5 rounds" not in block
