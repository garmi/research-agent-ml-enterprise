"""Tests for Slice S26: your practitioner experience, captured before feedback and shown after the run.

Requirements (DEC-013 holds throughout: practitioner text is never sent to a remote model):
1. Notes are matched to sub-questions by rule, never by a model: a note goes to the sub-question(s) it shares
   the most distinguishing terms with (terms every sub-question has count for less); a note sharing only the
   question's common subject is "general"; a note sharing nothing is "unmatched". Plurals match singulars.
2. The coverage reads in plain words: "Q1: your notes 1 and 3", "Q2: nothing from your notes", plus which
   notes are general or unmatched.
3. Step 2 has a "Your experience" box (one note per line) that says it stays on this machine and is never sent
   to the model, a no-client-names confirmation, and the coverage lines; the notes are not passed to the
   reasoning or re-reasoning call.
4. At run time the experience notes join the Lane C field notes (no duplicates); the abstraction is confirmed
   only when every box that holds notes was confirmed.
5. After the run, each sub-question section of the Brief shows the matching field-note claims as
   "Your observation" lines (escaped, labelled as not peer-reviewed); the downloadable brief and the share post
   never include them.
"""

from __future__ import annotations

from pathlib import Path

SUBS = ["How does AI-assisted code review affect review speed and cycle time?",
        "How does AI-assisted code review affect defect rates and code quality?",
        "How does AI-assisted code review change developer trust and manual checks?"]
NOTES = ["AI review comments cut our first-review wait and cycle times by a day.",
         "Junior engineers trusted the bot too much and skipped manual checks.",
         "We rolled out AI-assisted code review across teams last year.",
         "Our cafeteria menu changed in March."]


# ------------------------------------------------------------------------------
# Tests 1-2: Matching and coverage
# ------------------------------------------------------------------------------
def test_notes_matched_by_rule():
    from src.ui.experience_view import match_notes

    m = match_notes(NOTES, SUBS)
    assert m["by_question"] == [[1], [], [2]]
    assert m["general"] == [3] and m["unmatched"] == [4]
    assert match_notes([], SUBS) == {"by_question": [[], [], []], "general": [], "unmatched": []}


def test_coverage_lines():
    from src.ui.experience_view import coverage_lines

    lines = coverage_lines(NOTES, SUBS)
    assert lines[0] == "Q1: your note 1"
    assert lines[1] == "Q2: nothing from your notes"
    assert lines[2] == "Q3: your note 2"
    assert "About the question in general: note 3" in lines
    assert "Not matched to any sub-question: note 4" in lines
    assert coverage_lines([], SUBS) == []


# ------------------------------------------------------------------------------
# Test 3: Step 2 box
# ------------------------------------------------------------------------------
def test_step_two_experience_box():
    intake = Path("src/ui/intake_view.py").read_text(encoding="utf-8")
    assert 'key="input_s2_experience"' in intake
    assert "never sent to the model" in intake
    assert 'key="chk_s2_experience_abstract"' in intake
    assert "coverage_lines(" in intake
    for call in ("reason_question(", "feedback_prompt("):
        for chunk in intake.split(call)[1:]:
            args = chunk[: chunk.index(")")]
            assert "experience" not in args, f"{call} must not receive the experience notes"


# ------------------------------------------------------------------------------
# Test 4: Run-time inputs
# ------------------------------------------------------------------------------
def test_practitioner_inputs():
    from src.ui.experience_view import practitioner_inputs

    notes, ok = practitioner_inputs("Note A\nNote B", True, ["Note B", "Note C"], True)
    assert notes == ["Note A", "Note B", "Note C"] and ok is True
    assert practitioner_inputs("Note A", True, ["Note C"], False)[1] is False
    assert practitioner_inputs("", False, ["Note C"], True) == (["Note C"], True)
    assert practitioner_inputs("", False, [], False) == ([], False)
    web = Path("web_app.py").read_text(encoding="utf-8")
    assert "practitioner_inputs(" in web


# ------------------------------------------------------------------------------
# Test 5: After the run
# ------------------------------------------------------------------------------
REPORT = {"answer": {"text": "A [P1].", "confidence": {}}, "sections": [
    {"index": i + 1, "sub_question": q, "sentences": [], "table": [], "confidence": {}} for i, q in enumerate(SUBS)],
    "tensions": [], "gaps": [], "implications": []}
CLAIMS = [{"lane": "PRACTITIONER", "assertion": "Junior engineers trusted the bot too much and skipped manual checks <x>."},
          {"lane": "ACADEMIC", "assertion": "Manual checks dropped [P1]."}]


def test_observations_by_section():
    from src.ui.experience_view import observations_by_section

    obs = observations_by_section(REPORT, CLAIMS)
    assert list(obs) == [3] and "skipped manual checks" in obs[3][0]


def test_brief_shows_observations_but_exports_do_not():
    from src.output.share_pack import post_text
    from src.ui.brief_view import report_blocks, report_markdown
    from src.ui.experience_view import observations_by_section

    obs = observations_by_section(REPORT, CLAIMS)
    html = "".join(report_blocks(REPORT, {}, {}, observations=obs))
    assert "Your observation" in html and "not peer-reviewed" in html
    assert "&lt;x&gt;" in html and "<x>" not in html
    assert "Your observation" not in "".join(report_blocks(REPORT, {}, {}))
    assert "skipped manual checks" not in report_markdown(REPORT, question="Q")
    summary = {"hook": "H", "opening": "O", "takeaways": [{"text": "T [P1].", "papers": ["P1"]}], "question": "Q?", "hashtags": []}
    assert "skipped manual checks" not in post_text(summary, [])
