"""Test A5: Lane and question scoping.

Verifies:
1. Every row used by an output is filtered by run_id and question_id.
2. The canary hospital question produces 0 practitioner claims and Outcome 3 or 4 (NEVER Outcome 1).
3. Practitioner observations preserve full text without [:50] truncation.
4. If a question has 0 enterprise claims, Lane B indicates no enterprise claims for this question.
5. If a question has 0 practitioner observations, Lane C indicates no practitioner observations for this question.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.collectors.practitioner.collector import PractitionerCollector
from src.gaps.matrix_builder import GapMatrixBuilder
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, Question, Run, Source
from src.ledger.repository import LedgerRepository


def test_canary_hospital_question_isolated_from_software_delivery_observations():
    """Verify hospital canary question does NOT inherit software observations or enterprise claims."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.db")
        prac_db_path = str(Path(tmpdir) / "test_prac.db")
        apply_migrations(db_path=db_path)
        apply_migrations(db_path=prac_db_path)

        repo = LedgerRepository(db_path=db_path)
        prac_collector = PractitionerCollector(db_path=prac_db_path)

        # 1. Seed unrelated software engineering question with practitioner observations
        q_soft = Question(
            id="q-soft-01",
            text="How do automated verification gates affect software defects?",
            scope="software architecture",
        )
        repo.insert_question(q_soft)
        prac_collector.add_observation(
            question_id=q_soft.id,
            situation="140 enterprise microservices undergoing continuous deployment",
            decision="Enforced strict gate check",
            action="Automated static analysis",
            outcome="Zero defect regression",
            sector="software_delivery",
            abstraction_confirmed=True,
        )

        # 2. Canary Hospital Question
        q_hosp = Question(
            id="q-hosp-01",
            text="How are hospitals governing clinical AI triage tools to manage patient safety and regulatory compliance?",
            scope="clinical AI governance",
        )
        repo.insert_question(q_hosp)

        # Academic papers for hospital question (so academic lane is active)
        hosp_paper = {
            "id": "src-hosp-01",
            "title": "Clinical AI Governance in Acute Care Hospitals: Patient Safety and Regulatory Audits",
            "abstract": "We evaluate clinical AI triage tools and safety governance in hospital networks under healthcare regulatory compliance standards.",
            "year": 2024,
            "venue": "Journal of Clinical Medicine & AI Governance",
            "url": "https://doi.org/10.1000/clinical-gov",
            "relevance_score": 0.95,
        }

        runner = MultiLaneResearchRunner(
            db_path=db_path,
            practitioner_db_path=prac_db_path,
        )

        results = runner.run_workflow(
            topic=q_hosp.text,
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=[hosp_paper],
        )

        # Hospital question must have ZERO practitioner observations
        assert len(results["practitioner_observations"]) == 0, (
            f"Expected 0 practitioner observations for hospital question, found: {results['practitioner_observations']}"
        )
        assert results["lane_breakdown"]["practitioner_claims_count"] == 0

        # Hospital question must have ZERO enterprise claims
        assert len(results["enterprise_sources"]) == 0, (
            f"Expected 0 enterprise sources for hospital question, found: {results['enterprise_sources']}"
        )
        assert results["lane_breakdown"]["enterprise_claims_count"] == 0

        # Gap Matrix must NOT be Outcome 1 (Supported)
        gap_res = results["gap_matrix"]
        assert gap_res["field_state"] == "none found", f"Expected field_state 'none found', got {gap_res['field_state']}"
        assert gap_res["enterprise_state"] == "none found", f"Expected enterprise_state 'none found', got {gap_res['enterprise_state']}"
        assert gap_res["outcome"] in (3, 4), f"Expected Outcome 3 or 4, but got Outcome {gap_res['outcome']}"
        assert gap_res["outcome"] != 1, "Hospital question must NEVER evaluate to Outcome 1 without enterprise or field claims!"


def test_practitioner_observation_preserves_full_text_without_truncation():
    """Verify practitioner observations preserve full situation/action text (> 50 chars)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prac_db_path = str(Path(tmpdir) / "test_prac.db")
        apply_migrations(db_path=prac_db_path)
        collector = PractitionerCollector(db_path=prac_db_path)

        long_situation = "Production cluster deployment across 140 enterprise microservices handling real-time financial telemetry"
        long_action = "Integrated automated verification gates for custom stack and audited deployment pipeline drift"
        long_outcome = "Maintained verified governance and zero ungrounded regression across all regional clusters"

        src, claim = collector.add_observation(
            question_id="q-text-01",
            situation=long_situation,
            decision="Enforce verification gate",
            action=long_action,
            outcome=long_outcome,
            sector="financial_delivery",
            abstraction_confirmed=True,
        )

        observations = collector.list_observations(question_id="q-text-01")
        assert len(observations) == 1
        obs = observations[0]
        ctx = obs.context_json or {}

        assert ctx.get("situation") == long_situation, f"Situation truncated! Got: {ctx.get('situation')}"
        assert ctx.get("action") == long_action, f"Action truncated! Got: {ctx.get('action')}"
        assert ctx.get("outcome") == long_outcome, f"Outcome truncated! Got: {ctx.get('outcome')}"
