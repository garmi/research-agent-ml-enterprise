"""Tests for Slice S29b: readable citations on the Brief and Evidence pages ([P1][E2] are hard to relate to).

Requirements:
1. Each source gets a name by rule: a paper -> first author's surname + year ("Chen 2024"); a paper with no authors ->
   its first three content words + year; an enterprise source -> its organisation (or site name) + year. Duplicate
   names get a/b. Each source also gets a kind: study (papers), report (industry report, standard, filing, news,
   practitioner write-up) or vendor ("Vendor says").
2. On screen, [P#] / [E#] / [P#.n] tags become chips with the source's name and kind; no codes are left in the
   sentence. The chip links to the source and its hover text names the title. Unknown tags stay as plain text.
3. A brief sentence with cited claims opens (click) to show the exact quotes it rests on, each under its source's
   chip. The Brief shows a one-line legend of the three kinds.
4. The evidence map names its sources and says how many brief sentences each section takes from each one; a section
   no source backs is flagged. Diagram boxes name their sources.
5. The brief download uses names inline ("(Chen 2024)") and ends with a numbered source list.
The ledger, the gates and Check D keep using P#/E#.
"""

from __future__ import annotations

import re

PAPERS = [
    {"id": "s1", "key": "P1", "title": "AI coding assistants and cycle time in teams", "year": "2024",
     "venue": "Empirical Software Engineering", "url": "https://doi.org/10.1/a", "authors": ["Wei Chen", "Ana Ruiz"]},
    {"id": "s2", "key": "P2", "title": "The effects of code review bots on defects", "year": "2023",
     "venue": "ICSE", "url": "https://doi.org/10.1/b"},
    {"id": "s3", "key": "P3", "title": "Another paper", "year": "2024", "url": "https://doi.org/10.1/c",
     "authors": [{"name": "Li Chen"}]},
]
DOCS = [
    {"id": "e1", "key": "E1", "title": "Why our reviewer catches more bugs", "label": "Vendor says", "venue": "CodeRabbit",
     "year": "2025", "url": "https://www.coderabbit.ai/blog/x"},
    {"id": "e2", "key": "E2", "title": "State of DevOps", "label": "Industry report", "venue": "", "year": "n.d.",
     "url": "https://www.dora.dev/research/2025"},
]
MAP = {p["key"]: p for p in PAPERS + DOCS}


def _claims():
    from src.ledger.models import Claim

    return {"c1": Claim(id="c1", source_id="s1", text="The study reports that wait fell.",
                        source_excerpt="Median time to first review fell from 9.1 to 6.4 hours.", grade="moderate"),
            "c2": Claim(id="c2", source_id="e1", text="The vendor states its bot catches more bugs.",
                        source_excerpt="Teams using our reviewer caught 2x more issues.", grade="vendor_claim")}


# ------------------------------------------------------------------------------
# Test 1: Names and kinds
# ------------------------------------------------------------------------------
def test_source_labels():
    from src.ui.evidence_view import source_labels

    lab = source_labels(PAPERS + DOCS)
    assert lab["P1"]["name"] == "Chen 2024a" and lab["P3"]["name"] == "Chen 2024b", "duplicates get a/b"
    assert lab["P2"]["name"] == "Effects code review 2023", "no authors: first content words + year"
    assert lab["E1"]["name"] == "CodeRabbit 2025" and lab["E1"]["kind"] == "vendor"
    assert lab["E2"]["name"] == "Dora" and lab["E2"]["kind"] == "report", "no organisation: the site name; no year"
    assert lab["P1"]["kind"] == "study"


# ------------------------------------------------------------------------------
# Test 2: Chips instead of codes
# ------------------------------------------------------------------------------
def test_tags_become_named_chips():
    from src.ui.evidence_view import render_sentence

    out = render_sentence('Wait fell <b>a lot</b> [P1.2][E1] and more [P9].', MAP)
    assert "Chen 2024a" in out and "CodeRabbit 2025" in out
    assert "src-chip src-study" in out and "src-chip src-vendor" in out
    assert "[P1" not in out and "[E1]" not in out
    assert "[P9]" in out, "an unknown tag stays as plain text"
    assert "<b>a lot</b>" not in out and 'href="https://doi.org/10.1/a"' in out
    assert 'title="AI coding assistants and cycle time in teams' in out


