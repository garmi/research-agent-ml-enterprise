"""Tests for Slice S28b: fixes from live run job_685a8995521c (Check D: 8 of 26 sentences supported).

Requirements:
1. Each source gives the writer numbered quotes (P3.1, P3.2, E2.1 ...): its claims' source sentences, at most 6,
   those with figures or the question's terms first. A map ties each quote id to its claim.
2. The report prompt tells the writer to cite the quote ids each sentence rests on and to write only what those
   quotes say.
3. A quote tag resolves to exactly that claim ([P1.2] -> its claim; unknown ids -> nothing); [P#] tags still work.
   Stored sentences show paper-level tags ([P1.2][P1.3][E2.1] -> [P1][E2]).
4. After Check D, unsupported sentences are removed from the brief by rule and listed with their reasons; partly
   supported sentences stay, marked. Publishing is blocked only when the answer itself is unsupported.
5. The Brief marks partly supported sentences; the Checks tab lists every Check D verdict and reason as text.
"""

from __future__ import annotations

from pathlib import Path

from src.ledger.models import Claim


def _c(cid, sid, text):
    return Claim(id=cid, source_id=sid, text=f"The study reports that {text}", source_excerpt=text[:60], grade="moderate")


CLAIMS = [_c("a1", "s1", "background on review practice in general."),
          _c("a2", "s1", "AI review cut first-review wait by 30% in 12 teams."),
          _c("a3", "s1", "reviewers trusted explained comments more."),
          _c("b1", "s2", "bot comments were often ignored by senior reviewers.")]
PAPERS = [{"id": "s1", "key": "P1"}, {"id": "s2", "key": "P2"}]


# ------------------------------------------------------------------------------
# Test 1: Quote ids
# ------------------------------------------------------------------------------
def test_quote_ids():
    from src.synth.limits import source_quotes

    quotes, qmap = source_quotes(PAPERS, CLAIMS, terms=["review", "reviewers", "wait"])
    assert [q["id"] for q in quotes["P1"]] == ["P1.1", "P1.2", "P1.3"]
    assert quotes["P1"][0]["text"].startswith("AI review cut first-review wait by 30%"), "figures first"
    assert qmap["P1.1"] == "a2" and qmap["P2.1"] == "b1"
    many = [_c(f"x{i}", "s1", f"review finding number {i}.") for i in range(9)]
    assert len(source_quotes(PAPERS[:1], many, terms=["review"])[0]["P1"]) == 6


# ------------------------------------------------------------------------------
# Test 2: Prompt
# ------------------------------------------------------------------------------
def test_prompt_asks_for_quote_ids():
    from src.prompts.research_prompts import ResearchPromptLibrary

    p = ResearchPromptLibrary.report("t", [{"paper_id": "P1", "quotes": [{"id": "P1.1", "text": "x"}]}], ["Q1?"], question="Q?")
    assert "quote ids" in p and "[P2.1]" in p and "only what" in p


# ------------------------------------------------------------------------------
# Test 3: Resolution and display
# ------------------------------------------------------------------------------
def test_quote_tags_resolve_exactly():
    from src.synth.generator import display_tags, resolve_citations

    by_id = {c.id: c for c in CLAIMS}
    qmap = {"P1.1": "a2", "P1.2": "a3", "P2.1": "b1"}
    assert resolve_citations("AI review cut wait by 30% [P1.1].", PAPERS, CLAIMS, by_id, quote_map=qmap) == ["a2"]
    assert resolve_citations("Mixed views [P1.2][P2.1].", PAPERS, CLAIMS, by_id, quote_map=qmap) == ["a3", "b1"]
    assert resolve_citations("Unknown [P1.9].", PAPERS, CLAIMS, by_id, quote_map=qmap) == []
    assert resolve_citations("AI review cut first-review wait by 30% [P1].", PAPERS, CLAIMS, by_id, quote_map=qmap)
    assert display_tags("A [P1.2][P1.3] and B [E2.1][P1].") == "A [P1] and B [E2][P1]."


