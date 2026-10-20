"""Tests for Slice S19b: a readable page in both themes, a working Load Question, and an Evidence map.

Requirements:
1. Dark mode cannot leave light text on a white card: it darkens the whole rendered page in one rule
   (an inverting filter, so inline-coloured cards, banners and canvas data grids all follow) and turns
   images and video back so they keep their colours. Light mode adds nothing.
2. The theme switch sits in the main page next to the header, so it is visible (and dark mode can be
   switched off) even when the sidebar is collapsed.
3. "Load Question" puts the question into the Step 1 box (the widget's own state, not only
   current_question) and confirms with a toast naming the question.
4. The Evidence tab opens with an evidence map: one row per paper, a column per sub-question with a
   mark where that section cites the paper, the paper's method, and a "not cited" note for papers no
   section uses; a section backed by fewer than two papers is flagged as thin. Text is escaped.
"""

from __future__ import annotations

from pathlib import Path

WEB = Path("web_app.py")


# ------------------------------------------------------------------------------
# Test 1: Dark mode is one page-wide rule
# ------------------------------------------------------------------------------
def test_dark_mode_inverts_page_and_restores_media():
    from src.ui.theme_mode import theme_css

    dark = theme_css("dark")
    assert "invert(" in dark and "hue-rotate(180deg)" in dark
    for media in ("img", "video"):
        assert media in dark, media
    assert theme_css("light") == ""


# ------------------------------------------------------------------------------
# Test 2: Theme switch visible in the main page
# ------------------------------------------------------------------------------
def test_theme_switch_in_main_page():
    web = WEB.read_text(encoding="utf-8")
    toggle = web.index('st.toggle("🌙 Dark mode"')
    assert toggle > web.index("<h1>AI Guruji</h1>"), "the switch renders with the header, not in the sidebar"
    assert web.count('st.toggle("🌙 Dark mode"') == 1


# ------------------------------------------------------------------------------
# Test 3: Load Question fills the box and confirms
# ------------------------------------------------------------------------------
def test_load_question_fills_box_and_toasts():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("web_app.py")
    at.run(timeout=30)
    loads = [b for b in at.button if str(b.key or "").startswith("load_q_")]
    assert loads, "the register shows at least one Load Question button"
    loads[0].click()
    at.run(timeout=30)
    assert not at.exception, at.exception
    loaded = at.session_state["input_user_question"]
    assert loaded and loaded == at.session_state["current_question"]
    assert any("Loaded" in str(t.value) for t in at.toast)


# ------------------------------------------------------------------------------
# Test 4: Evidence map
# ------------------------------------------------------------------------------
REPORT = {"sections": [
    {"index": 1, "sub_question": "Which frameworks help?", "table": [
        {"paper": "P1", "method": "empirical"}, {"paper": "P2", "method": "conceptual"}]},
    {"index": 2, "sub_question": "How do <teams> change?", "table": [{"paper": "P1", "method": "empirical"}]},
]}
PAPERS = [{"key": "P1", "title": "Study one"}, {"key": "P2", "title": "Essay two"}, {"key": "P3", "title": "Unused <b>three</b>"}]


def test_evidence_map_rows():
    from src.ui.evidence_view import evidence_map

    m = evidence_map(REPORT, PAPERS)
    assert [r["paper"] for r in m["rows"]] == ["P1", "P2", "P3"]
    assert m["rows"][0]["cited"] == [True, True]
    assert m["rows"][1]["cited"] == [True, False]
    assert m["rows"][2]["cited"] == [False, False] and m["rows"][2]["note"] == "not cited"
    assert m["rows"][0]["method"] == "empirical"
    assert m["thin"] == [2]


def test_evidence_map_html_escapes_and_flags_thin():
    from src.ui.evidence_view import evidence_map_html

    out = evidence_map_html(REPORT, PAPERS)
    assert "&lt;teams&gt;" in out and "<teams>" not in out
    assert "&lt;b&gt;three" in out
    assert "thin" in out.lower() and "not cited" in out
    assert "\n\n" not in out, "a blank line would end Markdown's HTML block"
    assert evidence_map_html({}, PAPERS) == ""
