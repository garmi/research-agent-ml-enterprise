"""Tests for Slice S22: enterprise and practice evidence found with Gemini's Google Search grounding.

Requirements (recorded responses and pages only; no network):
1. GeminiClient.search_sources sends the google_search tool and returns only the grounding metadata: source URLs
   and titles (groundingChunks), the queries Google ran (webSearchQueries) and the Search Suggestions markup
   (searchEntryPoint). Gemini's answer text is discarded.
2. Redirect links are resolved to the real page URL; a link that cannot be resolved is kept as given.
3. Sources are classified and capped by rule: vendor pages -> vendor_blog / "vendor says"; independent surveys,
   analyst and industry reports, standards and regulators -> industry report, capped at moderate; news -> weak;
   filings -> weak; other company engineering write-ups -> practitioner write-up, weak. Blocklisted domains
   (content farms, social sites) are dropped.
4. Only passages that carry the question's terms become claims, at most `max_claims_per_doc` per document, each
   located "(Location: Web page)" or "(Location: PDF)".
5. A page's publication date is read from its metadata; a page older than the recency window (24 months) is kept
   but marked and ranked after newer pages. An analyst page that only shows a teaser (paywall) is not read and
   gives a coverage note naming the site.
6. In a run, one grounded call is made for the main question and one per sub-question (capped), results are
   de-duplicated, at most `max_docs` pages are read, and each page is its own enterprise Source (so Check A judges
   each). The RSS feeds are not used when grounded search works. With no grounded search (no Gemini key) the run
   falls back to the feeds and logs grounded search as not searched.
7. The writer gets the on-topic enterprise documents as E# entries (type, date, passages, allowed verbs, figures)
   and is told to cite them as [E#] and to say "one vendor reports" / "one organisation reports" unless two or
   more independent organisations agree. [E#] tags resolve to that document's claims; the report table lists the
   E# source with its type; the confidence badge counts papers and practice sources separately.
8. The Evidence tab shows the Search Suggestions next to the enterprise sources and lists the coverage notes.
"""

from __future__ import annotations

import json
from pathlib import Path

GROUNDED_REPLY = {
    "candidates": [{
        "content": {"parts": [{"text": "Gemini's own answer, which must never be used."}]},
        "groundingMetadata": {
            "webSearchQueries": ["AI code review enterprise survey", "AI pull request review case study"],
            "groundingChunks": [
                {"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AAA", "title": "dora.dev"}},
                {"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/BBB", "title": "devblogs.microsoft.com"}},
            ],
            "searchEntryPoint": {"renderedContent": "<div class=\"chips\">AI code review enterprise survey</div>"},
        },
    }]
}


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code, self.ok, self.reason, self.text = payload, status, status < 400, "OK", json.dumps(payload)

    def json(self):
        return self._payload


# ------------------------------------------------------------------------------
# Test 1: Grounded call
# ------------------------------------------------------------------------------
def test_search_sources_reads_only_grounding_metadata(monkeypatch):
    import src.llm.gemini_client as gc

    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent["body"] = json
        return FakeResponse(GROUNDED_REPLY)

    monkeypatch.setattr(gc.requests, "post", fake_post)
    client = gc.GeminiClient(api_key="test-key-not-real")
    out = client.search_sources("Find enterprise evidence on AI code review.")
    assert sent["body"]["tools"] == [{"google_search": {}}]
    assert [c["uri"] for c in out["chunks"]][1].endswith("BBB") and out["chunks"][0]["title"] == "dora.dev"
    assert out["queries"] == GROUNDED_REPLY["candidates"][0]["groundingMetadata"]["webSearchQueries"]
    assert "chips" in out["entry_point"]
    assert "answer" not in json.dumps(out).lower()


# ------------------------------------------------------------------------------
# Test 2: Redirects
# ------------------------------------------------------------------------------
def test_redirects_resolved(monkeypatch):
    import src.collectors.enterprise.grounded as g

    class R:
        url = "https://dora.dev/research/2025/dora-report/"

    monkeypatch.setattr(g.requests, "head", lambda u, allow_redirects=True, timeout=None, headers=None: R())
    assert g.resolve_redirect("https://vertexaisearch.cloud.google.com/grounding-api-redirect/AAA") == R.url

    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(g.requests, "head", boom)
    monkeypatch.setattr(g.requests, "get", boom)
    assert g.resolve_redirect("https://x.example/a") == "https://x.example/a"


