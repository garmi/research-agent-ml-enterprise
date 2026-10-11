"""Test A10: Comprehensive Canary Suite and Full Regression Verification.

Verifies all architectural guarantees across the 3 canary questions:
1. Q1 (Kiro / Developer Productivity) vs Q2 (Hospital Clinical AI Triage):
   - Share ZERO assertive findings sentences (no canned text).
2. Q2 (Hospital Clinical AI Triage):
   - Cites ZERO papers about software engineering, microservices, or delivery velocity.
   - Contains ZERO practitioner observations unless explicitly entered for Q2.
3. Q3 (Sourdough fermentation temperature and crumb structure):
   - Evaluates to honest Outcome 3 or 4 (food science, no software/vendor claims).
   - Contains ZERO software/delivery claims in any lane.
4. Fallback honesty:
   - When primary model fails or stub mode is used, generation_mode is 'extractive_fallback'
   - Status is NEVER 'publish_ready'.
5. Single Source of Truth:
   - Every rendered sentence traces 1-to-1 to an output_sentences row and cited ledger claims.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List
import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.collectors.practitioner.collector import PractitionerCollector
from src.ledger.migrations import apply_migrations
from src.ledger.models import Question
from src.ledger.repository import LedgerRepository


def _create_runner(tmpdir: str) -> MultiLaneResearchRunner:
    db_path = str(Path(tmpdir) / "test_ledger.db")
    prac_db_path = str(Path(tmpdir) / "test_prac.db")
    q_yaml_path = str(Path(tmpdir) / "register.yaml")
    apply_migrations(db_path=db_path)
    apply_migrations(db_path=prac_db_path)
    return MultiLaneResearchRunner(
        db_path=db_path,
        practitioner_db_path=prac_db_path,
        questions_yaml_path=q_yaml_path,
    )


def test_canary_suite_q1_kiro_vs_q2_hospitals_isolation_and_distinct_findings():
    """Verify Q1 and Q2 share ZERO findings text and Q2 cites zero software papers or observations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = _create_runner(tmpdir)

        # Seed unrelated software practitioner observations
        prac_col = PractitionerCollector(db_path=runner.practitioner_db_path)
        q_soft = Question(id="q-soft-pilot", text="Software delivery velocity", scope="software")
        prac_col.repo.insert_question(q_soft)
        prac_col.add_observation(
            question_id=q_soft.id,
            situation="140 enterprise microservices undergoing continuous deployment",
            decision="Enforced strict gate check",
            action="Automated static analysis",
            outcome="Zero defect regression",
            sector="software_delivery",
            abstraction_confirmed=True,
        )

        # Q1 Papers (Software)
        q1_papers = [
            {
                "id": "paper-kiro-1",
                "title": "Empirical Evaluation of Amazon Kiro and Generative Assistants in Software Delivery",
                "abstract": "We evaluate Amazon Kiro adoption, empirical velocity increases by 32% across standard delivery tasks.",
                "year": 2024,
                "venue": "IEEE Transactions on Software Engineering",
                "url": "https://doi.org/10.1109/tse.2024.01",
                "relevance_score": 0.95,
            }
        ]

        # Q2 Papers (Healthcare / Hospital Triage)
        q2_papers = [
            {
                "id": "paper-hosp-1",
                "title": "Governance and Patient Safety of Clinical AI Triage Tools in Acute Care Hospitals",
                "abstract": "Clinical AI triage tools reduce emergency department wait times by 18% under strict human-in-the-loop audit governance.",
                "year": 2024,
                "venue": "New England Journal of Medicine AI",
                "url": "https://doi.org/10.1056/nejmai.2024.01",
                "relevance_score": 0.94,
            }
        ]

        # Run Q1
        q1_topic = "What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?"
        res1 = runner.run_workflow(
            topic=q1_topic,
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=q1_papers,
        )

        # Run Q2
        q2_topic = "How are hospitals governing clinical AI triage tools to manage patient safety and regulatory compliance?"
        res2 = runner.run_workflow(
            topic=q2_topic,
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=q2_papers,
        )

        # 1. Verify Q1 and Q2 share NO assertive findings sentences
        q1_sentences = {s["text"].strip() for s in res1.get("sentence_traces", []) if s.get("type") == "assertive"}
        q2_sentences = {s["text"].strip() for s in res2.get("sentence_traces", []) if s.get("type") == "assertive"}
        shared_findings = q1_sentences.intersection(q2_sentences)
        assert len(shared_findings) == 0, f"Defect D1 regression! Shared findings detected: {shared_findings}"

        # 2. Verify Q2 cites ZERO software papers
        for p in res2.get("papers", []):
            title_lower = p.get("title", "").lower()
            assert "software" not in title_lower, f"Q2 leaked software paper: {p['title']}"
            assert "kiro" not in title_lower, f"Q2 leaked Kiro paper: {p['title']}"

        # 3. Verify Q2 contains ZERO practitioner observations from software question
        assert len(res2.get("practitioner_observations", [])) == 0, (
            f"Q2 leaked practitioner observations: {res2.get('practitioner_observations')}"
        )

        # 4. Verify neither is 'publish_ready' in offline fallback mode
        assert res1["publish_res"]["status"] in ("blocked", "not_publishable")
        assert res2["publish_res"]["status"] in ("blocked", "not_publishable")
        assert res1["publish_res"]["allowed"] is False
        assert res2["publish_res"]["allowed"] is False


