"""Tests for Slice S24: a Claims & gaps tab a busy reader understands at a glance.

Requirements:
1. Evidence grades read as plain labels with a one-line meaning (strong, moderate, weak, vendor says,
   anecdote); an unknown grade reads "Not graded".
2. "At a glance" states each lane in plain words (research papers, enterprise practice, your field notes): how
   many claims from how many sources, and what that means; never the raw state words ("SUPPORTED", "none found").
3. The outcome reads as a title and one sentence ("Research ahead of practice" ...), for outcomes 1-4 and
   "Practice not assessed".
4. Claims are grouped by the sub-question whose report section cites them, then "Found but not used in the
   brief"; each claim reads as its plain sentence (no "The study reports that" lead-in) with its source and grade.
5. "What's missing" lists, in plain words: the report's gap sentences (no [P#] tags), sections resting on
   fewer than two papers, and lanes with no evidence or not searched.
6. The HTML escapes every text and has no blank lines; the tab shows it first, and the full claim table moves
   into a "Full claim ledger" expander.
"""

from __future__ import annotations

import json
from pathlib import Path

CLAIMS = [
    {"id": "c1", "assertion": "The study reports that AI review cut review time by 30%.", "excerpt": "cut review time by 30%",
     "grade": "MODERATE", "lane": "ACADEMIC", "source_key": "P1", "source_title": "Review study", "venue": "ICSE", "year": "2025"},
    {"id": "c2", "assertion": "AI comments were often ignored <sometimes>.", "excerpt": "often ignored",
     "grade": "WEAK", "lane": "ACADEMIC", "source_key": "P2", "source_title": "Field study", "venue": "arXiv", "year": "2026"},
    {"id": "c3", "assertion": "Our reviewer bot catches more bugs.", "excerpt": "catches more bugs",
     "grade": "VENDOR_CLAIM", "lane": "ENTERPRISE", "source_key": "src_ms", "source_title": "Vendor blog", "venue": "Microsoft", "year": "2025"},
    {"id": "c4", "assertion": "Unused claim text.", "excerpt": "unused", "grade": "MODERATE", "lane": "ACADEMIC",
     "source_key": "P3", "source_title": "Third", "venue": "TSE", "year": "2024"},
]
REPORT = {
    "sections": [
        {"index": 1, "sub_question": "How does AI review change quality?", "sentences": [
            {"type": "assertive", "text": "One study reports a 30% cut [P1].", "claim_ids": ["c1"]},
            {"type": "synthesis", "text": "Comments were ignored [P2].", "claim_ids": ["c2", "c1"]}],
         "table": [{"paper": "P1"}, {"paper": "P2"}]},
        {"index": 2, "sub_question": "What slows review?", "sentences": [], "table": []},
    ],
    "gaps": [{"text": "No study followed teams beyond six months [P1][P2]."},
             {"text": "Section 2 has no evidence from the papers found."}],
}
RESULTS = {
    "claims": CLAIMS, "report": REPORT,
    "gap_matrix": {"academic_state": "supported", "enterprise_state": "partial", "field_state": "none found", "outcome": 1},
    "lane_breakdown": {"academic_sources_count": 3, "academic_claims_count": 3, "enterprise_sources_count": 1,
                       "enterprise_claims_count": 1, "practitioner_observations_count": 0, "practitioner_claims_count": 0},
}


# ------------------------------------------------------------------------------
# Test 1: Grade labels
# ------------------------------------------------------------------------------
def test_grade_labels():
    from src.ui.claims_view import grade_label

    assert grade_label("STRONG")[0] == "Strong"
    assert grade_label("moderate")[0] == "Moderate"
    assert grade_label("WEAK")[0] == "Weak"
    assert grade_label("VENDOR_CLAIM")[0] == "Vendor says"
    assert grade_label("ANECDOTE")[0] == "Anecdote"
    assert grade_label("??")[0] == "Not graded"
    assert all(grade_label(g)[1] for g in ("strong", "moderate", "weak", "vendor_claim", "anecdote"))


