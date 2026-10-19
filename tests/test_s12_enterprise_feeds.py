"""Tests for Slice S12: the first working enterprise-lane fetchers (vendor engineering blog feeds).

Requirements:
1. Feed items use only the feed's own title and summary. An item with no summary is skipped, never
   given its title as a stand-in; HTML is stripped; Atom feeds work as well as RSS.
2. Items are filtered to the approved question with Check A's key-term rule.
3. At most a few items per feed are kept.
4. Vendor blogs are venue_tier "vendor", commercial_stake "vendor" and graded vendor_claim.
5. A network failure logs "searched_error" with zero results, never a pass.
6. Blog feeds are fetched by default (opt out with ALLOW_LIVE_ENTERPRISE=0); EDGAR and DORA still
   have no fetcher and keep logging "not_implemented".
7. In a stub run the "not searched" coverage line no longer names the blogs, and two different
   questions never share a finding sentence (D1).
No test reaches the network: urlopen and the feed fetcher are mocked.
"""

from __future__ import annotations

import io

import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.collectors.enterprise import feed_fetcher
from src.collectors.enterprise.collector import EnterpriseCollector
from src.collectors.enterprise.feed_fetcher import EnterpriseFeedFetcher
from src.ledger.migrations import apply_migrations
from src.ledger.models import Question
from src.synth.generator import search_log_negative_findings

BLOGS = ["aws-dev-blog", "ms-engineering-blog", "google-cloud-blog"]
QUESTION = "How do AI coding assistants affect cycle time in engineering teams?"

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Blog</title>
<item><title>AI coding assistants cut review cycle time</title><link>https://b.example/1</link>
  <pubDate>Tue, 03 Jun 2025 10:00:00 GMT</pubDate>
  <description>&lt;p&gt;Engineering teams using AI coding assistants saw shorter &lt;b&gt;cycle time&lt;/b&gt; in reviews.&lt;/p&gt;</description></item>
<item><title>Item with no summary about AI coding assistants</title><link>https://b.example/2</link>
  <pubDate>Tue, 03 Jun 2025 10:00:00 GMT</pubDate></item>
<item><title>Blank summary about coding assistants</title><link>https://b.example/3</link>
  <description>   </description></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Blog</title>
<entry><title>Coding assistants in engineering teams</title><link href="https://b.example/a1"/>
  <published>2025-04-02T08:00:00Z</published><summary>Teams adopting coding assistants changed how engineering work is reviewed.</summary></entry>
