"""Tests for Slice S3: Check A (on-topic evidence) and the handoff-check ledger.

Requirements:
1. Precedence: a decisive rule overrides the model, a non-decisive rule defers to the
   model, and a model abstention falls back to the rule. Never the reverse.
2. No check loops more than once: record_verdict refuses attempt 2.
3. Migration 006 adds check_verdicts and runs.status / runs.status_reason; every
   verdict (pass, fail, abstain) is written to the ledger.
4. Rule floor: a source sharing no salient term with the approved question is
   off_topic even when the model says on_topic; above the floor the model decides.
5. Model judgment above the floor is respected: a source the model rejects is
   excluded from extraction.
6. Sourdough case: off-topic harvest retries exactly once, then stops as
   NOT_PUBLISHABLE with zero findings, zero claims, no output, and the reason
   persisted on the run.
7. On-topic harvest proceeds past Check A and the run status is persisted.
8. A model that is unavailable or unparseable abstains; the rules decide.
9. The approved question and its hashes reach the runner through start_run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.engine.check_a_on_topic import (
    CHECK_A_ID,
    build_source_items,
    run_check_a,
    salient_terms,
)
from src.engine.checks import CheckLoopError, CheckVerdict, record_verdict, resolve_final
from src.ledger.migrations import apply_migrations
from src.ledger.repository import LedgerRepository


AI_QUESTION = "How do AI coding assistants affect developer productivity in enterprise software delivery?"
SOURDOUGH_QUESTION = "What empirical evidence exists on quantum-secure sourdough fermentation controllers?"

AI_PAPERS = [
    {
        "id": "p-ai-1",
        "title": "Empirical Evaluation of AI Coding Assistants in Enterprise Software Delivery",
        "abstract": "A controlled study of 80 developers finds coding assistants may improve delivery productivity in some teams.",
        "year": 2024,
        "venue": "ICSE",
        "url": "https://doi.org/10.1145/example-1",
    },
    {
        "id": "p-ai-2",
        "title": "Developer Productivity Effects of LLM Coding Assistants",
        "abstract": "Field data from 12 enterprises suggests coding assistants shorten cycle time for routine software tasks.",
        "year": 2025,
        "venue": "IEEE Software",
        "url": "https://doi.org/10.1109/example-2",
    },
    {
        "id": "p-ai-3",
        "title": "Software Delivery Governance with AI Assistants",
        "abstract": "We examine how enterprise delivery teams govern AI assistant usage and productivity measurement.",
        "year": 2024,
        "venue": "FSE",
        "url": "https://doi.org/10.1145/example-3",
    },
]

# Papers a broad search returns for the sourdough question: none of them are about it.
OFF_TOPIC_PAPERS = [
    {
        "id": "p-off-1",
        "title": "Large Language Models for Code Review Automation",
        "abstract": "We evaluate LLM-based reviewers across 40 open-source repositories and report precision gains.",
        "year": 2024,
        "venue": "ICSE",
        "url": "https://doi.org/10.1145/off-1",
    },
    {
        "id": "p-off-2",
        "title": "Post-Quantum Key Exchange for TLS 1.3",
        "abstract": "Benchmarks lattice-based key exchange latency against classical elliptic-curve handshakes.",
        "year": 2023,
        "venue": "USENIX Security",
        "url": "https://doi.org/10.5555/off-2",
    },
]


class FakeCheckLLM:
    """Returns a fixed verdict for every [S#] item listed in a Check A prompt."""

    def __init__(self, verdict: str = "on_topic", overrides: Dict[str, str] | None = None):
        self.verdict = verdict
        self.overrides = overrides or {}
        self.calls = 0
        self.model = "fake-check-model"

    def generate(self, prompt: str, system_prompt=None, temperature=0.0, json_mode=False) -> str:
        self.calls += 1
        items = []
        for sid, title in re.findall(r"\[(S\d+)\][^\n]*?title: ([^\n|]+)", prompt):
            verdict = self.verdict
            for needle, forced in self.overrides.items():
                if needle.lower() in title.lower():
                    verdict = forced
            items.append({"id": sid, "verdict": verdict, "reason": f"fake judged {verdict}"})
        return json.dumps({"verdicts": items})


class BrokenLLM:
    model = "broken-model"

    def generate(self, *args, **kwargs) -> str:
        raise ConnectionError("model offline")


def _runner(tmp_path: Path, llm: Any) -> MultiLaneResearchRunner:
    db = str(tmp_path / "ledger.db")
    prac = str(tmp_path / "prac.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    runner = MultiLaneResearchRunner(
        db_path=db,
        practitioner_db_path=prac,
        questions_yaml_path=str(tmp_path / "register.yaml"),
    )
    runner._build_check_llm = lambda provider: llm  # type: ignore[assignment]
    runner._harvest_enterprise_lane = lambda **kwargs: []  # type: ignore[assignment]
    runner.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1}
    return runner


