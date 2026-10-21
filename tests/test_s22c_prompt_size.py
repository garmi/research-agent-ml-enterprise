"""Tests for Slice S22c: fixes from live run job_48f38d97efe0 (the report call timed out: ReadTimeout).

Requirements:
1. The Gemini client waits up to 300 seconds by default (a report over 20+ sources takes longer than 120).
2. The writer gets at most 8 enterprise entries (newer first), each with at most 3 passages of at most 240
   characters; every entry's allowed verbs list has at most 6 verbs.
3. Grounded pages are read in parallel (several at a time), keeping their order.
4. Sales cues are looked for in the whole page (header and footer included), not only in the article text, so a
   vendor whose "Book a demo" sits in its navigation is still a vendor.
"""

from __future__ import annotations

import time

from src.ledger.models import Claim, Source


def test_gemini_timeout_default():
    from src.llm.gemini_client import GeminiClient

    assert GeminiClient(api_key="test-key-not-real").timeout >= 300


def test_enterprise_entries_are_compact(tmp_path):
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.ledger.migrations import apply_migrations
    from src.score.checker import GateChecker
    from src.synth.limits import paper_evidence_limits

    db, prac = str(tmp_path / "l.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    r = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    claims = []
    for i in range(12):
        sid = f"ent_{i}"
        r._ephemeral_sources[sid] = Source(id=sid, lane="enterprise", source_type="customer_case_study", title=f"Doc {i}",
                                           org=f"org{i}.example", pub_date="2025-01-01")
        for k in range(5):
            claims.append(Claim(id=f"c{i}_{k}", source_id=sid, text="The study reports that " + "AI review cut wait time. " * 20,
                                source_excerpt="AI review cut wait time", grade="weak",
                                context_json={"older_than_window": i < 3}))
    docs, entries = r._enterprise_entries(claims)
    assert len(entries) == 8 and len(docs) == 8
    assert all(len(e["passages"]) <= 3 and all(len(p) <= 240 for p in e["passages"]) for e in entries)
    assert not any(e["older_than_24_months"] for e in entries), "newer sources first"
    lim = paper_evidence_limits(docs, claims, GateChecker())
    assert all(len(v["allowed_verbs"]) <= 6 for v in lim.values())


def test_pages_read_in_parallel(monkeypatch):
    import src.collectors.enterprise.grounded as g
    from src.collectors.enterprise.grounded import GroundedSearch

    class Gem:
        def search_sources(self, prompt):
            return {"chunks": [{"uri": f"https://r/{i}", "title": f"t{i}"} for i in range(6)], "queries": [], "entry_point": ""}

    def slow_fetch(url):
        time.sleep(0.3)
        return ("T " + url, "AI code review cut review wait time for teams in this report about code review.", "2025-01-01", "html")

    monkeypatch.setattr(g, "resolve_redirect", lambda u: u.replace("https://r/", "https://org") + ".example.org/x")
    monkeypatch.setattr(g, "fetch_page", slow_fetch)
    s = GroundedSearch(Gem(), max_calls=1, max_per_call=6, max_docs=6)
    t0 = time.time()
    docs = s.run(["Q?"], ["code", "review", "ai"])
    assert time.time() - t0 < 1.2, "6 pages x 0.3s read side by side"
    assert [d["url"] for d in docs] == [f"https://org{i}.example.org/x" for i in range(6)]


def test_sales_cues_in_navigation_mark_vendor():
    from src.collectors.enterprise.grounded import page_is_selling

    html = ("<html><header><nav><a href='/demo'>Book a demo</a> <a href='/pricing'>Pricing</a></nav></header>"
            "<article><p>AI code review metrics explained for engineering leaders.</p></article></html>")
    assert page_is_selling(html) is True
    assert page_is_selling("<html><article><p>How our team reviews code.</p></article></html>") is False
