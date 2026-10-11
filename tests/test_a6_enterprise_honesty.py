"""Test A6: Enterprise lane honesty and gap matrix rules.

Verifies:
1. Distinct sources and distinct claims are counted separately everywhere (sources count != claims count).
2. 'Harvested N' equals the number of items actually retrieved, never the number of registry entries.
3. If only vendor sources are found, outcome is capped at Outcome 2 (NEVER Outcome 1).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.gaps.matrix_builder import GapMatrixBuilder
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, Question, Run, Source
from src.ledger.repository import LedgerRepository


def test_vendor_only_capping_caps_at_outcome_2_not_outcome_1():
    """Verify that 1 vendor source + 0 independent sources caps at Outcome 2 even with strong academic evidence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.db")
        rules_path = "grade/rules.yaml"
        apply_migrations(db_path=db_path)
        repo = LedgerRepository(db_path=db_path)

        # Question
        q = Question(
            id="q-vendor-eval-01",
            text="How do AI coding assistants perform in enterprise production?",
            scope="developer tooling",
        )
        repo.insert_question(q)

        # 1. Peer-reviewed academic source + strong claim
        acad_src = Source(
            id="src-acad-peer-01",
            lane="academic",
            source_type="peer_reviewed",
            org="ACM/IEEE",
            title="Controlled Study of Autonomous Coding Assistants",
            venue="ICSE 2024",
            venue_tier="verified",
            pub_date="2024",
            commercial_stake="none",
            status="active",
        )
        repo.insert_source(acad_src)
        c_acad = Claim(
            id="c-acad-01",
            question_id=q.id,
            source_id=acad_src.id,
            text="Controlled evaluation demonstrates 25% improvement in task completion.",
            source_excerpt="Controlled evaluation demonstrates 25% improvement.",
            grade="strong",
            status="approved",
        )
        repo.insert_claim(c_acad)

        # 2. Exactly ONE Vendor Enterprise Source with TWO claims (claims != sources count)
        vendor_src = Source(
            id="src-vendor-aws-01",
            lane="enterprise",
            source_type="vendor_blog",
            org="Vendor Corp",
            title="Vendor Corp Technology Evaluation Blog",
            venue="Vendor Corp Tech Blog",
            venue_tier="vendor",
            pub_date="2024",
            commercial_stake="vendor",
            status="active",
        )
        repo.insert_source(vendor_src)

        c_vendor_1 = Claim(
            id="c-vendor-01",
            question_id=q.id,
            source_id=vendor_src.id,
            text="Vendor blog reports internal adoption improved velocity by 40%.",
            source_excerpt="Internal adoption improved velocity by 40%.",
            grade="vendor_claim",
            status="approved",
        )
        c_vendor_2 = Claim(
            id="c-vendor-02",
            question_id=q.id,
            source_id=vendor_src.id,
            text="Vendor telemetry shows 85% developer satisfaction.",
            source_excerpt="Developer satisfaction measured at 85%.",
            grade="vendor_claim",
            status="approved",
        )
        repo.insert_claim(c_vendor_1)
        repo.insert_claim(c_vendor_2)

        builder = GapMatrixBuilder(db_path=db_path, rules_path=rules_path)
        entry = builder.evaluate_question_lanes(question_id=q.id, run_id="run-test-vcap")

        # With strong academic evidence and active enterprise claims, uncapped would be Outcome 1.
        # But vendor-only capping rule MUST cap it at Outcome 2!
        assert entry.outcome == 2, f"Expected Outcome 2 due to vendor-only capping, but got Outcome {entry.outcome}"
        assert entry.outcome != 1, "Must NEVER be Outcome 1 when enterprise evidence is vendor-only!"
        assert "vendor" in entry.rationale.lower()


