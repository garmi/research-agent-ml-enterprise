"""Tests for the PR #5 review findings on Slice S6 (gates and human publishing).

Requirements (one per review finding):
1. The publisher itself refuses a run that is BLOCKED, NOT_PUBLISHABLE, FAILED, RUNNING or already
   PUBLISHED, and never publishes the same draft twice.
2. A run blocked for unconfirmed practitioner notes shows G6 as FAIL in the gate table and is not passed.
4. Hosted demo runs end in a gated status (with publishing disabled), not 'DRAFT'.
5. A gate row from an audit that predates S6 explains itself instead of leaving Why empty.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.ledger.migrations import apply_migrations
from src.ledger.models import OutputDoc, Run
from src.ledger.repository import LedgerRepository
from src.score.checker import GateChecker
from src.ui.publish_view import gate_rows
from tests.test_s6_gates_and_publish import CLAIM, GOOD, QUESTION, SOURCE, _check


def _ledger(tmp_path: Path, run_status: str, band: str = "PUBLISH_READY") -> LedgerRepository:
    db = str(tmp_path / f"fix_{run_status}.db")
    apply_migrations(db_path=db)
    repo = LedgerRepository(db_path=db)
    repo.insert_question(QUESTION)
    repo.insert_source(SOURCE)
    repo.insert_claim(CLAIM)
    repo.insert_run(Run(id="run_fix", question_ids=[QUESTION.id]))
    repo.set_run_status("run_fix", run_status)
    repo.insert_output(OutputDoc(id="out", run_id="run_fix", kind="field_note", status="draft",
                                 score_json={"band": band, "total_score": 90}))
    repo.insert_output_sentence(GOOD)
    return repo


def _publish(repo: LedgerRepository, tmp_path: Path):
    from src.publish.publisher import Publisher

    return Publisher(db_path=repo.db_path, export_dir=str(tmp_path / "json")).publish_output(
        "out", reviewer="G. M.", signoff_reason="Checked every citation.", force_publish_non_band=True,
    )


# ------------------------------------------------------------------------------
# Test 1: The publisher enforces the run's status, and publishes once
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("run_status", ["BLOCKED", "NOT_PUBLISHABLE", "FAILED", "RUNNING", "PUBLISHED"])
def test_publisher_refuses_ungated_run_status(tmp_path, run_status):
    repo = _ledger(tmp_path, run_status)
    ok, res = _publish(repo, tmp_path)
    assert not ok and res["status"] == run_status and res["reason"]
    with repo._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM reviews WHERE action='publish';").fetchone()[0] == 0


def test_publisher_publishes_once(tmp_path):
    repo = _ledger(tmp_path, "PUBLISH_READY")
    ok, res = _publish(repo, tmp_path)
    assert ok, res
    ok2, res2 = _publish(repo, tmp_path)
    assert not ok2 and "already published" in res2["reason"].lower()
    with repo._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM reviews WHERE action='publish';").fetchone()[0] == 1


# ------------------------------------------------------------------------------
# Test 2: Unconfirmed practitioner notes fail G6 where the UI reads it
# ------------------------------------------------------------------------------
def test_practitioner_block_fails_g6_in_hard_gates():
    gate_results = _check([GOOD]).to_dict()
    assert gate_results["hard_gates"]["G6"]["state"] == "PASS"
    MultiLaneResearchRunner._fail_g6_practitioner(gate_results, "Gate 6: Practitioner abstraction not confirmed by operator.")
    g6 = gate_results["hard_gates"]["G6"]
    assert g6["pass"] is False and g6["state"] == "FAIL" and "Practitioner" in g6["reason_plain"]
    assert gate_results["passed"] is False and gate_results["gates"]["G6_copyright"]["pass"] is False
    rows = {r["Gate"][:2]: r for r in gate_rows(gate_results)}
    assert rows["G6"]["Result"] == "FAIL"
    src = Path("src/analysis/multilane_runner.py").read_text(encoding="utf-8")
    assert 'gate_results["G6"] = ' not in src


# ------------------------------------------------------------------------------
# Test 4: Hosted demo ends in a gated status
# ------------------------------------------------------------------------------
def test_hosted_demo_status_is_gated(monkeypatch):
    gate_results = GateChecker().check_output(sentences=[], ledger_claims={}).to_dict()
    res = MultiLaneResearchRunner._hosted_demo_status(gate_results, {"band": "PUBLISH_READY"})
    assert res["status"] == "BLOCKED" and res["allowed"] is False and res["published"] is False
    assert any("hosted demo" in r.lower() for r in res["reasons"])
    src = Path("src/analysis/multilane_runner.py").read_text(encoding="utf-8")
    assert '"status": "DRAFT"' not in src
    from src.ui.publish_view import publish_eligibility

    monkeypatch.setenv("HOSTED_DEMO", "1")
    eligible, _, why = publish_eligibility({"status": "PUBLISH_READY", "doc_id": "o"})
    assert not eligible and "hosted demo" in why.lower()


# ------------------------------------------------------------------------------
# Test 5: Pre-S6 gate rows explain themselves
# ------------------------------------------------------------------------------
def test_pre_s6_gate_rows_have_a_reason():
    rows = {r["Gate"][:2]: r for r in gate_rows({"hard_gates": {"G1": {"pass": False, "violations": []},
                                                                   "G2": {"pass": True, "violations": []}}})}
    assert rows["G1"]["Result"] == "FAIL" and "before" in rows["G1"]["Why"].lower()
    assert rows["G2"]["Result"] == "PASS" and rows["G2"]["Why"]
    assert rows["G3"]["Result"].startswith("NO DATA") and rows["G3"]["Why"] == "Not audited for this run."
