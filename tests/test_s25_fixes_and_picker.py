"""Tests for Slice S25: the custom-URL crash, a sub-question picker, and the meditating Buddha mark.

Requirements:
1. A custom enterprise URL that is not a vendor page no longer crashes the run (its commercial stake was
   "independent", which the Source model does not allow): it is stored with stake "unknown". One URL that
   cannot be ingested is skipped with a warning; it never fails the run.
2. Step 2 lists the sub-questions with an include checkbox each: the current proposal's sub-questions start
   ticked, and sub-questions from earlier proposals that the model dropped are listed unticked, so the user can
   bring one back without re-reasoning. Duplicates (ignoring case and spacing) appear once. Only ticked
   sub-questions go into the approved package. The ticks reset for each new proposal version.
3. The header and sidebar show a meditating Buddha mark (inline SVG, labelled for screen readers) next to
   "AI Guruji"; the old microscope mark is gone.
"""

from __future__ import annotations

from pathlib import Path

WEB = Path("web_app.py")
INTAKE = Path("src/ui/intake_view.py")


# ------------------------------------------------------------------------------
# Test 1: Custom enterprise URL
# ------------------------------------------------------------------------------
def _runner(tmp_path, monkeypatch, pages):
    import src.analysis.multilane_runner as mr
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.collectors.enterprise.collector import EnterpriseCollector
    from src.ledger.migrations import apply_migrations
    from src.ledger.models import Question

    monkeypatch.setattr(mr, "fetch_url_metadata", lambda u: pages[u])
    monkeypatch.setattr(EnterpriseCollector, "search_and_ingest", lambda self, **kw: [])
    db, prac = str(tmp_path / "l.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    r = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    q = Question(id="q1", text="How does AI-assisted code review affect review speed?")
    r.repo.insert_question(q)
    return r, q


def test_independent_url_does_not_crash(tmp_path, monkeypatch):
    url = "https://www.example-research.org/reports/ai-code-review-2025"
    text = "Teams using AI-assisted code review reported faster first reviews. Review speed improved in most teams."
    r, q = _runner(tmp_path, monkeypatch, {url: ("AI code review report", text, "www.example-research.org")})
    claims = r._harvest_enterprise_lane(topic=q.text, question_obj=q, run_id="run1", custom_urls=[url])
    assert claims
    src = r._source(claims[0].source_id) or r.repo.get_source(claims[0].source_id)
    assert src.commercial_stake == "unknown"


def test_one_bad_url_is_skipped(tmp_path, monkeypatch):
    good = "https://devblogs.microsoft.com/post"
    bad = "https://broken.example/x"
    pages = {good: ("Post", "Teams using AI-assisted code review reported faster first reviews.", "devblogs.microsoft.com")}
    r, q = _runner(tmp_path, monkeypatch, pages)  # the bad URL raises KeyError inside fetch
    claims = r._harvest_enterprise_lane(topic=q.text, question_obj=q, run_id="run1", custom_urls=[bad, good])
    assert claims, "the good URL is still ingested"


# ------------------------------------------------------------------------------
# Test 2: Sub-question picker
# ------------------------------------------------------------------------------
def test_subquestion_choices():
    from src.ui.intake_view import subquestion_choices

    history = [
        {"sub_questions": ["How fast are reviews?", "What breaks?", "Who benefits most?"]},
        {"sub_questions": ["How fast are reviews?", "What does it cost?", "what  breaks?"]},
    ]
    current = ["How fast are reviews?", "What does it cost?", "What breaks?"]
    choices = subquestion_choices(current, history)
    assert choices == [("How fast are reviews?", True), ("What does it cost?", True), ("What breaks?", True),
                       ("Who benefits most?", False)]
    assert subquestion_choices([], []) == []


def test_picker_wired_into_step_two():
    intake = INTAKE.read_text(encoding="utf-8")
    assert "subquestion_choices(" in intake
    assert 'current_package["sub_questions"] = chosen_sub_qs' in intake
    assert "chk_subq_v" in intake, "checkbox keys carry the proposal version, so ticks reset per version"


# ------------------------------------------------------------------------------
# Test 3: Buddha mark
# ------------------------------------------------------------------------------
def test_buddha_mark():
    from src.ui.brand import BUDDHA_SVG

    assert BUDDHA_SVG.startswith("<svg") and 'aria-label="Meditating Buddha"' in BUDDHA_SVG
    assert "\n\n" not in BUDDHA_SVG
    web = WEB.read_text(encoding="utf-8")
    assert web.count("buddha_svg(") >= 2, "used in the header and the sidebar"
    assert "🔬" not in web
    assert "<h1>AI Guruji</h1>" in web