def test_field_note_binds_quotes_and_shows_paper_tags(tmp_path):
    from src.ledger.migrations import apply_migrations
    from src.ledger.models import Question, Run, Source
    from src.ledger.repository import LedgerRepository
    from src.synth.generator import SynthesisEngine

    db = str(tmp_path / "l.db")
    apply_migrations(db_path=db)
    repo = LedgerRepository(db_path=db)
    repo.insert_question(Question(id="q", text="Does AI review cut wait time?"))
    repo.insert_run(Run(id="r", question_ids=["q"]))
    for sid in ("s1", "s2"):
        repo.insert_source(Source(id=sid, lane="academic", source_type="preprint", title=sid))
    for c in CLAIMS:
        repo.insert_claim(Claim(**{**c.model_dump(), "question_id": "q"}))
    synth = {"executive_summary": "AI review cut first-review wait by 30% [P1.1].",
             "sections": [{"sub_question": "Wait time?", "synthesis": [],
                           "evidence": ["One study reports AI review cut first-review wait by 30% [P1.1]."]}],
             "quote_map": {"P1.1": "a2"}}
    _, sentences, _ = SynthesisEngine(db_path=db).build_field_note(
        question_id="q", run_id="r", executive_synthesis=synth, papers=PAPERS,
        claims_override=[repo.get_claim(c.id) for c in CLAIMS])
    ev = next(s for s in sentences if s.type == "assertive")
    assert ev.claim_ids_json == ["a2"] and ev.text.endswith("[P1].")


# ------------------------------------------------------------------------------
# Test 4: Pruning after Check D
# ------------------------------------------------------------------------------
REPORT = {"answer": {"text": "Answer [P1]."}, "sections": [{"index": 1, "sub_question": "Q1", "sentences": [
    {"type": "assertive", "text": "Good [P1]."}, {"type": "synthesis", "text": "Bad [P1][P2]."},
    {"type": "assertive", "text": "Half [P2]."}]}], "tensions": [{"text": "Bad tension [P1]."}], "gaps": [], "implications": []}


def _cd(verdicts):
    return {"checked": len(verdicts), "unsupported": sum(v == "unsupported" for v in verdicts.values()),
            "items": [{"text": t, "verdict": v, "reason": f"why {t}"} for t, v in verdicts.items()]}


def test_prune_unsupported():
    import copy

    from src.engine.check_d_support import apply_check_d

    result = {"report": copy.deepcopy(REPORT), "status": "PUBLISH_READY",
              "publish_res": {"status": "PUBLISH_READY", "allowed": True, "reasons": ["ok"]}}
    apply_check_d(result, _cd({"Answer [P1].": "supported", "Good [P1].": "supported", "Bad [P1][P2].": "unsupported",
                               "Half [P2].": "partial", "Bad tension [P1].": "unsupported"}))
    texts = [s["text"] for s in result["report"]["sections"][0]["sentences"]]
    assert texts == ["Good [P1].", "Half [P2]."]
    assert result["report"]["sections"][0]["sentences"][1].get("support") == "partial"
    assert result["report"]["tensions"] == []
    assert [d["text"] for d in result["check_d"]["removed"]] == ["Bad [P1][P2].", "Bad tension [P1]."]
    assert result["publish_res"]["allowed"] is True and result["status"] == "PUBLISH_READY"
    assert any("removed" in r for r in result["publish_res"]["reasons"])

    blocked = {"report": copy.deepcopy(REPORT), "status": "PUBLISH_READY",
               "publish_res": {"status": "PUBLISH_READY", "allowed": True, "reasons": ["ok"]}}
    apply_check_d(blocked, _cd({"Answer [P1].": "unsupported"}))
    assert blocked["status"] == "BLOCKED" and blocked["publish_res"]["allowed"] is False


# ------------------------------------------------------------------------------
# Test 5: UI
# ------------------------------------------------------------------------------
def test_brief_marks_partial_and_checks_tab_lists_reasons():
    from src.ui.brief_view import report_blocks

    rep = {"answer": {"text": "A [P1]."}, "sections": [{"index": 1, "sub_question": "Q1", "sentences": [
        {"type": "synthesis", "text": "Half [P2].", "support": "partial"}], "table": [], "confidence": {}}],
        "tensions": [], "gaps": [], "implications": []}
    assert "Partly supported" in "".join(report_blocks(rep, {}, {}))
    web = Path("web_app.py").read_text(encoding="utf-8")
    tab = web[web.index("with tab_checks:"):]
    assert "check_d_items_html(" in tab and "Removed from the brief" in tab
    from src.ui.claims_view import check_d_items_html

    html = check_d_items_html({"items": [{"text": "X <b>", "verdict": "partial", "reason": "adds a claim"}]})
    assert "&lt;b&gt;" in html and "adds a claim" in html and "\n\n" not in html