# ------------------------------------------------------------------------------
# Test 3: Classification
# ------------------------------------------------------------------------------
def test_classification_by_rule():
    from src.collectors.enterprise.grounded import classify_source

    vendor = classify_source("https://devblogs.microsoft.com/engineering-at-microsoft/x", "AI reviews at scale", "")
    assert (vendor["source_type"], vendor["grade"], vendor["stake"], vendor["label"]) == ("vendor_blog", "vendor_claim", "vendor", "Vendor says")
    survey = classify_source("https://dora.dev/research/2025/", "State of AI-assisted Software Development", "")
    assert (survey["source_type"], survey["grade"], survey["label"]) == ("analyst_survey", "moderate", "Industry report")
    reg = classify_source("https://www.nist.gov/ai/guide", "AI risk guide", "")
    assert reg["source_type"] == "regulator_standard" and reg["grade"] == "moderate"
    news = classify_source("https://www.reuters.com/technology/ai-code", "Banks adopt AI code review", "")
    assert (news["grade"], news["label"]) == ("weak", "News")
    filing = classify_source("https://www.sec.gov/Archives/edgar/data/1/10k.htm", "Annual report", "")
    assert (filing["source_type"], filing["grade"]) == ("filing", "weak")
    write_up = classify_source("https://netflixtechblog.com/ai-review", "How we review code", "")
    assert (write_up["source_type"], write_up["grade"], write_up["label"]) == ("customer_case_study", "weak", "Practitioner write-up")
    assert classify_source("https://www.pinterest.com/pin/1", "AI review", "") is None


# ------------------------------------------------------------------------------
# Tests 4-5: Passages, dates, paywalls
# ------------------------------------------------------------------------------
PAGE = """<html><head><title>AI code review at scale</title>
<meta property="article:published_time" content="2025-06-02T10:00:00Z"></head><body><article>
<p>Our cafeteria now serves lunch at noon on most weekdays for everyone in the building.</p>
<p>AI-assisted code review now comments on 90% of pull requests across the company.</p>
<p>Teams reported that AI code review cut time to first review by about a day.</p>
<p>The weather was pleasant and sunny during the annual conference held last spring.</p>
</article></body></html>"""


def test_passages_with_question_terms_only():
    from src.collectors.enterprise.grounded import select_passages
    from src.analysis.multilane_runner import readable_text

    text = readable_text(PAGE)
    passages = select_passages(text, ["code", "review", "pull", "requests", "ai"], max_sentences=8)
    assert len(passages) == 2 and all("review" in p for p in passages)
    assert len(select_passages(" ".join(["AI code review sentence number %d is here." % i for i in range(20)]),
                               ["code", "review"], max_sentences=8)) == 8


def test_page_date_recency_and_paywall():
    from src.collectors.enterprise.grounded import is_paywalled, older_than, page_date

    assert page_date(PAGE) == "2025-06-02"
    assert older_than("2023-01-15", months=24, today="2026-10-21") is True
    assert older_than("2025-06-02", months=24, today="2026-10-21") is False
    assert older_than("", months=24, today="2026-10-21") is False
    teaser = "Gartner research. To read the full report, log in or become a client. Subscribe to continue reading."
    assert is_paywalled("https://www.gartner.com/en/documents/123", teaser) is True
    assert is_paywalled("https://dora.dev/research/", "A long open report " * 60) is False


# ------------------------------------------------------------------------------
# Test 6: Run integration
# ------------------------------------------------------------------------------
Q = "How does AI-assisted code review affect review speed in enterprise teams?"
PKG = {"refined_question": Q, "sub_questions": ["How does AI code review change time to first review?",
                                                 "What do enterprises report about AI code review quality?"]}


class FakeGemini:
    def __init__(self):
        self.calls = []

    def search_sources(self, prompt):
        self.calls.append(prompt)
        n = len(self.calls)
        return {"chunks": [{"uri": f"https://redirect/{n}{k}", "title": f"site{n}{k}"} for k in range(4)] +
                          [{"uri": "https://redirect/dup", "title": "dup"}],
                "queries": [f"q{n}"], "entry_point": f"<div>chips {n}</div>"}


def _fake_pages():
    pages = {}
    for n in range(1, 4):
        for k in range(4):
            pages[f"https://redirect/{n}{k}"] = (f"https://org{n}{k}.example.org/report", PAGE)
    pages["https://redirect/dup"] = ("https://org10.example.org/report", PAGE)
    return pages


