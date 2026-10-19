"""Tests for Slice S5 (part 1): hedge terms on claims, honest citation binding, Check C scaffolding.

Requirements:
1. Hedge terms come from synth/hedge_terms.yaml and are found by whole word or phrase,
   case-insensitively, deduplicated, in order of appearance ("may" is not found in "mayor").
2. The extractor records the hedge terms of each claim's source sentence.
3. Migration 007 adds claims.hedge_terms_json and it round-trips through the repository.
4. Citation binding resolves every [P#] and [c_...] tag in a sentence; a sentence with no
   tag is unbound (no claim attached), never bound to a default claim.
5. In a run, every drafted finding cites only claims its own tags point to.
6. Check C rules: a claim with hedges and a sentence with none is "dropped"; a sentence that
   keeps any hedge is "kept"; a claim with no hedges is "no_hedge".
7. The Check C model judge returns a verdict per pair; malformed or missing output abstains.
8. The Check C bake-off data loads and the rules-only baseline scores it without a model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.engine.check_c_hedges import judge_hedges_with_model, rules_hedge_verdict
from src.extract.claim_extractor import extract_claims_from_paper
from src.extract.hedges import find_hedge_terms
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, Source
from src.ledger.repository import LedgerRepository
from src.synth.generator import resolve_citations


# ------------------------------------------------------------------------------
# Test 1: Hedge term detection
# ------------------------------------------------------------------------------
def test_find_hedge_terms_whole_words_phrases_and_order():
    text = "Results suggest gains may appear In Some Settings; the mayor suggests otherwise, and it may."
    assert find_hedge_terms(text) == ["suggest", "may", "appear", "in some settings", "suggests"]
    assert find_hedge_terms("The mayor approved the budget.") == []
    assert find_hedge_terms("") == []


# ------------------------------------------------------------------------------
# Test 2: Extractor records hedges from the source sentence
# ------------------------------------------------------------------------------
def test_extractor_records_hedge_terms():
    paper = {
        "id": "p-h",
        "title": "Assistants in delivery",
        "abstract": "Results suggest that coding assistants may shorten cycle time by 14%. Teams adopted the tool in 2024.",
    }
    claims = extract_claims_from_paper(paper, "q")
    assert claims[0].hedge_terms_json == ["suggest", "may"]
    assert claims[1].hedge_terms_json == []


# ------------------------------------------------------------------------------
# Test 3: Migration 007 and repository round-trip
# ------------------------------------------------------------------------------
def test_migration_007_hedge_terms_round_trip(tmp_path):
    db = str(tmp_path / "ledger.db")
    assert apply_migrations(db_path=db) >= 7
    repo = LedgerRepository(db_path=db)
    with repo._conn() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(claims);").fetchall()}
    assert "hedge_terms_json" in cols
    repo.insert_source(Source(id="s1", lane="academic", source_type="peer_reviewed", org="ICSE", title="T"))
    repo.insert_claim(Claim(id="c1", source_id="s1", text="x", source_excerpt="y", hedge_terms_json=["may", "suggests"]))
    assert repo.get_claim("c1").hedge_terms_json == ["may", "suggests"]
    repo.insert_claim(Claim(id="c2", source_id="s1", text="x", source_excerpt="y"))
    assert repo.get_claim("c2").hedge_terms_json is None


# ------------------------------------------------------------------------------
# Test 4: Citation binding resolves tags; untagged sentences stay unbound
# ------------------------------------------------------------------------------
def test_resolve_citations_all_tags_and_unbound():
    claims = [
        Claim(id="c_a_1", source_id="pa", text="a1", source_excerpt="e"),
        Claim(id="c_a_2", source_id="pa", text="a2", source_excerpt="e"),
        Claim(id="c_b_1", source_id="pb", text="b1", source_excerpt="e"),
    ]
    papers = [{"id": "pa"}, {"id": "pb"}]
    by_id = {c.id: c for c in claims}
    assert resolve_citations("Gains were seen [P1].", papers, claims, by_id) == ["c_a_1", "c_a_2"]
    assert resolve_citations("Both [P2] and [c_a_2] agree.", papers, claims, by_id) == ["c_b_1", "c_a_2"]
    assert resolve_citations("A sentence with no citation.", papers, claims, by_id) == []
    assert resolve_citations("Unknown [P9] and [c_zz_1].", papers, claims, by_id) == []


# ------------------------------------------------------------------------------
# Test 5: In a run, drafted findings cite only what their tags point to
# ------------------------------------------------------------------------------
def test_run_findings_cite_only_tagged_claims(tmp_path, monkeypatch):
    from src.analysis.multilane_runner import MultiLaneResearchRunner

    db, prac = str(tmp_path / "l.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    runner = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    runner._harvest_enterprise_lane = lambda **kwargs: []
    runner.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1}

    def fake_deliverables(**kwargs):
        return {
            "executive_summary": "summary",
            "key_findings": ["Assistants may shorten cycle time [P1].", "An untagged claim with no citation."],
            "generation_mode": "model",
            "is_fallback": False,
        }

    monkeypatch.setattr(runner, "_generate_executive_deliverables", lambda **kw: fake_deliverables(**kw))
    papers = [{
        "id": "p-cyc", "title": "AI coding assistants and enterprise software delivery cycle time",
        "abstract": "Results suggest AI coding assistants may shorten enterprise software delivery cycle time by 14%.",
        "year": 2024, "venue": "ICSE", "url": "https://doi.org/p-cyc",
    }]
    res = runner.run_workflow(
        topic="How do AI coding assistants affect enterprise software delivery cycle time?",
        map_provider="stub", reduce_provider="stub", academic_papers_override=papers,
    )
    by_text = {s["text"]: s for s in res["sentence_traces"]}
    tagged = by_text["Assistants may shorten cycle time [P1]."]
    untagged = by_text["An untagged claim with no citation."]
    assert tagged["claims"] and all(cid.startswith("c_p-cyc_") for cid in tagged["claims"])
    assert untagged["claims"] == []
    assert untagged["checks_json"].get("binding") == "unbound"


# ------------------------------------------------------------------------------
# Test 6: Check C rules
# ------------------------------------------------------------------------------
def test_rules_hedge_verdict():
    assert rules_hedge_verdict(["may"], "AI improves teamwork.") == "dropped"
    assert rules_hedge_verdict(["may"], "AI could improve teamwork.") == "kept"
    assert rules_hedge_verdict([], "AI improves teamwork.") == "no_hedge"
    assert rules_hedge_verdict(None, "AI improves teamwork.") == "no_hedge"


# ------------------------------------------------------------------------------
# Test 7: Check C model judge
# ------------------------------------------------------------------------------
def test_judge_hedges_with_model_parses_and_abstains():
    pairs = [
        {"claim": "AI may improve teamwork.", "sentence": "AI improves teamwork."},
        {"claim": "Gains appear in some settings.", "sentence": "Gains appear in some settings."},
    ]

    class Good:
        model = "fake"

        def generate(self, prompt, **kwargs):
            assert "[H1]" in prompt and "[H2]" in prompt
            return json.dumps({"verdicts": [{"id": "H1", "verdict": "dropped", "reason": "x"}, "junk",
                                            {"id": "H2", "verdict": "kept", "reason": "y"}]})

    class Broken:
        model = "broken"

        def generate(self, *a, **k):
            raise ConnectionError("offline")

    assert [v["verdict"] for v in judge_hedges_with_model(Good(), pairs)] == ["dropped", "kept"]
    assert [v["verdict"] for v in judge_hedges_with_model(Broken(), pairs)] == ["abstain", "abstain"]
    from src.llm.stub_client import StubLLM

    assert [v["verdict"] for v in judge_hedges_with_model(StubLLM(), pairs)] == ["abstain", "abstain"]


# ------------------------------------------------------------------------------
# Test 8: Bake-off data and rules-only baseline
# ------------------------------------------------------------------------------
def test_check_c_bakeoff_data_and_rules_baseline(tmp_path):
    import subprocess
    import sys

    data = json.loads(Path("evals/data/check_c_pairs_v1.json").read_text(encoding="utf-8"))
    pairs = data["pairs"]
    assert len(pairs) >= 20
    assert {p["label"] for p in pairs} == {"kept", "dropped"}
    assert all(p["claim"] and p["sentence"] for p in pairs)

    out = tmp_path / "rules.json"
    proc = subprocess.run(
        [sys.executable, "evals/bakeoff_check_c.py", "--provider", "rules", "--out", str(out)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["n"] == len(pairs)
    assert report["dropped"]["precision"] is not None
