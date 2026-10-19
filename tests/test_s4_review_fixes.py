"""Tests for the PR #3 review findings on Slice S4 (Check B, evidence board).

Requirements (one per review finding):
1. The evidence-board editor is keyed per run, so one run's row edits never land on another's rows.
2. Re-runs keep the operator's practitioner abstraction choice and remote-synthesis setting.
3. Exported papers carry no full harvested record; the re-draft copy lives apart and is not exported.
4. Re-runs resolve the provider the same way the main run does (Gemini without a key falls back).
5. Two claims with identical text from one source get different exclusion keys.
6. A run stopped at Check B reports the enterprise sources and practitioner claims it shows.
7. Re-drafting with an unchanged exclusion does not log the exclusion again.
8. Excluded claims say whether the operator excluded them or Check B set them aside.
9. Source lookups are made once per source per run.
10. The Check A bake-off does not change process-wide settings (env vars, module prompt path).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.engine.check_b_wellformed import claim_content_keys
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, Source
from src.ledger.repository import LedgerRepository
from src.ui.rerun import board_editor_key, export_view, papers_for_rerun

QUESTION = "How do AI coding assistants affect developer productivity in enterprise software delivery?"
PAPERS = [
    {"id": "p-1", "title": "AI Coding Assistants and Developer Productivity in Enterprise Teams",
     "abstract": "A controlled study of 80 enterprise developers finds AI coding assistants reduce task time by 21%.",
     "year": 2024, "venue": "ICSE", "url": "https://doi.org/p-1"},
    {"id": "p-2", "title": "Enterprise Software Delivery with LLM Coding Assistants",
     "abstract": "Across 12 enterprises, coding assistants shortened software delivery cycle time by 14%.",
     "year": 2024, "venue": "FSE", "url": "https://doi.org/p-2"},
]


class OnTopic:
    model = "fake"

    def generate(self, prompt, **kwargs):
        import re

        return json.dumps({"verdicts": [{"id": i, "verdict": "on_topic", "reason": "r"} for i in re.findall(r"\[(S\d+)\]", prompt)]})


def _runner(tmp_path: Path, **check_b: Any) -> MultiLaneResearchRunner:
    db, prac = str(tmp_path / "l.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    r = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    r._build_check_llm = lambda provider: OnTopic()
    r._harvest_enterprise_lane = lambda **kwargs: []
    r.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1, **check_b}
    return r


def _run(r: MultiLaneResearchRunner, **kw: Any) -> Dict[str, Any]:
    return r.run_workflow(topic=QUESTION, map_provider="stub", reduce_provider="stub", academic_papers_override=PAPERS, **kw)


def _web_app() -> str:
    return Path("web_app.py").read_text(encoding="utf-8")


# ------------------------------------------------------------------------------
# Test 1: Board editor keyed per run
# ------------------------------------------------------------------------------
def test_board_editor_key_is_per_run():
    assert board_editor_key({"run_id": "run_a"}) != board_editor_key({"run_id": "run_b"})
    assert board_editor_key({"run_id": "run_a"}) == board_editor_key({"run_id": "run_a"})
    assert 'key=board_editor_key(results)' in _web_app()
    assert 'key="evidence_board_editor"' not in _web_app()


# ------------------------------------------------------------------------------
# Test 2: Re-runs keep the practitioner settings
# ------------------------------------------------------------------------------
def test_reruns_keep_practitioner_settings():
    src = _web_app()
    redraft = src[src.index("evidence_board_redraft"):]
    loop1 = src[src.index("Execute Feedback Loop"):src.index("evidence_board_redraft")]
    for block in (redraft, loop1):
        call = block[block.index("run_production_pipeline("):]
        call = call[:call.index(")\n")]
        assert "practitioner_abstraction_confirmed=prac_abs_confirmed" in call
        assert "allow_remote_practitioner_synthesis=allow_remote_prac_synth" in call


# ------------------------------------------------------------------------------
# Test 3: No full harvested records in exported papers
# ------------------------------------------------------------------------------
def test_papers_carry_no_raw_record_and_exports_skip_rerun_copy(tmp_path):
    res = _run(_runner(tmp_path))
    assert res["papers"] and all("raw" not in p for p in res["papers"])
    assert {p["id"] for p in res["harvested_papers"]} == {"p-1", "p-2"}
    view = export_view(res)
    assert "harvested_papers" not in view and view["papers"] == res["papers"]
    assert papers_for_rerun(res)[0]["abstract"].startswith("A controlled study")
    assert [p["id"] for p in papers_for_rerun(res, drop_keys={"P1"})] == ["p-2"]
    src = _web_app()
    assert '"raw"' not in src
    assert "json.dumps(syn_raw or export_view(results)" in src


# ------------------------------------------------------------------------------
# Test 4: Re-runs resolve the provider like the main run
# ------------------------------------------------------------------------------
def test_reruns_use_effective_provider():
    src = _web_app()
    assert src.count("map_provider=selected_provider") == 0
    assert src.count("map_provider=rerun_provider") == 2
    assert "rerun_provider = effective_provider(selected_provider" in src


# ------------------------------------------------------------------------------
# Test 5: Identical-text claims get distinct keys
# ------------------------------------------------------------------------------
def test_identical_text_claims_get_distinct_keys(tmp_path):
    a = Claim(id="c1", source_id="s", text="Same sentence.", source_excerpt="e")
    b = Claim(id="c2", source_id="s", text="Same  sentence.", source_excerpt="e")
    c = Claim(id="c3", source_id="other", text="Same sentence.", source_excerpt="e")
    keys = claim_content_keys([a, b, c])
    assert len(set(keys.values())) == 3
    assert claim_content_keys([a, b])["c1"] == keys["c1"], "keys are stable across runs"


# ------------------------------------------------------------------------------
# Test 6: Check B stop payload reports what it shows
# ------------------------------------------------------------------------------
def test_check_b_stop_reports_enterprise_sources(tmp_path):
    r = _runner(tmp_path, min_claims=99, min_sources=9)

    def ent(**kw):
        src = Source(id="dora-dev-survey", lane="enterprise", source_type="analyst_survey", org="DORA",
                     title="DORA report", url="https://dora.dev", commercial_stake="none")
        r._ephemeral_sources[src.id] = src
        r.repo.insert_source(src)
        claim = Claim(id="c_ent_1", question_id=kw["question_obj"].id, source_id=src.id,
                      text="Enterprise software delivery teams using AI coding assistants report shorter cycle time.",
                      source_excerpt="teams report shorter cycle time", grade="moderate")
        r._safe_insert_claim(claim)
        return [claim]

    r._harvest_enterprise_lane = ent
    res = _run(r)
    assert res["stopped_at"] == "check_b"
    assert [s["title"] for s in res["enterprise_sources"]] == ["DORA report"]
    assert res["lane_breakdown"]["enterprise_sources_count"] == 1
    assert res["lane_breakdown"]["enterprise_claims_count"] == 1


# ------------------------------------------------------------------------------
# Test 7: Unchanged exclusions are not logged again
# ------------------------------------------------------------------------------
def test_unchanged_exclusion_logged_once(tmp_path):
    r = _runner(tmp_path)
    first = _run(r)
    key = first["claims"][0]["content_key"]
    _run(r, excluded_claim_keys=[key])
    _run(r, excluded_claim_keys=[key])
    with LedgerRepository(db_path=r.db_path)._conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM reviews WHERE gate='evidence_board' AND action='exclude';").fetchone()[0]
    assert n == 1


# ------------------------------------------------------------------------------
# Test 8: Exclusion kind is explicit
# ------------------------------------------------------------------------------
def test_excluded_claims_carry_kind(tmp_path):
    r = _runner(tmp_path)
    first = _run(r)
    res = _run(r, excluded_claim_keys=[first["claims"][0]["content_key"]])
    assert {c["exclusion_kind"] for c in res["excluded_claims"]} == {"operator"}
    src = _web_app()
    assert 'c.get("exclusion_kind") == "operator"' in src
    assert '== "Excluded on the evidence board."' not in src


# ------------------------------------------------------------------------------
# Test 9: One source lookup per source per run
# ------------------------------------------------------------------------------
def test_source_lookups_once_per_source(tmp_path, monkeypatch):
    r = _runner(tmp_path)
    calls: List[str] = []
    real = r.repo.get_source

    def counting(sid):
        calls.append(sid)
        return real(sid)

    monkeypatch.setattr(r.repo, "get_source", counting)
    _run(r)
    per_source = {sid: calls.count(sid) for sid in set(calls)}
    assert all(n <= 1 for n in per_source.values()), per_source


# ------------------------------------------------------------------------------
# Test 10: Bake-off leaves process settings alone
# ------------------------------------------------------------------------------
def test_bakeoff_does_not_mutate_globals(tmp_path, monkeypatch):
    sys.path.insert(0, "evals")
    import bakeoff_check_a
    import src.engine.check_a_on_topic as check_a

    before_prompt = check_a.PROMPT_FILE_PATH
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    bakeoff_check_a.main(["--provider", "stub", "--model", "some-model", "--prompt", "prompts/check_a_on_topic_v2.md",
                          "--out", str(tmp_path / "r.json")])
    assert check_a.PROMPT_FILE_PATH == before_prompt
    assert "OLLAMA_MODEL" not in os.environ
    report = json.loads((tmp_path / "r.json").read_text())
    assert report["prompt"] == "prompts/check_a_on_topic_v2.md"
