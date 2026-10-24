"""Tests for the PR #4 review findings on Slice S5 (hedges, binding, draft view).

Requirements (one per review finding):
1. Finding text is HTML-escaped before citation pills are added; pills still link to their paper.
2. Grouped citations ([P1, P3], [c_a; c_b]) resolve to every cited claim.
3. A claim's hedge terms come from the quote that is shown (the <=25-word excerpt).
4. Common non-hedge words ('can', 'about', 'around') are not counted as hedges.
5. The Check C bake-off leaves process-wide settings alone.
6. Only http(s) source URLs become links in the draft view.
7. Each signal / risk / roadmap sentence resolves its citations once.
8. The draft view reuses Check B's location-tag pattern.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from src.extract.claim_extractor import extract_claims_from_paper
from src.extract.hedges import find_hedge_terms
from src.ledger.models import Claim
from src.synth.generator import resolve_citations
from src.ui.evidence_view import finding_card_html, render_sentence, safe_url

PAPER_MAP = {"P1": {"title": 'Study "A" <1>', "url": "https://doi.org/a", "year": "2024"},
             "P2": {"title": "Bad", "url": "javascript:alert(1)", "year": "2024"}}


# ------------------------------------------------------------------------------
# Test 1: Escape first, then pills
# ------------------------------------------------------------------------------
def test_sentence_escaped_before_pills():
    out = render_sentence('Gains <img src=x onerror=alert(1)> seen [P1].', PAPER_MAP)
    assert "<img" not in out and "&lt;img" in out
    # S29b: the tag became a named chip linking to the paper.
    assert 'href="https://doi.org/a"' in out and "src-chip" in out and "Study 2024" in out
    assert "<1>" not in out
    card = finding_card_html({"id": "s", "text": "x <b>y</b> [P1]", "binding": "unbound", "sources_trace": []}, 1,
                             "x <b>y</b> [P1]", paper_map=PAPER_MAP)
    assert "<b>y</b>" not in card
    src = Path("web_app.py").read_text(encoding="utf-8")
    assert "finding_card_html(item, idx_num, item.get(\"text\", \"\"), paper_map=paper_map)" in src


# ------------------------------------------------------------------------------
# Test 2: Grouped citations resolve
# ------------------------------------------------------------------------------
def test_grouped_citations_resolve():
    claims = [Claim(id="c_a_1", source_id="pa", text="a", source_excerpt="e"),
              Claim(id="c_b_1", source_id="pb", text="b", source_excerpt="e"),
              Claim(id="c_c_1", source_id="pc", text="c", source_excerpt="e")]
    papers = [{"id": "pa"}, {"id": "pb"}, {"id": "pc"}]
    by_id = {c.id: c for c in claims}
    assert resolve_citations("Fell [P1, P3].", papers, claims, by_id) == ["c_a_1", "c_c_1"]
    assert resolve_citations("Both [c_a_1; c_b_1].", papers, claims, by_id) == ["c_a_1", "c_b_1"]
    assert resolve_citations("Mixed [P2][c_c_1] and [note].", papers, claims, by_id) == ["c_b_1", "c_c_1"]


# ------------------------------------------------------------------------------
# Test 3: Hedges come from the shown quote
# ------------------------------------------------------------------------------
def test_hedges_from_shown_excerpt():
    words = " ".join(["word"] * 30)
    abstract = f"Teams adopting assistants report {words} gains that may persist."
    claim = extract_claims_from_paper({"id": "p", "title": "T", "abstract": abstract}, "q")[0]
    assert "may" not in claim.source_excerpt
    assert claim.hedge_terms_json == []


# ------------------------------------------------------------------------------
# Test 4: Common non-hedge words are not hedges
# ------------------------------------------------------------------------------
def test_common_words_not_hedges():
    assert find_hedge_terms("This paper is about code review.") == []
    assert find_hedge_terms("Agents can be deployed via CI around the world.") == []
    assert find_hedge_terms("Gains may persist, with slowdowns of up to 19%.") == ["may", "up to"]


# ------------------------------------------------------------------------------
# Test 5: Check C bake-off leaves globals alone
# ------------------------------------------------------------------------------
def test_check_c_bakeoff_does_not_mutate_env(tmp_path, monkeypatch):
    sys.path.insert(0, "evals")
    import bakeoff_check_c

    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    bakeoff_check_c.main(["--provider", "stub", "--model", "some-model", "--out", str(tmp_path / "r.json")])
    assert "OLLAMA_MODEL" not in os.environ
    assert json.loads((tmp_path / "r.json").read_text())["n"] >= 20


# ------------------------------------------------------------------------------
# Test 6: Only http(s) links
# ------------------------------------------------------------------------------
def test_only_http_links():
    assert safe_url("https://doi.org/a") == "https://doi.org/a"
    assert safe_url("http://x.org") == "http://x.org"
    for bad in ("javascript:alert(1)", "data:text/html,x", "  JAVASCRIPT:x", None, ""):
        assert safe_url(bad) == "#"
    assert 'href="javascript' not in render_sentence("See [P2].", PAPER_MAP).lower()
    card = finding_card_html({"id": "s", "text": "t", "binding": "bound", "sources_trace": [
        {"claim_id": "c", "source_key": "P2", "source_title": "Bad", "url": "javascript:alert(1)", "excerpt": "q",
         "grade": "WEAK", "hedge_terms": []}]}, 1, "t", sentence_is_html=False)
    assert "javascript:" not in card.lower()


# ------------------------------------------------------------------------------
# Test 7: Citations resolved once per sentence
# ------------------------------------------------------------------------------
def test_bind_called_once_per_sentence():
    src = Path("src/synth/generator.py").read_text(encoding="utf-8")
    assert "bind(sig)[0]" not in src and "bind(r)[0]" not in src and "bind(str(act))[0]" not in src


# ------------------------------------------------------------------------------
# Test 8: Location tag pattern reused
# ------------------------------------------------------------------------------
def test_location_tag_reused():
    src = Path("src/ui/evidence_view.py").read_text(encoding="utf-8")
    assert "from src.engine.check_b_wellformed import LOCATION_TAG" in src
    assert "re.compile(" not in src.split("def ")[0] or "_LOCATION_TAG = re.compile" not in src
