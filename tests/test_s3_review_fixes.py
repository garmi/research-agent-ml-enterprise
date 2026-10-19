"""Tests for the PR #2 review findings on Slice S3 (Check A).

Requirements (one per review finding):
1. Practitioner field-note text is never put in the Check A model prompt.
2. Malformed model verdict entries abstain instead of crashing the run.
3. A run that raises after registration is marked FAILED with the error, not left RUNNING.
4. Migration 006 does not label pre-existing runs RUNNING.
5. A stopped run's gap matrix uses this run's (empty) evidence, not earlier runs' claims.
6. Negative-finding statements are not repeated when the retry logs the same searches.
7. Claims Check A rejects carry a reviews row saying it was Check A, not an operator.
8. The retry only re-harvests the academic lane, the one that can be widened.
9. Verdicts are written in one batch, and a batch with attempt 2 writes nothing.
10. The check model is built once per run, even when Check A retries.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.engine.check_a_on_topic import CHECK_A_ID, build_source_items, run_check_a
from src.engine.checks import CheckLoopError, CheckVerdict, record_verdicts
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, Run, SearchLog
from src.ledger.repository import LedgerRepository
from src.synth.generator import search_log_negative_findings

AI_QUESTION = "How do AI coding assistants affect developer productivity in enterprise software delivery?"
SOURDOUGH = "What empirical evidence exists on quantum-secure sourdough fermentation controllers?"
AI_PAPER = {
    "id": "p-ai-1",
    "title": "Empirical Evaluation of AI Coding Assistants in Enterprise Software Delivery",
    "abstract": "A controlled study of 80 developers finds coding assistants may improve delivery productivity.",
    "year": 2024, "venue": "ICSE", "url": "https://doi.org/x",
}
OFF_PAPER = {
    "id": "p-off", "title": "Large Language Models for Code Review Automation",
    "abstract": "We evaluate LLM-based reviewers across 40 open-source repositories.", "year": 2024,
}


class RecordingLLM:
    model = "recorder"

    def __init__(self, verdict: str = "on_topic") -> None:
        self.prompts: List[str] = []
        self.verdict = verdict

    def generate(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        ids = re.findall(r"\[(S\d+)\]", prompt)
        return json.dumps({"verdicts": [{"id": i, "verdict": self.verdict, "reason": "r"} for i in ids]})


def _runner(tmp_path: Path) -> MultiLaneResearchRunner:
    db, prac = str(tmp_path / "l.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    return MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))


# ------------------------------------------------------------------------------
# Test 1: Practitioner text never reaches the check model
# ------------------------------------------------------------------------------
def test_practitioner_text_not_sent_to_check_model():
    prac = Claim(id="cp1", source_id="prac-src", text="Client X pilot cut review time for AI coding assistants",
                 source_excerpt="confidential delivery note about AI coding assistants")
    items = build_source_items([AI_PAPER], [], [prac])
    llm = RecordingLLM()
    result = run_check_a(AI_QUESTION, items, llm, run_id="r", attempt=0)
    sent = "\n".join(llm.prompts)
    assert "confidential delivery note" not in sent and "Client X" not in sent
    by_id = {v.object_id: v for v in result.verdicts if v.object_type == "source"}
    assert by_id["prac-src"].model_verdict == "abstain"
    assert by_id["prac-src"].final == "on_topic"  # rule floor decides: it shares key terms


# ------------------------------------------------------------------------------
# Test 2: Malformed verdict entries abstain
# ------------------------------------------------------------------------------
def test_malformed_verdict_entries_abstain():
    class Garbled:
        model = "garbled"

        def generate(self, prompt, **kwargs):
            return json.dumps({"verdicts": ["S1 on_topic", None, 7]})

    items = build_source_items([AI_PAPER], [], [])
    result = run_check_a(AI_QUESTION, items, Garbled(), run_id="r", attempt=0)
    assert [v.model_verdict for v in result.verdicts if v.object_type == "source"] == ["abstain"]


# ------------------------------------------------------------------------------
# Test 3: A crashing run is marked FAILED
# ------------------------------------------------------------------------------
def test_crashing_run_is_marked_failed(tmp_path, monkeypatch):
    runner = _runner(tmp_path)
    runner._harvest_enterprise_lane = lambda **kwargs: []
    runner._build_check_llm = lambda provider: RecordingLLM()

    def boom(*args, **kwargs):
        raise RuntimeError("synthesis exploded")

    monkeypatch.setattr(runner, "_generate_executive_deliverables", boom)
    with pytest.raises(RuntimeError):
        runner.run_workflow(topic=AI_QUESTION, map_provider="stub", reduce_provider="stub", academic_papers_override=[AI_PAPER])
    repo = LedgerRepository(db_path=runner.db_path)
    with repo._conn() as conn:
        rows = conn.execute("SELECT status, status_reason FROM runs;").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert "synthesis exploded" in rows[0]["status_reason"]


# ------------------------------------------------------------------------------
# Test 4: Migration 006 does not mark historical runs RUNNING
# ------------------------------------------------------------------------------
def test_migration_006_leaves_historical_runs_unknown(tmp_path):
    db = str(tmp_path / "old.db")
    from src.ledger.db import get_connection
    from src.ledger.migrations import list_migration_files

    conn = get_connection(db, verify_integrity=False)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (schema_version INTEGER PRIMARY KEY, created_at TEXT NOT NULL);")
    for version, path in list_migration_files():
        if version <= 5:
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO meta (schema_version, created_at) VALUES (?, 'x');", (version,))
    conn.execute("INSERT INTO runs (id, started_at, created_at) VALUES ('old_run', 'x', 'x');")
    conn.commit()
    conn.close()

    apply_migrations(db_path=db)
    status, reason = LedgerRepository(db_path=db).get_run_status("old_run")
    assert status == "UNKNOWN"
    assert "before run status" in (reason or "")
    repo = LedgerRepository(db_path=db)
    repo.insert_run(Run(id="new_run", question_ids=[]))
    assert repo.get_run_status("new_run")[0] == "RUNNING"


# ------------------------------------------------------------------------------
# Test 5: Stopped run's gap matrix ignores earlier runs' claims
# ------------------------------------------------------------------------------
def test_stopped_run_gap_matrix_ignores_earlier_claims(tmp_path):
    runner = _runner(tmp_path)
    runner._harvest_enterprise_lane = lambda **kwargs: []
    runner._build_check_llm = lambda provider: RecordingLLM()
    runner.config.setdefault("checks", {})["check_a"] = {"min_on_topic_sources": 1}
    first = runner.run_workflow(topic=AI_QUESTION, map_provider="stub", reduce_provider="stub", academic_papers_override=[AI_PAPER])
    assert first.get("stopped_at") is None
    runner._build_check_llm = lambda provider: RecordingLLM(verdict="off_topic")
    second = runner.run_workflow(topic=AI_QUESTION, map_provider="stub", reduce_provider="stub", academic_papers_override=[AI_PAPER])
    assert second["stopped_at"] == "check_a"
    assert second["gap_matrix"]["academic_state"] != "supported"


# ------------------------------------------------------------------------------
# Test 6: Negative findings are not repeated
# ------------------------------------------------------------------------------
def test_negative_findings_deduplicated():
    logs = [
        SearchLog(id=f"s{i}", run_id="r", question_id="q", lane="enterprise", query="q", source_api="dora",
                  result_count=0, status="not_implemented", executed_at="x")
        for i in range(2)
    ]
    out = search_log_negative_findings(logs)
    assert len(out) == 1
    assert out[0][1]["search_log_id"] == "s0"


# ------------------------------------------------------------------------------
# Test 7: Check A rejections are attributed in reviews
# ------------------------------------------------------------------------------
def test_check_a_rejections_are_attributed(tmp_path):
    runner = _runner(tmp_path)
    runner._build_check_llm = lambda provider: RecordingLLM(verdict="off_topic")
    runner._harvest_enterprise_lane = lambda **kwargs: []
    res = runner.run_workflow(topic=SOURDOUGH, map_provider="stub", reduce_provider="stub", academic_papers_override=[OFF_PAPER])
    repo = LedgerRepository(db_path=runner.db_path)
    runner.repo.insert_run(Run(id="r_manual", question_ids=[]))
    claim = Claim(id="c_ent_1", question_id=res["question_id"], source_id="aws-dev-blog", text="Vendor says X.", source_excerpt="x")
    from src.ledger.models import Source

    repo.insert_source(Source(id="aws-dev-blog", lane="enterprise", source_type="vendor_blog", org="AWS", title="AWS blog"))
    repo.insert_claim(claim)
    runner._safe_reject_claims(["c_ent_1"], run_id="r_manual", reason="Model judged off-topic.")
    with repo._conn() as conn:
        rows = conn.execute("SELECT gate, action, object_id, reason, reviewer FROM reviews WHERE object_id='c_ent_1';").fetchall()
    assert rows and rows[0]["gate"] == "check_a" and rows[0]["action"] == "reject"
    assert rows[0]["reviewer"] == "check_a"
    assert repo.get_claim("c_ent_1").status == "rejected"


# ------------------------------------------------------------------------------
# Test 8: Retry re-harvests only the academic lane
# ------------------------------------------------------------------------------
def test_retry_only_reharvests_academic_lane(tmp_path):
    runner = _runner(tmp_path)
    runner._build_check_llm = lambda provider: RecordingLLM(verdict="off_topic")
    calls = {"academic": 0, "enterprise": 0}
    real_academic = runner._harvest_academic_lane

    def academic(**kw):
        calls["academic"] += 1
        return real_academic(**kw)

    def enterprise(**kw):
        calls["enterprise"] += 1
        return []

    runner._harvest_academic_lane = academic
    runner._harvest_enterprise_lane = enterprise
    runner.run_workflow(topic=SOURDOUGH, map_provider="stub", reduce_provider="stub", academic_papers_override=[OFF_PAPER])
    assert calls == {"academic": 2, "enterprise": 1}


# ------------------------------------------------------------------------------
# Test 9: Verdicts are written in one batch, all or nothing
# ------------------------------------------------------------------------------
def test_record_verdicts_batches_and_is_atomic(tmp_path):
    db = str(tmp_path / "l.db")
    apply_migrations(db_path=db)
    repo = LedgerRepository(db_path=db)
    repo.insert_run(Run(id="rb", question_ids=[]))

    def v(i: int, attempt: int = 0) -> CheckVerdict:
        return CheckVerdict(CHECK_A_ID, "rb", "source", f"s{i}", "abstain", "on_topic", False, "x", attempt=attempt)

    with pytest.raises(CheckLoopError):
        record_verdicts(repo, [v(1), v(2, attempt=2)])
    assert repo.list_check_verdicts("rb") == []

    opened = {"n": 0}
    real_conn = repo._conn

    def counting_conn():
        opened["n"] += 1
        return real_conn()

    repo._conn = counting_conn
    record_verdicts(repo, [v(i) for i in range(5)])
    assert opened["n"] == 1
    repo._conn = real_conn
    assert len(repo.list_check_verdicts("rb")) == 5


# ------------------------------------------------------------------------------
# Test 10: The check model is built once per run
# ------------------------------------------------------------------------------
def test_check_model_built_once_per_run(tmp_path):
    runner = _runner(tmp_path)
    runner._harvest_enterprise_lane = lambda **kwargs: []
    built = {"n": 0}

    def build(provider):
        built["n"] += 1
        return RecordingLLM(verdict="off_topic")

    runner._make_check_llm = build
    runner.run_workflow(topic=SOURDOUGH, map_provider="stub", reduce_provider="stub", academic_papers_override=[OFF_PAPER])
    assert built["n"] == 1
