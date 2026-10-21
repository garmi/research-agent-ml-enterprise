"""Tests for Slice S28c: fixes from live run job_02026a208ae9 (17 supported, 10 partial, 2 unsupported of 29).

Requirements:
1. Check D tells the judge each sentence's type and judges by type: an implication is supported when the evidence
   it rests on is supported (its recommendation wording is not a claim); a gap sentence is supported when the
   quotes show that limitation or say the matter is open.
2. When sources give quotes, the writer no longer gets narrative summary fields (key findings, problem, relevance)
   to borrow details from; it keeps title, method and limitations, plus the quotes.
3. One repair pass: each partly supported brief sentence is rewritten once to say only what its quotes say (verbs
   softened by rule again), then judged again. Supported -> it replaces the sentence (marked repaired); otherwise
   the sentence is removed and listed with the reason. A partly supported answer stays, marked. Partly supported
   takeaways are dropped from the share post.
4. Check D reports the support rate of what remains in the brief, and the Checks tab shows it.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from src.ledger.models import Claim

CLAIMS = {"c1": Claim(id="c1", source_id="s1", text="The study reports that individual job satisfaction rose under a 4-day week.",
                      source_excerpt="individual job satisfaction rose", grade="moderate"),
          "c2": Claim(id="c2", source_id="s2", text="The study reports that weekday stress increased with workload compression.",
                      source_excerpt="weekday stress increased", grade="moderate")}
LANES = {"s1": "academic", "s2": "academic"}


# ------------------------------------------------------------------------------
# Test 1: Type-aware judging
# ------------------------------------------------------------------------------
def test_check_d_prompt_is_type_aware():
    from types import SimpleNamespace

    from src.engine.check_d_support import run_check_d

    seen = []

    class J:
        def generate(self, prompt, system_prompt=None, temperature=0.0, json_mode=False):
            seen.append(prompt)
            return '{"verdicts": []}'

    sents = [SimpleNamespace(id="a", ordinal=1, text="Leaders should watch stress [P2].", type="implication", claim_ids_json=["c2"]),
             SimpleNamespace(id="b", ordinal=2, text="Long-term effects remain open [P1].", type="gap", claim_ids_json=["c1"])]
    run_check_d(sents, CLAIMS, LANES, J())
    p = seen[0]
    assert "[S1] (implication)" in p and "[S2] (gap)" in p
    assert "recommendation" in p.lower() and "limitation" in p.lower()


# ------------------------------------------------------------------------------
# Test 2: No narrative summary fields beside quotes
# ------------------------------------------------------------------------------
def test_writer_gets_quotes_not_summaries(tmp_path, monkeypatch):
    from tests.test_s20_visuals import FakeLLM, _run, _spec

    llm = FakeLLM(_spec())
    _run(tmp_path, monkeypatch, llm)
    rp = next(p for p in llm.prompts if "Answer each sub-question" in p)
    assert '"quotes"' in rp and '"key_findings"' not in rp and '"research_method"' in rp


# ------------------------------------------------------------------------------
# Test 3: One repair pass
# ------------------------------------------------------------------------------
class Repairer:
    """Rewrites on the repair prompt; on the Check D prompt, supports sentences that say 'individual'."""

    def generate(self, prompt, system_prompt=None, temperature=0.0, json_mode=False):
        if "Rewrite each sentence" in prompt:
            return json.dumps({"rewrites": [{"id": "S1", "text": "One study reports individual job satisfaction rose [P1]."},
                                            {"id": "S2", "text": "Leaders should demonstrably act on stress [P2]."}]})
        ids = [line.split("]")[0].strip("[") for line in prompt.splitlines() if line.startswith("[S")]
        out = []
        for sid, line in zip(ids, [l for l in prompt.splitlines() if l.startswith("[S")]):
            out.append({"id": sid, "verdict": "supported" if "individual" in line else "partial", "reason": "r"})
        return json.dumps({"verdicts": out})


def _result():
    report = {"answer": {"text": "Answer [P1].", "support": "partial", "claim_ids": ["c1"]},
              "sections": [{"index": 1, "sub_question": "Q1", "sentences": [
                  {"type": "assertive", "text": "Team satisfaction rose [P1].", "claim_ids": ["c1"], "support": "partial"},
                  {"type": "assertive", "text": "Stress rose [P2].", "claim_ids": ["c2"]}]}],
              "tensions": [], "gaps": [],
              "implications": [{"type": "implication", "text": "Leaders must cut stress [P2].", "claim_ids": ["c2"], "support": "partial"}]}
    return {"report": report, "check_d": {"checked": 4, "supported": 1, "partial": 3, "unsupported": 0, "items": [], "removed": []},
            "publish_res": {"status": "PUBLISH_READY", "allowed": True, "reasons": []}, "status": "PUBLISH_READY"}


def test_repair_once_then_remove():
    from src.engine.check_d_support import repair_partials
    from src.score.checker import GateChecker

    res = _result()
    repair_partials(res, CLAIMS, LANES, Repairer(), GateChecker())
    sec = res["report"]["sections"][0]["sentences"]
    assert sec[0]["text"] == "One study reports individual job satisfaction rose [P1]." and sec[0]["support"] == "repaired"
    assert res["report"]["implications"] == [], "still partial after one rewrite: removed"
    removed = [r["text"] for r in res["check_d"]["removed"]]
    assert "Leaders must cut stress [P2]." in removed
    assert res["report"]["answer"]["support"] == "partial", "the answer stays, marked"
    assert "demonstrably" not in json.dumps(res), "verbs are softened again by rule (or the rewrite is dropped)"
    assert res["check_d"]["in_brief"] == 3 and res["check_d"]["supported_in_brief"] == 2


def test_partial_takeaways_dropped():
    from src.engine.check_d_support import check_takeaways

    class J:
        def generate(self, prompt, system_prompt=None, temperature=0.0, json_mode=False):
            return '{"verdicts": [{"id": "S1", "verdict": "supported", "reason": "ok"}, {"id": "S2", "verdict": "partial", "reason": "adds"}]}'

    s = {"takeaways": [{"text": "A [P1].", "claim_ids": ["c1"]}, {"text": "B [P2].", "claim_ids": ["c2"]}], "dropped": []}
    out = check_takeaways(s, CLAIMS, LANES, J())
    assert [t["text"] for t in out["takeaways"]] == ["A [P1]."]


# ------------------------------------------------------------------------------
# Test 4: Rate of what is in the brief
# ------------------------------------------------------------------------------
def test_checks_tab_shows_brief_rate():
    web = Path("web_app.py").read_text(encoding="utf-8")
    tab = web[web.index("with tab_checks:"):]
    assert "supported_in_brief" in tab and "In the brief" in tab


# ------------------------------------------------------------------------------
# S28e: uncited "no evidence" sentences (live run job_5ab130593406 failed G1 on two of them)
# ------------------------------------------------------------------------------
def test_uncited_absence_sentences_dropped(tmp_path):
    from src.ledger.migrations import apply_migrations
    from src.ledger.models import Question, Run, Source
    from src.ledger.repository import LedgerRepository
    from src.synth.generator import SynthesisEngine, is_absence_statement

    assert is_absence_statement("The reviewed papers say nothing on defect escape rates.")
    assert is_absence_statement("No study in this set addresses test coverage.")
    assert not is_absence_statement("Teams reported fewer defects.")

    db = str(tmp_path / "l.db")
    apply_migrations(db_path=db)
    repo = LedgerRepository(db_path=db)
    repo.insert_question(Question(id="q", text="Does AI review cut defects?"))
    repo.insert_run(Run(id="r", question_ids=["q"]))
    repo.insert_source(Source(id="s1", lane="academic", source_type="preprint", title="s1"))
    c = Claim(id="c1", question_id="q", source_id="s1", text="The study reports that individual job satisfaction rose.",
              source_excerpt="individual job satisfaction rose", grade="moderate")
    repo.insert_claim(c)
    synth = {"executive_summary": "Satisfaction rose [P1].",
             "sections": [{"sub_question": "Defects?", "synthesis": [],
                           "evidence": ["The reviewed papers say nothing on defect escape rates."]},
                          {"sub_question": "Satisfaction?", "synthesis": [], "evidence": ["One study reports satisfaction rose [P1]."]}],
             "gaps": ["No study in this set addresses test coverage."]}
    _, sentences, summary = SynthesisEngine(db_path=db).build_field_note(
        question_id="q", run_id="r", executive_synthesis=synth, papers=[{"id": "s1"}], claims_override=[repo.get_claim("c1")])
    assert not any("say nothing" in s.text or "addresses test coverage" in s.text for s in sentences)
    g1 = (summary.get("gate_results") or {}).get("violations", {}).get("G1") or []
    assert not any("lacks citation" in v for v in g1)