# ------------------------------------------------------------------------------
# Tests 2-3: At a glance and outcome
# ------------------------------------------------------------------------------
def test_lanes_in_plain_words():
    from src.ui.claims_view import lane_summary

    lanes = lane_summary(RESULTS)
    assert [l["name"] for l in lanes] == ["Research papers", "Enterprise practice", "Your field notes"]
    assert lanes[0]["count"] == "3 claims from 3 papers"
    assert lanes[1]["count"] == "1 claim from 1 source"
    assert "none" in lanes[2]["meaning"].lower() or "no " in lanes[2]["meaning"].lower()
    text = json.dumps(lanes)
    for raw in ("SUPPORTED", "supported", "none found", "partial"):
        assert raw not in text, raw
    not_searched = lane_summary(dict(RESULTS, gap_matrix=dict(RESULTS["gap_matrix"], enterprise_state="not searched")))
    assert "not searched" in not_searched[1]["meaning"].lower()


def test_outcome_plain():
    from src.ui.claims_view import outcome_plain

    titles = [outcome_plain(o)[0] for o in (1, 2, 3, 4, "Practice not assessed")]
    assert titles == ["Research and practice agree", "Practice ahead of research", "Research ahead of practice",
                      "Thin evidence everywhere", "Practice not checked"]
    assert all(outcome_plain(o)[1] for o in (1, 2, 3, 4, "practice_not_assessed"))
    assert outcome_plain("2")[0] == "Practice ahead of research"


# ------------------------------------------------------------------------------
# Test 4: Claims by sub-question
# ------------------------------------------------------------------------------
def test_claims_grouped_by_question():
    from src.ui.claims_view import claims_by_question

    groups = claims_by_question(RESULTS)
    assert [g["title"] for g in groups] == ["1. How does AI review change quality?", "Found but not used in the brief"]
    assert [c["id"] for c in groups[0]["claims"]] == ["c1", "c2"]
    assert groups[0]["claims"][0]["text"] == "AI review cut review time by 30%."
    assert groups[0]["mix"] == "1 moderate · 1 weak"
    assert [c["id"] for c in groups[1]["claims"]] == ["c3", "c4"]
    assert groups[1]["claims"][0]["source"] == "Vendor blog · Microsoft · 2025"


# ------------------------------------------------------------------------------
# Test 5: What's missing
# ------------------------------------------------------------------------------
def test_missing_in_plain_words():
    from src.ui.claims_view import missing_plain

    lines = missing_plain(RESULTS)
    assert "No study followed teams beyond six months." in lines
    assert not any("[P" in l for l in lines)
    assert any("What slows review?" in l and "no evidence" in l for l in lines)
    assert any("field notes" in l.lower() for l in lines)
    assert len(lines) == len(set(lines))


# ------------------------------------------------------------------------------
# Test 6: HTML and tab
# ------------------------------------------------------------------------------
def test_overview_html_escaped_one_block():
    from src.ui.claims_view import claims_overview_html

    out = claims_overview_html(RESULTS)
    assert "At a glance" in out and "What&#x27;s missing" in out or "What's missing" in out
    assert "&lt;sometimes&gt;" in out and "<sometimes>" not in out
    assert "\n\n" not in out
    assert "Research and practice agree" in out


def test_claims_tab_shows_overview_first():
    web = Path("web_app.py").read_text(encoding="utf-8")
    tab = web[web.index('if page == "evidence":'):]
    assert tab.index("claims_overview_html(") < tab.index("render_safe_table(claims_table_data")
    assert 'st.expander("Full claim ledger' in tab
    assert 'm_col1.metric("Academic Lane State"' not in web


def test_quote_drops_location_tag():
    from src.ui.claims_view import claims_by_question

    res = dict(RESULTS, claims=[dict(CLAIMS[0], excerpt="cut review time by 30% (Location: Abstract)")], report=REPORT)
    c = claims_by_question(res)[0]["claims"][0]
    assert c["excerpt"] == "cut review time by 30%" and c["where"] == "from the abstract"