<entry><title>Title only entry</title><link href="https://b.example/a2"/><published>2025-04-03T08:00:00Z</published></entry>
</feed>"""


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _serve(monkeypatch, body):
    monkeypatch.setattr(feed_fetcher, "_rate_limit", lambda *a, **k: None)
    monkeypatch.setattr(feed_fetcher.urllib.request, "urlopen", lambda req, timeout=0: _Resp(body))


def _item(i, title="AI coding assistants shorten cycle time for engineering teams",
          abstract="Engineering teams that adopted AI coding assistants reported shorter cycle time."):
    return {"title": f"{title} {i}", "abstract": abstract, "url": f"https://b.example/{i}", "pub_date": "2025-05-01",
            "speaker": "vendor"}


def _collector(tmp_path):
    db = str(tmp_path / "l.db")
    apply_migrations(db_path=db)
    c = EnterpriseCollector(db_path=db, cache_dir=str(tmp_path / "cache"))
    q = Question(id="q-s12", text=QUESTION, scope="enterprise")
    c.repo.insert_question(q)
    return c, q


# ------------------------------------------------------------------------------
# Test 1: Feed parsing uses only the feed's own text
# ------------------------------------------------------------------------------
def test_rss_skips_items_without_summary_and_strips_html(tmp_path, monkeypatch):
    _serve(monkeypatch, RSS)
    items = EnterpriseFeedFetcher(cache_dir=str(tmp_path)).fetch_rss_feed("https://b.example/rss")
    assert [i["url"] for i in items] == ["https://b.example/1"]
    assert "<" not in items[0]["abstract"] and "cycle time" in items[0]["abstract"]
    assert items[0]["pub_date"] == "2025-06-03" and items[0]["speaker"] == "vendor"


def test_atom_links_are_read_and_summaryless_entries_skipped(tmp_path, monkeypatch):
    _serve(monkeypatch, ATOM)
    items = EnterpriseFeedFetcher(cache_dir=str(tmp_path)).fetch_rss_feed("https://b.example/atom")
    assert [i["url"] for i in items] == ["https://b.example/a1"]
    assert items[0]["pub_date"] == "2025-04-02"


# ------------------------------------------------------------------------------
# Tests 2-4: Filter, cap, vendor grading
# ------------------------------------------------------------------------------
def test_blog_items_filtered_capped_and_graded_as_vendor_claims(tmp_path, monkeypatch):
    c, q = _collector(tmp_path)
    feed = [_item(i) for i in range(6)] + [
        _item(9, title="Optimizing DynamoDB for gaming leaderboards", abstract="Partition keys give low latency for games."),
        # shares only the generic word "teams" with the question
        _item(10, title="Planning offsites for remote teams", abstract="Our teams met in Lisbon for a week."),
    ]
    monkeypatch.setattr(c.fetcher, "fetch_rss_feed", lambda url: feed)
    claims = c.search_and_ingest(question=q, query=QUESTION, allow_live=True)

    logs = {l.source_api: l for l in c.repo.list_search_logs(question_id=q.id)}
    for sid in BLOGS:
        assert logs[sid].status == "searched_ok" and logs[sid].result_count == 3
    blog_claims = [x for x in claims if x.source_id in BLOGS]
    assert blog_claims
    assert not any("dynamodb" in (x.source_excerpt or "").lower() or "lisbon" in (x.source_excerpt or "").lower()
                   for x in blog_claims)
    for sid in BLOGS:
        src = c.repo.get_source(sid)
        assert src.venue_tier == "vendor" and src.commercial_stake == "vendor"
        assert len({x.id for x in blog_claims if x.source_id == sid}) >= 1
    assert {x.grade for x in blog_claims} == {"vendor_claim"}
    assert all((x.context_json or {}).get("url", "").startswith("https://b.example/") for x in blog_claims)


# ------------------------------------------------------------------------------
# Test 5: Network failure is an error, not a pass
# ------------------------------------------------------------------------------
def test_network_failure_logs_searched_error(tmp_path, monkeypatch):
    c, q = _collector(tmp_path)

    def boom(url):
        raise OSError("network down")

    monkeypatch.setattr(c.fetcher, "fetch_rss_feed", boom)
    claims = c.search_and_ingest(question=q, query=QUESTION, allow_live=True)
    assert claims == []
    logs = {l.source_api: l for l in c.repo.list_search_logs(question_id=q.id)}
    for sid in BLOGS:
        assert logs[sid].status == "searched_error" and logs[sid].result_count == 0


# ------------------------------------------------------------------------------
# Test 6: Default on, opt-out, and sources without fetchers stay honest
# ------------------------------------------------------------------------------
def test_blogs_default_live_and_opt_out(tmp_path, monkeypatch):
    c, q = _collector(tmp_path)
    monkeypatch.setattr(c.fetcher, "fetch_rss_feed", lambda url: [_item(1)])
    monkeypatch.delenv("ALLOW_LIVE_ENTERPRISE", raising=False)
    c.search_and_ingest(question=q, query=QUESTION)
    logs = {l.source_api: l for l in c.repo.list_search_logs(question_id=q.id)}
    assert all(logs[s].status == "searched_ok" for s in BLOGS)
    assert logs["sec-edgar-filings"].status == "not_implemented"
    assert logs["dora-dev-survey"].status == "not_implemented"

    (tmp_path / "off").mkdir()
    c2, q2 = _collector(tmp_path / "off")
    monkeypatch.setenv("ALLOW_LIVE_ENTERPRISE", "0")
    c2.search_and_ingest(question=q2, query=QUESTION)
    assert {l.status for l in c2.repo.list_search_logs(question_id=q2.id)} == {"not_implemented"}


def test_suite_default_is_offline():
    import os

    assert os.environ.get("ALLOW_LIVE_ENTERPRISE") == "0"


# ------------------------------------------------------------------------------
# Test 7: Stub run coverage line, and D1
# ------------------------------------------------------------------------------
def _runner(tmp_path):
    db, prac = str(tmp_path / "r.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    r = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    r.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1}
    return r


def _papers(topic_word):
    return [{"id": "p1", "title": f"{topic_word} study", "abstract": f"A study of {topic_word} reported results in detail.",
             "year": 2024, "venue": "Journal", "url": "https://doi.org/10.1/1", "relevance_score": 0.9}]


def test_stub_run_coverage_line_no_longer_lists_blogs(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_LIVE_ENTERPRISE", "1")
    monkeypatch.setattr(EnterpriseFeedFetcher, "fetch_rss_feed", lambda self, url: [_item(1)])
    r = _runner(tmp_path)
    r.run_workflow(topic=QUESTION, depth="Fast", map_provider="stub", reduce_provider="stub",
                   academic_papers_override=_papers("AI coding assistants cycle time engineering teams"))
    slogs = [s for s in r.repo.list_search_logs() if s.lane == "enterprise"]
    texts = [t for t, _ in search_log_negative_findings(slogs)]
    line = next(t for t in texts if t.startswith("Enterprise sources not searched"))
    assert "sec-edgar-filings" in line and "dora-dev-survey" in line
    assert not any(b in line for b in BLOGS)


def test_d1_no_shared_sentences_with_blog_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_LIVE_ENTERPRISE", "1")
    monkeypatch.setattr(EnterpriseFeedFetcher, "fetch_rss_feed", lambda self, url: [_item(1)])
    r = _runner(tmp_path)
    q2 = "How are hospitals governing clinical AI triage tools to manage patient safety?"
    out = []
    for topic, word in ((QUESTION, "AI coding assistants cycle time engineering teams"),
                        (q2, "hospital clinical AI triage patient safety governance")):
        res = r.run_workflow(topic=topic, depth="Fast", map_provider="stub", reduce_provider="stub",
                             academic_papers_override=_papers(word))
        out.append({s["text"].strip() for s in res.get("sentence_traces", []) if s.get("type") == "assertive"})
    assert not (out[0] & out[1])