# ------------------------------------------------------------------------------
# Test 1: Rules override the model, never the reverse
# ------------------------------------------------------------------------------
def test_precedence_rules_override_model_never_reverse():
    assert resolve_final(model_verdict="on_topic", rule_verdict="off_topic", rule_decisive=True) == "off_topic"
    assert resolve_final(model_verdict="off_topic", rule_verdict="on_topic", rule_decisive=False) == "off_topic"
    assert resolve_final(model_verdict="abstain", rule_verdict="on_topic", rule_decisive=False) == "on_topic"
    assert resolve_final(model_verdict=None, rule_verdict="fail", rule_decisive=False) == "fail"


# ------------------------------------------------------------------------------
# Test 2: Nothing loops more than once
# ------------------------------------------------------------------------------
def test_record_verdict_refuses_second_retry(tmp_path):
    db = str(tmp_path / "ledger.db")
    apply_migrations(db_path=db)
    repo = LedgerRepository(db_path=db)
    v = CheckVerdict(
        check_id=CHECK_A_ID, run_id="run_x", object_type="run", object_id="run_x",
        model_verdict=None, rule_verdict="fail", rule_decisive=True,
        reason_plain="too thin", attempt=2,
    )
    with pytest.raises(CheckLoopError):
        record_verdict(repo, v)


# ------------------------------------------------------------------------------
# Test 3: Migration 006 schema and verdict persistence
# ------------------------------------------------------------------------------
def test_migration_006_adds_verdict_table_and_run_status(tmp_path):
    db = str(tmp_path / "ledger.db")
    version = apply_migrations(db_path=db)
    assert version >= 6
    repo = LedgerRepository(db_path=db)
    with repo._conn() as conn:
        run_cols = {r[1] for r in conn.execute("PRAGMA table_info(runs);").fetchall()}
        verdict_cols = {r[1] for r in conn.execute("PRAGMA table_info(check_verdicts);").fetchall()}
    assert {"status", "status_reason"} <= run_cols
    assert {"check_id", "run_id", "model_verdict", "rule_verdict", "rule_decisive", "final", "reason_plain", "attempt"} <= verdict_cols

    from src.ledger.models import Run

    repo.insert_run(Run(id="run_y", question_ids=[]))
    repo.set_run_status("run_y", "blocked", "reason kept")
    repo.insert_run(Run(id="run_y", question_ids=[], config_json={"k": 1}))
    assert repo.get_run_status("run_y") == ("BLOCKED", "reason kept"), "re-inserting a run must not wipe its status"

    v = CheckVerdict(
        check_id=CHECK_A_ID, run_id="run_y", object_type="source", object_id="p-1",
        model_verdict="abstain", rule_verdict="on_topic", rule_decisive=False,
        reason_plain="model abstained; rule floor passed", attempt=0,
    )
    record_verdict(repo, v)
    rows = repo.list_check_verdicts("run_y")
    assert len(rows) == 1
    assert rows[0]["final"] == "on_topic"
    assert rows[0]["model_verdict"] == "abstain"