def _runner(tmp_path, searcher):
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.ledger.migrations import apply_migrations

    db, prac = str(tmp_path / "l.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    r = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    r._build_grounded_search = lambda provider: searcher
    r.config.setdefault("enterprise", {})["grounded_search"] = {"enabled": True, "max_calls": 3, "max_per_call": 5,
                                                               "max_docs": 6, "max_claims_per_doc": 8, "recency_months": 24}
    return r


def test_run_uses_grounded_search(tmp_path, monkeypatch):
    import src.collectors.enterprise.collector as col
    import src.collectors.enterprise.grounded as g
    from src.collectors.enterprise.grounded import GroundedSearch
    from src.ledger.models import Question

    pages = _fake_pages()
    monkeypatch.setattr(g, "resolve_redirect", lambda u: pages[u][0])
    monkeypatch.setattr(g, "fetch_page", lambda u: ("AI code review at scale", __import__("src.analysis.multilane_runner", fromlist=["x"]).readable_text(PAGE), "2025-06-02", "html"))
    monkeypatch.setattr(col.EnterpriseCollector, "search_and_ingest", lambda self, **kw: (_ for _ in ()).throw(AssertionError("feeds must not run")))
    gem = FakeGemini()
    r = _runner(tmp_path, GroundedSearch(gem, max_calls=3, max_per_call=5, max_docs=6))
    from src.ledger.models import Run

    q = Question(id="q1", text=Q)
    r.repo.insert_question(q)
    r.repo.insert_run(Run(id="run1", question_ids=["q1"]))
    claims = r._harvest_enterprise_lane(topic=Q, question_obj=q, run_id="run1", grounded_package=PKG, provider="gemini")
    assert len(gem.calls) == 3, "main question + 2 sub-questions"
    sources = {c.source_id for c in claims}
    assert len(sources) == 6, "capped at max_docs, de-duplicated"
    src = r._source(next(iter(sources)))
    assert src.lane == "enterprise" and src.url.startswith("https://org")
    assert all("(Location: Web page)" in c.source_excerpt for c in claims)
    assert r._grounded["entry_point"] and r._grounded["queries"]


def test_no_grounded_search_falls_back_to_feeds(tmp_path, monkeypatch):
    import src.collectors.enterprise.collector as col
    from src.ledger.models import Question

    called = {}
    monkeypatch.setattr(col.EnterpriseCollector, "search_and_ingest", lambda self, **kw: called.setdefault("feeds", []) or [])
    r = _runner(tmp_path, None)
    q = Question(id="q1", text=Q)
    r.repo.insert_question(q)
    r._harvest_enterprise_lane(topic=Q, question_obj=q, run_id="run1", grounded_package=PKG, provider="stub")
    assert "feeds" in called
    assert r._grounded["status"] == "not_searched"


# ------------------------------------------------------------------------------
# Test 7: Writer, citations, report
# ------------------------------------------------------------------------------
def test_report_prompt_has_enterprise_entries_and_wording():
    from src.prompts.research_prompts import ResearchPromptLibrary

    compact = [{"paper_id": "P1", "title": "T"},
               {"paper_id": "E1", "title": "AI reviews at scale", "source_type": "Vendor says", "passages": ["x"]}]
    p = ResearchPromptLibrary.report("t", compact, ["Q1?"], question="Q?")
    assert "[E#]" in p and "according to one vendor" in p and "one organisation reports" in p and "independent" in p


def test_e_tags_resolve_and_report_lists_them():
    from src.ledger.models import Claim, OutputSentence
    from src.synth.generator import resolve_citations
    from src.synth.report import build_report

    claims = {"c1": Claim(id="c1", source_id="s1", text="AI review cut defects in a study of teams.", source_excerpt="cut defects", grade="moderate"),
              "e1": Claim(id="e1", source_id="ent_ms", text="AI review comments on 90% of pull requests.", source_excerpt="90% of pull requests (Location: Web page)", grade="vendor_claim")}
    papers = [{"id": "s1"}]
    enterprise = [{"id": "ent_ms", "key": "E1"}]
    cids = resolve_citations("One vendor reports AI review comments on 90% of pull requests [E1].", papers,
                             list(claims.values()), claims, enterprise=enterprise)
    assert cids == ["e1"]
    sents = [OutputSentence(id="h", output_id="o", ordinal=1, text="Q1?", type="heading", checks_json={"section": 1}),
             OutputSentence(id="a", output_id="o", ordinal=2, text="x [P1]", type="assertive", claim_ids_json=["c1"], checks_json={"section": 1}),
             OutputSentence(id="b", output_id="o", ordinal=3, text="y [E1]", type="assertive", claim_ids_json=["e1"], checks_json={"section": 1})]
    rep = build_report(sents, [{"id": "s1", "key": "P1", "title": "Study"},
                               {"id": "ent_ms", "key": "E1", "title": "AI reviews", "lane": "enterprise", "label": "Vendor says"}],
                       claims, [{"paper_id": "P1", "research_method": "survey of teams"}], lambda p: "unverified")
    rows = {r["paper"]: r for r in rep["sections"][0]["table"]}
    assert rows["E1"]["method"] == "Vendor says"
    conf = rep["sections"][0]["confidence"]
    assert conf["papers"] == 1 and conf["practice"] == 1


# ------------------------------------------------------------------------------
# Test 8: Evidence tab
# ------------------------------------------------------------------------------
def test_evidence_tab_shows_suggestions_and_coverage():
    web = Path("web_app.py").read_text(encoding="utf-8")
    ev = web[web.index('if page == "evidence":'):]
    assert 'results.get("search_entry_point")' in ev and "components.html(" in ev
    assert 'results.get("enterprise_coverage")' in ev
