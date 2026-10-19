"""Tests for Slice S6: no data counts as FAIL, and only a human publishes.

Requirements:
1. Every gate reports PASS, FAIL or NO_DATA; NO_DATA is not a pass and shows as pass=False.
2. A draft with no grounded sentences is not passed (the old "zero sentences passes everything").
3. G5 is NO_DATA when the denylist file is missing; an empty but present file is checked.
4. Signals and risks must cite evidence (G1); roadmap actions are exempt from G1-G4.
5. G3 cannot pass without a question to check topic fit against.
6. The scorer gives no credit for missing data (freshness, contradictions, reproducibility).
7. No gate or status default anywhere reads missing as PASS.
8. A run never publishes itself; its status is one of the four gated statuses.
9. Publishing needs a named reviewer; REVISE also needs a reason; BLOCKED and NOT_PUBLISHABLE are refused.
10. A publish writes runs.status = PUBLISHED and a reviews row with the reviewer and reason.
11. The publish step's eligibility (enabled, needs a reason, why not) comes from one helper.
12. Gate rows show the verdict and reason before the description; a gate missing from the audit is NO DATA.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, OutputDoc, OutputSentence, Question, Run, Source
from src.ledger.repository import LedgerRepository
from src.score.checker import FAIL, NO_DATA, PASS, GateChecker
from src.score.scorer import QualityScorer
from src.ui.publish_view import gate_rows, gates_summary, publish_eligibility

QUESTION = Question(id="q-s6", text="How do AI coding assistants affect enterprise software delivery cycle time?")
SOURCE = Source(id="src-1", lane="academic", source_type="peer_reviewed", org="ICSE",
                title="AI coding assistants and enterprise software delivery cycle time", url="https://doi.org/x")
CLAIM = Claim(id="c_src-1_1", question_id="q-s6", source_id="src-1",
              text="The study reports that coding assistants shortened delivery cycle time by 14%.",
              source_excerpt="coding assistants shortened enterprise delivery cycle time by 14% (Location: Abstract)",
              grade="strong", claim_date="2024")


def _sentence(i: int, text: str, type_: str = "assertive", claims: List[str] | None = None) -> OutputSentence:
    return OutputSentence(id=f"out_{i}", output_id="out", ordinal=i, text=text, type=type_, claim_ids_json=claims)


GOOD = _sentence(1, "Coding assistants shortened enterprise delivery cycle time by 14% [P1].", claims=[CLAIM.id])


def _check(sentences, question=QUESTION, checker=None):
    return (checker or GateChecker()).check_output(
        sentences=sentences, ledger_claims={CLAIM.id: CLAIM}, source_texts={SOURCE.id: SOURCE.title},
        sources={SOURCE.id: SOURCE}, question=question, papers=[{"id": "src-1"}],
    )


# ------------------------------------------------------------------------------
# Test 1: Three states; NO_DATA is not a pass
# ------------------------------------------------------------------------------
def test_gate_states_and_no_data_not_pass():
    res = _check([])
    states = res.states()
    assert set(states) == {"G1", "G2", "G3", "G4", "G5", "G6"}
    assert all(s == NO_DATA for s in states.values()), states
    assert res.passed is False
    d = res.to_dict()
    assert d["passed"] is False
    assert all(g["pass"] is False and g["state"] == NO_DATA and g["reason_plain"] for g in d["hard_gates"].values())

    ok = _check([GOOD])
    assert ok.states() == {g: PASS for g in ("G1", "G2", "G3", "G4", "G5", "G6")}, ok.to_dict()["hard_gates"]
    assert ok.passed is True


# ------------------------------------------------------------------------------
# Test 2: Headings only is not passed
# ------------------------------------------------------------------------------
def test_no_grounded_sentences_is_not_passed():
    res = _check([_sentence(1, "What the Evidence Supports", "heading")])
    assert res.passed is False
    assert res.states()["G1"] == NO_DATA
    assert "No grounded sentences" in res.to_dict()["hard_gates"]["G1"]["reason_plain"]


# ------------------------------------------------------------------------------
# Test 3: Denylist missing vs empty
# ------------------------------------------------------------------------------
def test_denylist_missing_is_no_data_empty_is_checked(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_DENYLIST", str(tmp_path / "absent.txt"))
    res = _check([GOOD], checker=GateChecker())
    assert res.states()["G5"] == NO_DATA
    assert "denylist.txt" in res.to_dict()["hard_gates"]["G5"]["reason_plain"]

    empty = tmp_path / "denylist.txt"
    empty.write_text("# no names yet\n", encoding="utf-8")
    monkeypatch.setenv("RESEARCH_DENYLIST", str(empty))
    assert _check([GOOD], checker=GateChecker()).states()["G5"] == PASS

    empty.write_text("Acme Bank\n", encoding="utf-8")
    leak = _sentence(2, "Acme Bank shortened delivery cycle time by 14% [P1].", claims=[CLAIM.id])
    assert _check([GOOD, leak], checker=GateChecker()).states()["G5"] == FAIL


# ------------------------------------------------------------------------------
# Test 4: Signals and risks must cite; roadmap is exempt
# ------------------------------------------------------------------------------
def test_signals_and_risks_need_citations_roadmap_exempt():
    for t in ("signal", "risk"):
        res = _check([GOOD, _sentence(2, f"An uncited {t} about delivery.", t, claims=[])])
        assert res.states()["G1"] == FAIL, t
    road = _check([GOOD, _sentence(2, "Phase 1: Pilot assistants with two teams.", "roadmap", claims=[])])
    assert road.states()["G1"] == PASS


# ------------------------------------------------------------------------------
# Test 5: G3 needs a question
# ------------------------------------------------------------------------------
def test_g3_needs_question():
    res = _check([GOOD], question=None)
    assert res.states()["G3"] == NO_DATA
    assert res.passed is False


# ------------------------------------------------------------------------------
# Test 6: Scorer gives no credit for missing data
# ------------------------------------------------------------------------------
def test_scorer_no_credit_for_missing_data():
    scorer = QualityScorer()
    assert scorer.compute_reproducibility([], {}) is None
    score = scorer.calculate_score(
        gate_result=_check([]), sentences=[], ledger_claims={}, sources={}, questions=[QUESTION],
        cached_papers=[],
    )
    assert score["components"]["S5_freshness_scope"] == 0.0
    assert score["components"]["S7_reproducibility"] == "not measured"
    assert score["total_score"] <= 10, score


# ------------------------------------------------------------------------------
# Test 7: No missing-as-PASS defaults
# ------------------------------------------------------------------------------
def test_no_pass_defaults_anywhere():
    offenders = []
    files = list(Path("src").rglob("*.py")) + [Path("web_app.py")]
    pattern = re.compile(r"""\.get\(\s*["'](pass|passed)["']\s*,\s*True\s*\)""")
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{f}:{n}")
    assert offenders == []
    src = Path("web_app.py").read_text(encoding="utf-8")
    assert "ZERO UNGROUNDED CLAIMS" not in src
    assert "total_score', 88" not in Path("src/analysis/multilane_runner.py").read_text(encoding="utf-8")


# ------------------------------------------------------------------------------
# Test 8: A run never publishes itself
# ------------------------------------------------------------------------------
def test_run_never_publishes_itself(tmp_path):
    from src.analysis.multilane_runner import MultiLaneResearchRunner

    db, prac = str(tmp_path / "l.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    r = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    r._harvest_enterprise_lane = lambda **kwargs: []
    r.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1}
    called = {"n": 0}
    real = r.publisher.publish_output

    def spy(*a, **k):
        called["n"] += 1
        return real(*a, **k)

    r.publisher.publish_output = spy
    res = r.run_workflow(topic=QUESTION.text, map_provider="stub", reduce_provider="stub", academic_papers_override=[{
        "id": "src-1", "title": SOURCE.title, "abstract": "Coding assistants shortened enterprise delivery cycle time by 14%.",
        "year": 2024, "venue": "ICSE", "url": "https://doi.org/x",
    }])
    assert called["n"] == 0
    assert res["publish_res"]["published"] is False
    assert res["status"] in ("PUBLISH_READY", "REVISE", "BLOCKED", "NOT_PUBLISHABLE")
    repo = LedgerRepository(db_path=db)
    assert repo.get_run_status(res["run_id"])[0] == res["status"]
    with repo._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM outputs WHERE status='published';").fetchone()[0] == 0


# ------------------------------------------------------------------------------
# Tests 9-10: Human publishing rules and records
# ------------------------------------------------------------------------------
def _ledger_with_output(tmp_path: Path, band: str) -> LedgerRepository:
    db = str(tmp_path / f"pub_{band}.db")
    apply_migrations(db_path=db)
    repo = LedgerRepository(db_path=db)
    repo.insert_question(QUESTION)
    repo.insert_source(SOURCE)
    repo.insert_claim(CLAIM)
    repo.insert_run(Run(id="run_pub", question_ids=[QUESTION.id]))
    repo.set_run_status("run_pub", band)
    repo.insert_output(OutputDoc(id="out", run_id="run_pub", kind="field_note", status="draft",
                                 score_json={"band": band, "total_score": 90 if band == "PUBLISH_READY" else 75}))
    repo.insert_output_sentence(GOOD)
    return repo


def _publisher(repo: LedgerRepository, tmp_path: Path):
    from src.publish.publisher import Publisher

    return Publisher(db_path=repo.db_path, export_dir=str(tmp_path / "json"))


def test_publish_rules(tmp_path):
    repo = _ledger_with_output(tmp_path, "PUBLISH_READY")
    pub = _publisher(repo, tmp_path)
    ok, res = pub.publish_output("out", reviewer="", signoff_reason="Checked.")
    assert not ok and "reviewer" in res["reason"].lower()

    revise = _ledger_with_output(tmp_path, "REVISE")
    pub_r = _publisher(revise, tmp_path)
    ok, res = pub_r.publish_output("out", reviewer="G. M.", signoff_reason="", force_publish_non_band=True)
    assert not ok and "reason" in res["reason"].lower()

    low = _ledger_with_output(tmp_path, "NOT_PUBLISHABLE")
    ok, res = _publisher(low, tmp_path).publish_output("out", reviewer="G. M.", signoff_reason="Ship it.", force_publish_non_band=True)
    assert not ok and res["status"] == "NOT_PUBLISHABLE"


def test_publish_records_status_and_review(tmp_path):
    repo = _ledger_with_output(tmp_path, "REVISE")
    ok, res = _publisher(repo, tmp_path).publish_output(
        "out", reviewer="G. M.", signoff_reason="Reviewed every citation; band REVISE accepted.", force_publish_non_band=True,
    )
    assert ok, res
    assert repo.get_run_status("run_pub")[0] == "PUBLISHED"
    with repo._conn() as conn:
        row = conn.execute("SELECT reviewer, reason, after_json FROM reviews WHERE action='publish';").fetchone()
    assert row["reviewer"] == "G. M." and "REVISE accepted" in row["reason"]
    assert '"band": "REVISE"' in row["after_json"]


# ------------------------------------------------------------------------------
# Test 11: Publish eligibility helper
# ------------------------------------------------------------------------------
def test_publish_eligibility():
    assert publish_eligibility({"status": "PUBLISH_READY", "doc_id": "o"}) == (True, False, "")
    assert publish_eligibility({"status": "REVISE", "doc_id": "o"})[:2] == (True, True)
    for status in ("BLOCKED", "NOT_PUBLISHABLE", "PUBLISHED"):
        eligible, _, why = publish_eligibility({"status": status, "doc_id": "o"})
        assert not eligible and why
    assert publish_eligibility({"status": "PUBLISH_READY", "doc_id": None})[0] is False
    assert publish_eligibility({"status": "PUBLISH_READY", "doc_id": "o", "is_stub_mode": True})[0] is False
    src = Path("web_app.py").read_text(encoding="utf-8")
    assert "publish_eligibility(results)" in src


# ------------------------------------------------------------------------------
# Test 12: Gate rows lead with the verdict
# ------------------------------------------------------------------------------
def test_gate_rows_verdict_first():
    res = GateChecker().check_output(sentences=[], ledger_claims={})
    rows = gate_rows(res.to_dict())
    assert list(rows[0].keys()) == ["Gate", "Result", "Why", "What it checks"]
    assert all(r["Result"].startswith("NO DATA") and r["Why"] and r["Why"] != "Not audited for this run." for r in rows)
    missing = gate_rows({})
    assert all(r["Result"].startswith("NO DATA") and r["Why"] == "Not audited for this run." for r in missing)
    assert gates_summary({}) == "0/6 GATES PASS"