# ------------------------------------------------------------------------------
# Test 4: Rule floor overrides a model "on_topic"
# ------------------------------------------------------------------------------
def test_rule_floor_overrides_model_on_topic():
    items = build_source_items(OFF_TOPIC_PAPERS, [], [])
    result = run_check_a(
        question=SOURDOUGH_QUESTION,
        items=items,
        llm=FakeCheckLLM(verdict="on_topic"),
        run_id="run_floor",
        attempt=0,
        min_on_topic_sources=1,
    )
    by_id = {v.object_id: v for v in result.verdicts if v.object_type == "source"}
    assert all(v.model_verdict == "on_topic" for v in by_id.values())
    # p-off-1 shares no key term: the rule overrides the model.
    assert by_id["p-off-1"].rule_decisive and by_id["p-off-1"].final == "off_topic"
    # p-off-2 shares "quantum": the rule is not decisive, so the model's verdict stands.
    assert not by_id["p-off-2"].rule_decisive and by_id["p-off-2"].final == "on_topic"
    assert "sourdough" in salient_terms(SOURDOUGH_QUESTION)

    strict = run_check_a(
        question=SOURDOUGH_QUESTION, items=items, llm=FakeCheckLLM(verdict="off_topic"),
        run_id="run_floor2", attempt=0, min_on_topic_sources=1,
    )
    assert strict.passed is False and strict.on_topic_ids == set()


# ------------------------------------------------------------------------------
# Test 5: Model rejection above the floor is respected downstream
# ------------------------------------------------------------------------------
def test_model_rejection_above_floor_excludes_source(tmp_path):
    llm = FakeCheckLLM(verdict="on_topic", overrides={"Governance": "off_topic"})
    runner = _runner(tmp_path, llm)
    res = runner.run_workflow(
        topic=AI_QUESTION, depth="Fast", tone="Executive",
        map_provider="stub", reduce_provider="stub",
        academic_papers_override=AI_PAPERS,
    )
    titles = {p["title"] for p in res["papers"]}
    assert "Software Delivery Governance with AI Assistants" not in titles
    assert len(titles) == 2
    assert res.get("stopped_at") is None


# ------------------------------------------------------------------------------
# Test 6: Sourdough stops as NOT_PUBLISHABLE after exactly one retry
# ------------------------------------------------------------------------------
def test_sourdough_retries_once_then_not_publishable(tmp_path):
    llm = FakeCheckLLM(verdict="off_topic")
    runner = _runner(tmp_path, llm)
    harvest_calls: List[Dict[str, Any]] = []
    real_harvest = runner._harvest_academic_lane

    def spy(**kwargs):
        harvest_calls.append(kwargs)
        return real_harvest(**kwargs)

    runner._harvest_academic_lane = spy  # type: ignore[assignment]
    res = runner.run_workflow(
        topic=SOURDOUGH_QUESTION, depth="Fast", tone="Executive",
        map_provider="stub", reduce_provider="stub",
        academic_papers_override=OFF_TOPIC_PAPERS,
    )

    assert len(harvest_calls) == 2, "Check A must retry the harvest exactly once"
    assert harvest_calls[1]["query_limit"] > harvest_calls[0]["query_limit"]
    assert res["status"] == "NOT_PUBLISHABLE"
    assert res["publish_res"]["status"] == "NOT_PUBLISHABLE"
    assert res["stopped_at"] == "check_a"
    assert res["findings"] == [] and res["claims"] == []
    # Only rule-built "searched, nothing found" statements; nothing is drafted.
    assert all(t["type"] == "negative_finding" and t["claims"] == [] for t in res["sentence_traces"])
    assert res["doc_id"] is None
    assert "on-topic" in res["stop_reason"].lower()

    repo = LedgerRepository(db_path=runner.db_path)
    status, reason = repo.get_run_status(res["run_id"])
    assert status == "NOT_PUBLISHABLE"
    assert reason == res["stop_reason"]
    live_claims = [c for c in repo.list_claims(question_id=res["question_id"]) if c.status != "rejected"]
    assert live_claims == []
    with repo._conn() as conn:
        n_outputs = conn.execute("SELECT COUNT(*) FROM outputs;").fetchone()[0]
    assert n_outputs == 0

    verdicts = repo.list_check_verdicts(res["run_id"])
    run_level = [v for v in verdicts if v["object_type"] == "run"]
    assert [v["attempt"] for v in run_level] == [0, 1]
    assert all(v["final"] == "fail" for v in run_level)
    # The harvest keyword filter may already drop these papers; anything Check A saw is off-topic.
    assert all(v["final"] == "off_topic" for v in verdicts if v["object_type"] == "source")