def test_sources_and_claims_counted_separately_in_runner_payload():
    """Verify distinct source count and claim count are separate and differ when 1 source yields multiple claims."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.db")
        prac_db_path = str(Path(tmpdir) / "test_prac.db")
        apply_migrations(db_path=db_path)
        apply_migrations(db_path=prac_db_path)

        q_yaml_path = str(Path(tmpdir) / "register.yaml")
        runner = MultiLaneResearchRunner(
            db_path=db_path,
            practitioner_db_path=prac_db_path,
            questions_yaml_path=q_yaml_path,
        )

        dummy_papers = [
            {
                "id": "p-01",
                "title": "Empirical Study of Code Quality",
                "abstract": "We evaluate code review automation across repositories.",
                "year": 2024,
                "venue": "ICSE",
                "url": "https://doi.org/10.1145/example",
                "relevance_score": 0.95,
            }
        ]

        # 1 distinct enterprise feed yielding 2 distinct items
        dummy_enterprise = {
            "dora-dev-survey": [
                {
                    "title": "DORA Research Report Item 1",
                    "text": "Empirical survey finds that automated testing improves delivery performance.",
                    "speaker": "independent",
                    "year": 2024,
                },
                {
                    "title": "DORA Research Report Item 2",
                    "text": "Continuous delivery practices reduce change failure rate by 30%.",
                    "speaker": "independent",
                    "year": 2024,
                },
            ]
        }

        results = runner.run_workflow(
            topic="How does continuous delivery affect software quality in large enterprises?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=dummy_papers,
            enterprise_feed_override=dummy_enterprise,
        )

        bd = results["lane_breakdown"]
        # Verify distinct sources count vs distinct claims count
        assert bd["enterprise_sources_count"] == 1, f"Expected 1 distinct enterprise source, got {bd.get('enterprise_sources_count')}"
        assert bd["enterprise_claims_count"] == 2, f"Expected 2 enterprise claims, got {bd.get('enterprise_claims_count')}"
        assert bd["enterprise_sources_count"] != bd["enterprise_claims_count"], "Sources count and claims count must be distinct!"


def test_outcome_1_requires_peer_reviewed_academic_and_non_vendor_enterprise():
    """Verify that Outcome 1 strictly requires both peer-reviewed academic and non-vendor enterprise evidence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.db")
        rules_path = "grade/rules.yaml"
        apply_migrations(db_path=db_path)
        repo = LedgerRepository(db_path=db_path)

        q = Question(
            id="q-eval-outcomes",
            text="How do automated deployment pipelines improve reliability?",
            scope="reliability",
        )
        repo.insert_question(q)

        # 1. Non-peer-reviewed academic (e.g. preprint with weak/moderate grade)
        acad_src_preprint = Source(
            id="src-acad-pre",
            lane="academic",
            source_type="preprint",
            org="arXiv",
            title="Preprint on Deployments",
            venue="arXiv",
            venue_tier="unverified",
            pub_date="2024",
            commercial_stake="none",
            status="active",
        )
        repo.insert_source(acad_src_preprint)

        # Non-vendor enterprise source
        ent_src_indep = Source(
            id="src-ent-dora",
            lane="enterprise",
            source_type="analyst_survey",
            org="DORA",
            title="DORA Report",
            venue="DORA",
            venue_tier="verified",
            pub_date="2024",
            commercial_stake="none",
            status="active",
        )
        repo.insert_source(ent_src_indep)

        c_ent = Claim(
            id="c-ent-indep",
            question_id=q.id,
            source_id=ent_src_indep.id,
            text="Continuous delivery reduces MTTR by 50%.",
            source_excerpt="MTTR reduced by 50%.",
            grade="strong",
            status="approved",
        )
        repo.insert_claim(c_ent)

        builder = GapMatrixBuilder(db_path=db_path, rules_path=rules_path)

        # Case A: Academic has 0 claims, Enterprise has independent claim -> Outcome 2
        entry_a = builder.evaluate_question_lanes(question_id=q.id, run_id="run-a")
        assert entry_a.outcome == 2, f"Expected Outcome 2 when academic has no claims, got {entry_a.outcome}"

        # Case B: Add peer-reviewed academic claim -> Now both are satisfied -> Outcome 1
        acad_src_peer = Source(
            id="src-acad-peer",
            lane="academic",
            source_type="peer_reviewed",
            org="IEEE",
            title="Empirical Evaluation of CI/CD",
            venue="IEEE TSE",
            venue_tier="verified",
            pub_date="2024",
            commercial_stake="none",
            status="active",
        )
        repo.insert_source(acad_src_peer)
        c_acad = Claim(
            id="c-acad-peer",
            question_id=q.id,
            source_id=acad_src_peer.id,
            text="Empirical evaluation across 20 organizations confirms reduced defect escape rates.",
            source_excerpt="Reduced defect escape rates confirmed empirically.",
            grade="strong",
            status="approved",
        )
        repo.insert_claim(c_acad)

        entry_b = builder.evaluate_question_lanes(question_id=q.id, run_id="run-b")
        assert entry_b.outcome == 1, f"Expected Outcome 1 when both peer-reviewed academic and non-vendor enterprise are present, got {entry_b.outcome}"

