"""Tests for Slice S5 (part 2): the draft view shows each sentence's evidence on click.

Requirements:
1. A cited finding renders as a click-to-expand block: the sentence is the summary, and the
   body lists each cited quote with its source, grade and the claim's hedge terms.
2. A cited claim with no hedges says so ("No hedge in source").
3. An uncited (unbound) finding shows an "Unbound" badge and says it cites no ledger claim.
4. Quotes and sentences are HTML-escaped (citation pills excepted).
5. The run payload gives each trace its claim's hedge terms, marks unbound findings, and never
   invents a trace (no paper title shown as a "verbatim excerpt", no "VERIFIED" grade).
6. web_app renders findings through the shared card and has no invented-trace fallback.
"""

from __future__ import annotations

from pathlib import Path

from src.ui.evidence_view import finding_card_html


BOUND = {
    "id": "out_1_3",
    "text": "Assistants may shorten cycle time [P1].",
    "binding": "bound",
    "sources_trace": [{
        "claim_id": "c_p1_1", "source_key": "P1", "source_title": "Cycle time study", "url": "https://doi.org/x",
        "venue": "ICSE", "year": "2024", "grade": "MODERATE", "lane": "ACADEMIC", "study_type": "controlled_study",
        "excerpt": "Results suggest assistants may shorten cycle time by 14% (Location: Abstract)",
        "hedge_terms": ["suggest", "may"],
    }],
}


# ------------------------------------------------------------------------------
# Test 1: Cited finding expands to its quotes and hedges
# ------------------------------------------------------------------------------
def test_bound_finding_expands_to_quote_and_hedges():
    html_out = finding_card_html(BOUND, 1, BOUND["text"])
    assert "<details" in html_out and "<summary" in html_out
    summary = html_out.split("<summary", 1)[1].split("</summary>", 1)[0]
    assert "Assistants may shorten cycle time" in summary
    assert "1 cited quote" in summary
    body = html_out.split("</summary>", 1)[1]
    assert "Results suggest assistants may shorten cycle time by 14%" in body
    assert "Cycle time study" in body and "MODERATE" in body
    assert ">suggest<" in body and ">may<" in body


# ------------------------------------------------------------------------------
# Test 2: Claim with no hedges
# ------------------------------------------------------------------------------
def test_claim_without_hedges_says_so():
    item = {**BOUND, "sources_trace": [{**BOUND["sources_trace"][0], "hedge_terms": []}]}
    assert "No hedge in source" in finding_card_html(item, 1, item["text"])


# ------------------------------------------------------------------------------
# Test 3: Unbound finding badge
# ------------------------------------------------------------------------------
def test_unbound_finding_shows_badge():
    item = {"id": "out_1_4", "text": "An untagged claim.", "binding": "unbound", "sources_trace": []}
    html_out = finding_card_html(item, 2, item["text"])
    summary = html_out.split("<summary", 1)[1].split("</summary>", 1)[0]
    assert "Unbound" in summary
    assert "cites no ledger claim" in html_out


# ------------------------------------------------------------------------------
# Test 4: Escaping
# ------------------------------------------------------------------------------
def test_quote_and_sentence_are_escaped():
    item = {**BOUND, "sources_trace": [{**BOUND["sources_trace"][0], "excerpt": "<script>x</script>", "source_title": "A & B"}]}
    html_out = finding_card_html(item, 1, "Safe <b>text</b>", sentence_is_html=False)
    assert "<script>" not in html_out and "&lt;script&gt;" in html_out
    assert "A &amp; B" in html_out
    assert "&lt;b&gt;text&lt;/b&gt;" in html_out


# ------------------------------------------------------------------------------
# Test 5: Payload traces carry hedges; nothing is invented
# ------------------------------------------------------------------------------
def test_payload_traces_carry_hedges_and_are_never_invented(tmp_path, monkeypatch):
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.ledger.migrations import apply_migrations

    db, prac = str(tmp_path / "l.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    runner = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    runner._harvest_enterprise_lane = lambda **kwargs: []
    runner.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1}
    monkeypatch.setattr(runner, "_generate_executive_deliverables", lambda **kw: {
        "executive_summary": "s",
        "key_findings": ["Assistants may shorten cycle time [P1].", "Untagged sentence.", "Points at a paper with no claims [P7]."],
        "generation_mode": "model", "is_fallback": False,
    })
    papers = [{
        "id": "p-cyc", "title": "AI coding assistants and enterprise software delivery cycle time",
        "abstract": "Results suggest AI coding assistants may shorten enterprise software delivery cycle time by 14%.",
        "year": 2024, "venue": "ICSE", "url": "https://doi.org/p-cyc",
    }]
    res = runner.run_workflow(
        topic="How do AI coding assistants affect enterprise software delivery cycle time?",
        map_provider="stub", reduce_provider="stub", academic_papers_override=papers,
    )
    by_text = {f["text"]: f for f in res["findings"]}
    bound = by_text["Assistants may shorten cycle time [P1]."]
    assert bound["binding"] == "bound"
    assert bound["sources_trace"] and bound["sources_trace"][0]["hedge_terms"] == ["suggest", "may"]
    for text in ("Untagged sentence.", "Points at a paper with no claims [P7]."):
        assert by_text[text]["binding"] == "unbound"
        assert by_text[text]["sources_trace"] == []
    assert all(t["grade"] != "VERIFIED" for f in res["findings"] for t in f["sources_trace"])


# ------------------------------------------------------------------------------
# Test 6: web_app uses the shared card, no invented-trace fallback
# ------------------------------------------------------------------------------
def test_web_app_uses_shared_card_without_invented_traces():
    src = Path("web_app.py").read_text(encoding="utf-8")
    assert "finding_card_html(" in src
    assert '"ledger_verified"' not in src
    runner_src = Path("src/analysis/multilane_runner.py").read_text(encoding="utf-8")
    assert '"citation_ref"' not in runner_src