# ------------------------------------------------------------------------------
# Test 7: On-topic run proceeds and persists its status
# ------------------------------------------------------------------------------
def test_on_topic_run_passes_check_a_and_persists_status(tmp_path):
    runner = _runner(tmp_path, FakeCheckLLM(verdict="on_topic"))
    res = runner.run_workflow(
        topic=AI_QUESTION, depth="Fast", tone="Executive",
        map_provider="stub", reduce_provider="stub",
        academic_papers_override=AI_PAPERS,
    )
    assert res.get("stopped_at") is None
    assert len(res["papers"]) == 3
    repo = LedgerRepository(db_path=runner.db_path)
    status, _ = repo.get_run_status(res["run_id"])
    assert status == res["status"]
    run_level = [v for v in repo.list_check_verdicts(res["run_id"], check_id=CHECK_A_ID) if v["object_type"] == "run"]
    assert [v["final"] for v in run_level] == ["pass"]


# ------------------------------------------------------------------------------
# Test 8: Unavailable model abstains and rules decide
# ------------------------------------------------------------------------------
def test_unavailable_model_abstains_rules_decide():
    items = build_source_items(AI_PAPERS, [], [])
    result = run_check_a(
        question=AI_QUESTION, items=items, llm=BrokenLLM(),
        run_id="run_offline", attempt=0, min_on_topic_sources=2,
    )
    per_source = [v for v in result.verdicts if v.object_type == "source"]
    assert all(v.model_verdict == "abstain" for v in per_source)
    assert all(v.final == "on_topic" for v in per_source)
    assert result.passed is True

    # Synonyms count toward the floor (kiro -> spec-driven).
    kiro_items = build_source_items([{
        "id": "p-sdd", "title": "Spec-driven development in practice",
        "abstract": "We study spec-driven development workflows in 9 teams.",
    }], [], [])
    kiro = run_check_a(
        question="What is known about Kiro adoption?", items=kiro_items, llm=None,
        run_id="run_syn", attempt=0, synonyms={"kiro": ["spec-driven development"]},
    )
    assert kiro.passed is True

    from src.llm.stub_client import StubLLM
    stub_result = run_check_a(
        question=AI_QUESTION, items=items, llm=StubLLM(),
        run_id="run_stub", attempt=0, min_on_topic_sources=2,
    )
    assert all(v.model_verdict == "abstain" for v in stub_result.verdicts if v.object_type == "source")


# ------------------------------------------------------------------------------
# Test 9: Approved question and hashes reach the runner
# ------------------------------------------------------------------------------
def test_approved_question_threads_through_start_run(tmp_path, monkeypatch):
    import inspect

    from src.engine.approvals import get_latest_gate1_approval, save_gate1_approval
    from src.engine.entry import _filter_runner_args, start_run

    sig = inspect.signature(MultiLaneResearchRunner.run_workflow)
    assert "approved_question" in sig.parameters and "approval_ref" in sig.parameters

    approvals_dir = tmp_path / "approvals"
    package = {
        "refined_question": AI_QUESTION,
        "sub_questions": ["How does cycle time change?"],
        "scope": {"include": ["enterprise software teams"], "exclude": []},
        "added_terms": [],
    }
    save_gate1_approval(
        question_id="q-s3-thread",
        raw_user_text=AI_QUESTION,
        proposals=[package],
        final_package=package,
        provider="stub",
        model_name="stub",
        approvals_dir=approvals_dir,
    )

    captured: Dict[str, Any] = {}

    def mock_runner(**kwargs):
        captured.update(kwargs)
        return {"status": "DRAFT"}

    start_run("q-s3-thread", AI_QUESTION, runner=mock_runner, approvals_dir=approvals_dir, reasoned_package=package)
    approval = get_latest_gate1_approval("q-s3-thread", approvals_dir=approvals_dir)
    assert captured["approved_question"] == AI_QUESTION
    assert captured["approval_ref"]["question_sha256"] == approval.question_sha256
    assert captured["approval_ref"]["version"] == approval.version

    kept = _filter_runner_args(MultiLaneResearchRunner(db_path=str(tmp_path / "l.db")).run_workflow, captured)
    assert "approved_question" in kept and "approval_ref" in kept
