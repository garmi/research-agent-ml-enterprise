"""Tests for Slice S24b: fixes from the live run job_759a6eb39a4e (AI-assisted code review).

Requirements:
1. A web page given by URL is read for its article text: scripts, styles, navigation, header and footer are
   dropped; <article> or <main> is preferred; entities are unescaped; the whole page is read (not its first
   4,000 characters); the meta description is used only when the page has no readable text. A page that is
   only script gives no text.
2. The summary opening names the question only when it is short (at most 15 words); a long refined question
   is left out, so the post does not open with a paragraph-long question.
3. A summary sentence (opening, for leaders, nuance, what to watch) that states a number of studies or papers
   is kept only when that number matches the evidence profile; otherwise it is dropped and noted.
"""

from __future__ import annotations

PAGE = """<html><head><title>AI code reviews at scale - Engineering</title>
<meta name="description" content="How we use AI code reviews.">
<script>window.theme = localStorage.getItem('theme') || 'light'; document.body.className = theme;</script>
<style>.x { color: red }</style></head>
<body><script>var themePreference = 'dark';</script>
<header><nav>Home Blog Topics Subscribe</nav></header>
<main><article><h1>Enhancing code quality at scale</h1>
<p>AI-powered reviews now comment on most pull requests &amp; reviewers accept many suggestions.</p>
<p>Teams reported faster first review times after rollout.</p></article></main>
<footer>Privacy Terms Cookies</footer></body></html>"""


def test_reads_article_text_not_script():
    from src.analysis.multilane_runner import readable_text

    text = readable_text(PAGE)
    assert "AI-powered reviews now comment on most pull requests & reviewers accept many suggestions." in text
    assert "faster first review times" in text
    for junk in ("localStorage", "themePreference", "color: red", "Subscribe", "Privacy Terms"):
        assert junk not in text, junk


def test_whole_page_is_read():
    from src.analysis.multilane_runner import readable_text

    padded = PAGE.replace("<main>", "<div>" + "<span>x</span>" * 3000 + "</div><main>")
    assert "faster first review times" in readable_text(padded)


def test_script_only_page_gives_meta_or_nothing():
    from src.analysis.multilane_runner import readable_text

    only_script = "<html><head><script>var a = 1; var theme = 'dark';</script></head><body><script>x()</script></body></html>"
    assert readable_text(only_script) == ""
    with_meta = only_script.replace("<head>", '<head><meta name="description" content="A page about AI code review outcomes.">')
    assert readable_text(with_meta) == "A page about AI code review outcomes."


# ------------------------------------------------------------------------------
# Tests 2-3: summary opening and study counts
# ------------------------------------------------------------------------------
def _summary(raw_over, question):
    from tests.test_s21_thought_leadership import CLAIMS, PAPERS, RAW, REPORT
    from src.score.checker import GateChecker
    from src.synth.thought_leadership import build_summary

    return build_summary(dict(RAW, **raw_over), REPORT, PAPERS, CLAIMS, GateChecker(), n_reviewed=11,
                         subject=["review"], question=question)


def test_long_question_left_out_of_opening():
    long_q = ("What empirical effects does the adoption of AI-assisted code review tools have on code quality metrics "
              "and turnaround speed within enterprise software engineering teams?")
    s = _summary({}, long_q)
    assert s["opening"].startswith("I reviewed 11 studies") and long_q not in s["opening"]
    short = _summary({}, "Does AI code review help?")
    assert "Does AI code review help?" in short["opening"]


def test_unchecked_study_counts_dropped():
    s = _summary({"nuance": "While six empirical studies capture early drops, the long run is unsettled.",
                  "for_leaders": "Three papers suggest pairing tools with review."}, "Q?")
    assert "six empirical studies" not in s["nuance"]
    assert s["for_leaders"] == "" or "Three papers" not in s["for_leaders"]
    assert any("count" in d for d in s["dropped"])
    ok = _summary({"for_leaders": "All 3 papers point the same way."}, "Q?")
    assert "All 3 papers point the same way." in ok["for_leaders"], "3 matches the profile (3 papers cited)"