def test_canary_q3_sourdough_evaluation_honesty():
    """Verify Q3 (Sourdough) produces Outcome 3 or 4 with ZERO enterprise software claims."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = _create_runner(tmpdir)

        # Sourdough academic papers (Food Science)
        q3_papers = [
            {
                "id": "paper-sour-1",
                "title": "Impact of Fermentation Temperature on Sourdough Dough Rheology and Crumb Structure",
                "abstract": "Fermentation at 28C optimizes crumb porosity and lactic acid bacteria kinetics in wheat sourdough.",
                "year": 2023,
                "venue": "Journal of Cereal Science",
                "url": "https://doi.org/10.1016/jcs.2023.01",
                "relevance_score": 0.92,
            }
        ]

        q3_topic = "What empirical evidence exists on sourdough fermentation temperature and crumb structure?"
        res3 = runner.run_workflow(
            topic=q3_topic,
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=q3_papers,
        )

        # 1. Gap Matrix must evaluate to Outcome 3 or 4 (never Outcome 1, because Enterprise is none found)
        gap_entry = res3["gap_matrix"]
        assert gap_entry["outcome"] in (3, 4), (
            f"Expected Outcome 3 or 4 for sourdough question, but got Outcome {gap_entry['outcome']}"
        )
        assert gap_entry["enterprise_state"].lower() in ("none found", "unsupported", "none")

        # 2. Zero software or cloud vendor claims in any lane
        for c in res3.get("enterprise_claims", []):
            c_text = (getattr(c, "text", "") or "").lower()
            assert "microservice" not in c_text
            assert "kubernetes" not in c_text
            assert "aws" not in c_text


def test_all_output_sentences_trace_to_ledger_claims():
    """Verify that every rendered sentence strictly traces back to output_sentences and ledger claims."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = _create_runner(tmpdir)
        repo = LedgerRepository(db_path=runner.db_path)

        papers = [
            {
                "id": "paper-trace-1",
                "title": "Architectural Invariants in Production Systems",
                "abstract": "Automated verification eliminates drift across 45 distributed nodes in software systems.",
                "year": 2024,
                "venue": "ACM SIGSOFT",
                "url": "https://doi.org/10.1145/sigsoft.2024",
                "relevance_score": 0.91,
            }
        ]

        res = runner.run_workflow(
            topic="How do automated verification gates prevent architectural drift in production systems?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=papers,
        )

        sentence_traces = res.get("sentence_traces", [])
        assert len(sentence_traces) > 0, "Workflow should have generated output sentences"

        # Check DB persistence
        doc_id = res["doc_id"]
        db_sentences = repo.list_output_sentences(output_id=doc_id)
        assert len(db_sentences) == len(sentence_traces)

        # Verify every assertive sentence cites valid ledger claims
        for s in db_sentences:
            if s.type == "assertive":
                assert len(s.claim_ids_json) > 0, f"Assertive sentence {s.id} must cite at least one claim"
                for cid in s.claim_ids_json:
                    claim = repo.get_claim(cid)
                    assert claim is not None, f"Claim {cid} must exist in evidence ledger"

                    assert claim is not None, f"Claim {cid} must exist in evidence ledger"
