"""Tests for Slice S4: run-scoped evidence, Check B (well-formed claims) and the evidence board.

Requirements:
1. Check B passes when there are enough well-formed claims from enough sources.
2. Too few claims, or too few distinct sources, gives BLOCKED with a plain-words reason
   that states what was found and what is needed.
3. A malformed claim (no source, empty text, missing or over-25-word excerpt, unknown
   grade) is set aside with its reason and does not count.
4. Check B is rules only: deterministic for the same input and never builds or calls a model.
5. A run only sees its own claims: a second run on the same question does not inherit
   the first run's claims in the payload, gap matrix or draft.
6. Check B failing in a run stops it as BLOCKED before drafting; the claims are still
   returned so the evidence board can show them; runs.status and verdict rows persist.
7. Operator exclusions (by content key) remove claims from the draft, are listed as
   excluded, are logged to reviews, and can push the run into BLOCKED.
8. A re-draft runs the approved refined question, not the raw Step 1 input text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.engine.check_b_wellformed import CHECK_B_ID, claim_content_key, run_check_b
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, Source
from src.ledger.repository import LedgerRepository


QUESTION = "How do AI coding assistants affect developer productivity in enterprise software delivery?"


def _paper(pid: str, title: str, abstract: str) -> Dict[str, Any]:
    return {"id": pid, "title": title, "abstract": abstract, "year": 2024, "venue": "ICSE", "url": f"https://doi.org/{pid}"}


PAPERS_RUN1 = [
    _paper("p-r1-a", "AI Coding Assistants and Developer Productivity in Enterprise Teams",
           "A controlled study of 80 enterprise developers finds AI coding assistants reduce task time by 21%."),
    _paper("p-r1-b", "Enterprise Software Delivery with LLM Coding Assistants",
           "Across 12 enterprises, coding assistants shortened software delivery cycle time by 14%."),
]
PAPERS_RUN2 = [
    _paper("p-r2-a", "Developer Experience with AI Coding Assistants at Scale",
           "Survey of 1,200 enterprise software developers reports AI coding assistants improve perceived productivity."),
    _paper("p-r2-b", "Code Quality Effects of AI Coding Assistants in Enterprise Software",
           "Analysis of 300 enterprise repositories finds AI coding assistants increase review rework by 9%."),
]


def _claim(cid: str, source_id: str, text: str = "Assistants reduce task time.", excerpt: str = "reduce task time by 21%",
           grade: str = "moderate") -> Claim:
    return Claim(id=cid, question_id="q", source_id=source_id, text=text, source_excerpt=excerpt, grade=grade)


def _sources(*ids: str) -> Dict[str, Source]:
    return {
        sid: Source(id=sid, lane="academic", source_type="peer_reviewed", org="ICSE", title=f"Paper {sid}")
        for sid in ids
    }


class OnTopicLLM:
    model = "fake-on-topic"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str, **kwargs) -> str:
        import json
        import re

        self.calls += 1
        ids = re.findall(r"\[(S\d+)\]", prompt)
        return json.dumps({"verdicts": [{"id": i, "verdict": "on_topic", "reason": "fake"} for i in ids]})


def _runner(tmp_path: Path, **check_b: Any) -> MultiLaneResearchRunner:
    db = str(tmp_path / "ledger.db")
    prac = str(tmp_path / "prac.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    runner = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    runner._build_check_llm = lambda provider: OnTopicLLM()  # type: ignore[assignment]
    runner._harvest_enterprise_lane = lambda **kwargs: []  # type: ignore[assignment]
    runner.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1, **check_b}
    return runner


def _run(runner: MultiLaneResearchRunner, papers: List[Dict[str, Any]], **kwargs: Any) -> Dict[str, Any]:
    return runner.run_workflow(
        topic=QUESTION, depth="Fast", tone="Executive", map_provider="stub", reduce_provider="stub",
        academic_papers_override=papers, **kwargs,
    )


# ------------------------------------------------------------------------------
# Test 1: Enough well-formed claims from enough sources passes
# ------------------------------------------------------------------------------
def test_check_b_passes_with_enough_claims_and_sources():
    claims = [_claim("c1", "s1"), _claim("c2", "s2"), _claim("c3", "s2")]
    result = run_check_b(claims, _sources("s1", "s2"), run_id="r", min_claims=3, min_sources=2)
    assert result.passed is True
    assert [c.id for c in result.wellformed] == ["c1", "c2", "c3"]
    run_rows = [v for v in result.verdicts if v.object_type == "run"]
    assert len(run_rows) == 1 and run_rows[0].final == "pass" and run_rows[0].check_id == CHECK_B_ID


# ------------------------------------------------------------------------------
# Test 2: Too few claims or sources is BLOCKED with a plain-words reason
# ------------------------------------------------------------------------------
def test_check_b_blocks_with_plain_reason():
    few = run_check_b([_claim("c1", "s1"), _claim("c2", "s1")], _sources("s1"), run_id="r", min_claims=5, min_sources=3)
    assert few.passed is False
    assert few.reason_plain == "Only 2 usable claims from 1 source; at least 5 claims from 3 sources are needed."

    one_source = run_check_b([_claim(f"c{i}", "s1") for i in range(5)], _sources("s1"), run_id="r", min_claims=5, min_sources=2)
    assert one_source.passed is False
    assert "from 1 source" in one_source.reason_plain and "from 2 sources" in one_source.reason_plain


# ------------------------------------------------------------------------------
# Test 3: Malformed claims are set aside with a reason
# ------------------------------------------------------------------------------
def test_malformed_claims_set_aside_with_reason():
    long_excerpt = " ".join(["word"] * 30)
    claims = [
        _claim("ok", "s1"),
        _claim("no-source", "missing"),
        _claim("empty", "s1", text="  "),
        _claim("long", "s1", excerpt=long_excerpt),
        _claim("no-excerpt", "s1", excerpt=""),
    ]
    result = run_check_b(claims, _sources("s1"), run_id="r", min_claims=1, min_sources=1)
    assert [c.id for c in result.wellformed] == ["ok"]
    reasons = {v.object_id: v.reason_plain for v in result.verdicts if v.object_type == "claim"}
    assert reasons["no-source"] == "Set aside: its source is not in the ledger."
    assert reasons["empty"] == "Set aside: the claim text is empty."
    assert reasons["long"] == "Set aside: the source excerpt is longer than 25 words."
    assert reasons["no-excerpt"] == "Set aside: there is no source excerpt."
    assert "4 claims were set aside" in result.reason_plain


# ------------------------------------------------------------------------------
# Test 4: Rules only, deterministic, no model
# ------------------------------------------------------------------------------
def test_check_b_is_deterministic_and_never_uses_a_model(monkeypatch):
    def no_model(*args, **kwargs):
        raise AssertionError("Check B must not build a model")

    monkeypatch.setattr("src.llm.factory.build_llm", no_model)
    claims = [_claim("c1", "s1"), _claim("c2", "s2", excerpt="")]
    a = run_check_b(claims, _sources("s1", "s2"), run_id="r", min_claims=2, min_sources=2)
    b = run_check_b(claims, _sources("s1", "s2"), run_id="r", min_claims=2, min_sources=2)
    assert [(v.object_id, v.final, v.reason_plain) for v in a.verdicts] == [(v.object_id, v.final, v.reason_plain) for v in b.verdicts]
    assert all(v.model_verdict is None and v.rule_decisive for v in a.verdicts)


# ------------------------------------------------------------------------------
# Test 5: A run only sees its own claims
# ------------------------------------------------------------------------------
def test_second_run_does_not_inherit_first_runs_claims(tmp_path):
    runner = _runner(tmp_path)
    res1 = _run(runner, PAPERS_RUN1)
    res2 = _run(runner, PAPERS_RUN2)
    assert res1["question_id"] == res2["question_id"]
    run1_sources = {p["id"] for p in PAPERS_RUN1}
    run2_sources = {p["id"] for p in PAPERS_RUN2}
    assert res2["claims"], "run 2 should have its own claims"
    assert not ({c.get("source_id") for c in res2["claims"]} & run1_sources)
    cited_2 = {cid for s in res2["sentence_traces"] for cid in s["claims"]}
    run1_claim_ids = {c["id"] for c in res1["claims"]}
    assert not (cited_2 & run1_claim_ids), "run 2 draft cites run 1 claims"
    assert {c.get("source_id") for c in res2["claims"]} <= run2_sources


# ------------------------------------------------------------------------------
# Test 6: Check B failing in a run stops it as BLOCKED before drafting
# ------------------------------------------------------------------------------
def test_run_blocked_at_check_b_keeps_claims_for_the_board(tmp_path):
    runner = _runner(tmp_path, min_claims=50, min_sources=5)
    res = _run(runner, PAPERS_RUN1)
    assert res["status"] == "BLOCKED"
    assert res["stopped_at"] == "check_b"
    assert res["publish_res"]["status"] == "BLOCKED"
    assert res["doc_id"] is None and res["findings"] == []
    assert res["claims"], "the evidence board must still show the claims"
    assert res["stop_reason"].startswith("Stopped at Check B: Only ")
    assert res["check_b"]["passed"] is False

    repo = LedgerRepository(db_path=runner.db_path)
    assert repo.get_run_status(res["run_id"])[0] == "BLOCKED"
    with repo._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM outputs;").fetchone()[0] == 0
    rows = repo.list_check_verdicts(res["run_id"], check_id=CHECK_B_ID)
    assert [r["final"] for r in rows if r["object_type"] == "run"] == ["fail"]


# ------------------------------------------------------------------------------
# Test 7: Operator exclusions
# ------------------------------------------------------------------------------
def test_operator_exclusions_are_applied_logged_and_can_block(tmp_path):
    runner = _runner(tmp_path)
    first = _run(runner, PAPERS_RUN1)
    target = first["claims"][0]
    assert target["content_key"]

    second = _run(runner, PAPERS_RUN1, excluded_claim_keys=[target["content_key"]])
    kept_keys = {c["content_key"] for c in second["claims"]}
    assert target["content_key"] not in kept_keys
    assert target["content_key"] in {c["content_key"] for c in second["excluded_claims"]}
    cited = {cid for s in second["sentence_traces"] for cid in s["claims"]}
    assert not any(c["content_key"] == target["content_key"] and c["id"] in cited for c in second["excluded_claims"])

    repo = LedgerRepository(db_path=runner.db_path)
    with repo._conn() as conn:
        rows = conn.execute(
            "SELECT action, object_type, reason FROM reviews WHERE gate = 'evidence_board';"
        ).fetchall()
    assert any(r["action"] == "exclude" and r["object_type"] == "claim" for r in rows)

    all_keys = [c["content_key"] for c in first["claims"]]
    blocked = _run(runner, PAPERS_RUN1, excluded_claim_keys=all_keys)
    assert blocked["status"] == "BLOCKED" and blocked["stopped_at"] == "check_b"
    assert "excluded" in blocked["stop_reason"]
    assert claim_content_key(Claim(id="x", source_id="s", text=" A  b ", source_excerpt="e")) == claim_content_key(
        Claim(id="y", source_id="s", text="a b", source_excerpt="other")
    )


# ------------------------------------------------------------------------------
# Test 8: A re-draft runs the approved question, not the raw input text
# ------------------------------------------------------------------------------
def test_redraft_uses_approved_refined_question():
    from src.ui.intake_view import approved_question_text

    pkg = {"refined_question": "What measurable productivity impact do AI coding assistants have?"}
    assert approved_question_text(pkg, {"strategic_question": "raw typed text"}) == pkg["refined_question"]
    assert approved_question_text(None, {"strategic_question": "Question the run used"}) == "Question the run used"
