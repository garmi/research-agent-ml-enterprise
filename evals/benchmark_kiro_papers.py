"""Benchmark runner for Research Engine v2 Phase 1 on the 8 Kiro papers.

Ingests the 8 benchmark papers, extracts atomic claims, applies deterministic
grading rules, checks the sample draft outputs against hard gates G1-G6, and
calculates quality scores S1-S7.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, Dict, List

from src.extract.claim_extractor import extract_claims_from_paper
from src.grade.grader import Grader
from src.ledger.db import get_connection
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, OutputDoc, OutputSentence, Question, Source
from src.ledger.repository import LedgerRepository
from src.score.checker import GateChecker
from src.score.scorer import QualityScorer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_kiro_benchmark(
    report_json_path: str = "outputs/json/research_report.json",
    db_path: str = "ledger/ledger.db",
) -> Dict[str, Any]:
    # Step 1: Ensure database schema is migrated
    apply_migrations(db_path=db_path)
    repo = LedgerRepository(db_path=db_path)
    grader = Grader()
    checker = GateChecker()
    scorer = QualityScorer()

    # Step 2: Register Kiro question
    kiro_question = Question(
        id="q-kiro-empirical",
        text="What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?",
        scope="kiro",
        time_window_months=36,
        status="active",
        version=1,
    )
    repo.insert_question(kiro_question)

    # Step 3: Load the 8 papers
    with open(report_json_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    papers = report_data.get("papers", [])
    if not papers:
        raise ValueError(f"No papers found in {report_json_path}")

    stored_sources: Dict[str, Source] = {}
    stored_claims: Dict[str, Claim] = {}
    source_texts: Dict[str, str] = {}

    for p in papers:
        title = p.get("title", "")
        venue_str = p.get("venue") or p.get("source") or ""
        venue_tier = grader.resolve_venue_tier(venue_str)
        src_id = p.get("id") or f"src_{abs(hash(title)) % 1000000:06d}"

        source = Source(
            id=src_id,
            lane="academic",
            source_type="preprint" if "arxiv" in venue_str.lower() else "peer_reviewed",
            org=None,
            title=title,
            url=p.get("url"),
            doi=p.get("doi"),
            venue=venue_str,
            venue_tier=venue_tier,
            pub_date=str(p.get("year", "2026")),
            extraction_depth="abstract_only",
            commercial_stake="none",
        )
        repo.insert_source(source)
        stored_sources[src_id] = source
        source_texts[src_id] = f"{title} {p.get('abstract', '')}"

        # Extract atomic claims
        paper_record = dict(p)
        paper_record["id"] = src_id
        extracted = extract_claims_from_paper(
            paper=paper_record,
            question_id=kiro_question.id,
            target_entity="Amazon Kiro",
        )

        # Grade each claim
        for claim in extracted:
            assigned_grade, reasons = grader.grade_claim(claim, source)
            claim.grade = assigned_grade
            claim.grade_reasons_json = reasons
            repo.insert_claim(claim)
            stored_claims[claim.id] = claim

    # Step 4: Map the sample v1 draft sentences and evaluate against Hard Gates
    # In v1, Paper 4 (WJARR 2023) was misattributed for Kiro productivity ("up to 35%")
    # Let's find claims from Paper 4 and Paper 8
    p4_source = next((s for s in stored_sources.values() if "2023" in s.pub_date or "WJARR" in (s.venue or "")), None)
    p4_claim = next((c for c in stored_claims.values() if p4_source and c.source_id == p4_source.id), None)

    sample_sentences: List[OutputSentence] = []
    # Sentence 1: General Kiro claim citing Paper 4 (The exact v1 failure mode: R1 & G3 fail)
    s1_text = "Amazon Kiro enhances developer productivity by 25-35% in enterprise environments."
    s1_claim_id = p4_claim.id if p4_claim else list(stored_claims.keys())[0]
    sample_sentences.append(
        OutputSentence(
            id="sent_v1_1",
            output_id="out_kiro_v1",
            ordinal=1,
            text=s1_text,
            type="assertive",
            claim_ids_json=[s1_claim_id],
        )
    )

    # Sentence 2: Uncited headline number (The exact v1 failure mode: R2 & G2 fail)
    sample_sentences.append(
        OutputSentence(
            id="sent_v1_2",
            output_id="out_kiro_v1",
            ordinal=2,
            text="Autonomous coding platforms deliver a 67% reduction in defect remediations and a 20x velocity improvement.",
            type="assertive",
            claim_ids_json=[s1_claim_id],
        )
    )

    # Sentence 3: Uncited assertive sentence (G1 fail)
    sample_sentences.append(
        OutputSentence(
            id="sent_v1_3",
            output_id="out_kiro_v1",
            ordinal=3,
            text="Spec-driven governance models are essential for enterprise compliance.",
            type="assertive",
            claim_ids_json=[],
        )
    )

    # Check against Hard Gates
    gate_results = checker.check_output(
        sentences=sample_sentences,
        ledger_claims=stored_claims,
        source_texts=source_texts,
    )

    # Calculate Quality Score
    score_results = scorer.calculate_score(
        gate_result=gate_results,
        sentences=sample_sentences,
        ledger_claims=stored_claims,
        sources=stored_sources,
        questions=[kiro_question],
    )

    # Step 5: Compute Paper & Claim Statistics
    total_papers = len(papers)
    venue_counts = {}
    for s in stored_sources.values():
        venue_counts[s.venue_tier] = venue_counts.get(s.venue_tier, 0) + 1

    entity_match_counts = {}
    grade_counts = {}
    for c in stored_claims.values():
        entity_match_counts[c.entity_match] = entity_match_counts.get(c.entity_match, 0) + 1
        grade_counts[c.grade] = grade_counts.get(c.grade, 0) + 1

    summary = {
        "benchmark_papers_count": total_papers,
        "venue_tier_distribution": venue_counts,
        "total_claims_extracted": len(stored_claims),
        "entity_match_distribution": entity_match_counts,
        "claim_grade_distribution": grade_counts,
        "sample_v1_gate_check": gate_results.to_dict(),
        "sample_v1_score": score_results,
    }

    return summary


if __name__ == "__main__":
    result = run_kiro_benchmark()
    print(json.dumps(result, indent=2))