# ------------------------------------------------------------------------------
# Test 3: Click a sentence to see its quotes; legend
# ------------------------------------------------------------------------------
def _report():
    return {"answer": {"text": "Wait fell [P1] and vendors claim more [E1].", "claim_ids": ["c1", "c2"]},
            "sections": [{"index": 1, "sub_question": "Does wait fall?", "sentences": [
                {"type": "synthesis", "text": "Taken together, wait fell [P1][E1].", "claim_ids": ["c1", "c2"]}],
                "table": [{"paper": "P1", "title": "AI coding", "method": "empirical", "finding": "wait fell", "grade": "moderate"}]},
                {"index": 2, "sub_question": "Does trust change?", "sentences": [], "table": []}],
            "tensions": [], "gaps": [{"text": "Long-term effects are open [P2]."}],
            "implications": [{"text": "Pilot it [P1].", "section": 1}]}


def test_sentences_open_to_their_quotes_and_no_codes_left():
    from src.ui.brief_view import report_html

    html = report_html(_report(), MAP, {}, claims_by_id=_claims())
    assert "<details" in html and "Median time to first review fell from 9.1 to 6.4 hours." in html
    assert "Teams using our reviewer caught 2x more issues." in html
    assert not re.search(r"\[[PE]\d", html), "no [P#] / [E#] codes on screen"
    assert "src-legend" in html and "study" in html and "vendor says" in html


def test_trace_cards_name_their_source():
    from src.ui.evidence_view import finding_card_html

    item = {"text": "Wait fell [P1].", "sources_trace": [{"claim_id": "c1", "source_key": "P1", "source_title": "AI coding",
                                                           "excerpt": "Median fell.", "url": "https://doi.org/10.1/a"}]}
    card = finding_card_html(item, 1, item["text"], paper_map=MAP)
    assert "Chen 2024a" in card and "[P1]" not in card


# ------------------------------------------------------------------------------
# Test 4: Evidence map and diagram
# ------------------------------------------------------------------------------
def test_evidence_map_names_sources_and_counts_use():
    from src.ui.evidence_view import evidence_map, evidence_map_html

    m = evidence_map(_report(), PAPERS + DOCS)
    row = {r["paper"]: r for r in m["rows"]}
    assert row["P1"]["counts"] == [1, 0] and row["E1"]["counts"] == [1, 0]
    assert m["unbacked"] == [2]
    html = evidence_map_html(_report(), PAPERS + DOCS)
    assert "Chen 2024a" in html and "used · 1" in html and "no source" in html
    assert not re.search(r">\s*[PE]\d+\s*<", html)


def test_diagram_boxes_name_sources():
    from src.ui.diagrams import diagram_svg

    spec = {"type": "pathway", "title": "T", "nodes": [{"id": "a", "label": "Start", "cites": ["P1"]},
                                                       {"id": "b", "label": "End", "cites": ["E1"]}],
            "edges": [{"from": "a", "to": "b"}]}
    svg = diagram_svg(spec, labels={"P1": "Chen 2024a", "E1": "CodeRabbit 2025"})
    assert "Chen 2024a" in svg and "CodeRabbit 2025" in svg


# ------------------------------------------------------------------------------
# Test 5: Download
# ------------------------------------------------------------------------------
def test_markdown_uses_names_and_lists_sources():
    from src.ui.brief_view import report_markdown

    md = report_markdown(_report(), question="Q?", papers=PAPERS + DOCS)
    assert "(Chen 2024a)" in md and "(CodeRabbit 2025)" in md and "[P1]" not in md
    assert "## Sources" in md
    assert "1. Chen 2024a — AI coding assistants and cycle time in teams" in md


def test_result_papers_keep_their_authors():
    import inspect

    from src.analysis.multilane_runner import MultiLaneResearchRunner

    assert '"authors"' in inspect.getsource(MultiLaneResearchRunner._format_papers)
