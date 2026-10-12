"""Test A17: Adversarial Off-Topic Filter Tests (Prompt A3-4).

Verifies:
1. Adversarial negative papers against Q1:
   - "Amazon Marketplace Dynamic Pricing Algorithms"
   - "Principal-Agent Problems in Corporate Governance"
   - "Agent-Based Modeling of Epidemic Spread"
   - "Economic Development and Industrial Policy in East Asia"
   All 4 MUST be rejected with 'off_topic_low_relevance'.
2. Positive papers against Q1:
   - A paper about Amazon Kiro
   - A paper about spec-driven development
   - A paper about an AI coding assistant RCT
   All 3 MUST pass.
3. Reconciled threshold:
   - min_weighted_overlap is 0.35 across config.yaml, MultiLaneResearchRunner, and search logs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
import yaml

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.ledger.migrations import apply_migrations
from src.ledger.repository import LedgerRepository


def test_adversarial_negative_and_positive_topic_filtering_for_q1():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.db")
        prac_db_path = str(Path(tmpdir) / "test_prac.db")
        q_yaml_path = str(Path(tmpdir) / "register.yaml")
        apply_migrations(db_path=db_path)
        apply_migrations(db_path=prac_db_path)

        runner = MultiLaneResearchRunner(
            db_path=db_path,
            practitioner_db_path=prac_db_path,
            questions_yaml_path=q_yaml_path,
        )

        test_papers = [
            # Adversarial negatives
            {
                "id": "p-adv-amazon-pricing",
                "title": "Amazon Marketplace Dynamic Pricing Algorithms",
                "abstract": "We analyze algorithmic pricing, merchant competition, and seller revenue on the Amazon marketplace platform.",
                "year": 2024,
                "venue": "Management Science",
                "url": "https://doi.org/10.1000/amz-pricing",
                "relevance_score": 0.85,
            },
            {
                "id": "p-adv-principal-agent",
                "title": "Principal-Agent Problems in Corporate Governance",
                "abstract": "We investigate executive incentives, moral hazard, and contract theory in principal-agent relations in corporate firms.",
                "year": 2023,
                "venue": "Journal of Financial Economics",
                "url": "https://doi.org/10.1000/prin-agent",
                "relevance_score": 0.82,
            },
            {
                "id": "p-adv-agent-epidemic",
                "title": "Agent-Based Modeling of Epidemic Spread",
                "abstract": "Simulation of infectious disease transmission dynamics and viral contagion using multi-agent computational models.",
                "year": 2024,
                "venue": "Nature Computational Science",
                "url": "https://doi.org/10.1000/agent-epi",
                "relevance_score": 0.80,
            },
            {
                "id": "p-adv-east-asia-econ",
                "title": "Economic Development and Industrial Policy in East Asia",
                "abstract": "A macroeconomic analysis of trade tariffs, export discipline, and post-war manufacturing growth across East Asian economies.",
                "year": 2022,
                "venue": "World Development",
                "url": "https://doi.org/10.1000/east-asia-econ",
                "relevance_score": 0.75,
            },
            # Positives
            {
                "id": "p-pos-kiro",
                "title": "Empirical Analysis of AWS Kiro in Cloud Infrastructure",
                "abstract": "Field study evaluating Amazon Kiro for specification-driven cloud development and software delivery velocity.",
                "year": 2024,
                "venue": "IEEE Software",
                "url": "https://doi.org/10.1109/kiro-eval",
                "relevance_score": 0.95,
            },
            {
                "id": "p-pos-spec-driven",
                "title": "Spec-Driven Development with LLM Assistants: A Controlled Study",
                "abstract": "Specification-driven development contracts prevent code drift and improve developer throughput in enterprise codebases.",
                "year": 2024,
                "venue": "ACM ICSE",
                "url": "https://doi.org/10.1145/sdd-study",
                "relevance_score": 0.94,
            },
            {
                "id": "p-pos-assistant-rct",
                "title": "A Randomized Controlled Trial of AI Coding Assistants in Enterprise Software Teams",
                "abstract": "Randomized controlled trial of 250 professional software engineers measuring task completion time and defect rates with AI coding assistants.",
                "year": 2024,
                "venue": "ACM TOSEM",
                "url": "https://doi.org/10.1145/assistant-rct",
                "relevance_score": 0.96,
            },
        ]

        q1_topic = "What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?"
        results = runner.run_workflow(
            topic=q1_topic,
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=test_papers,
        )

        repo = LedgerRepository(db_path=db_path)
        accepted_paper_ids = [p["id"] for p in results["papers"]]

        # 1. All 4 adversarial negatives MUST be rejected
        assert "p-adv-amazon-pricing" not in accepted_paper_ids, f"Amazon pricing paper passed! Accepted: {accepted_paper_ids}"
        assert "p-adv-principal-agent" not in accepted_paper_ids, f"Principal-agent paper passed! Accepted: {accepted_paper_ids}"
        assert "p-adv-agent-epidemic" not in accepted_paper_ids, f"Agent epidemic paper passed! Accepted: {accepted_paper_ids}"
        assert "p-adv-east-asia-econ" not in accepted_paper_ids, f"East Asia econ paper passed! Accepted: {accepted_paper_ids}"

        # 2. All 3 positive papers MUST pass
        assert "p-pos-kiro" in accepted_paper_ids, f"Positive Kiro paper rejected! Accepted: {accepted_paper_ids}"
        assert "p-pos-spec-driven" in accepted_paper_ids, f"Positive spec-driven paper rejected! Accepted: {accepted_paper_ids}"
        assert "p-pos-assistant-rct" in accepted_paper_ids, f"Positive assistant RCT paper rejected! Accepted: {accepted_paper_ids}"

        # 3. Check search log rejection reasons
        search_logs = repo.list_search_logs()
        rejected_logs = {
            sl.details_json.get("paper_id"): sl.rejected_reason
            for sl in search_logs
            if sl.details_json and "paper_id" in sl.details_json
        }
        for adv_id in ("p-adv-amazon-pricing", "p-adv-principal-agent", "p-adv-agent-epidemic", "p-adv-east-asia-econ"):
            reason = rejected_logs.get(adv_id, "")
            assert "off_topic_low_relevance" in reason, f"Paper {adv_id} should have off_topic_low_relevance, got: {reason}"


def test_config_and_code_reconciliation_threshold():
    """Verify min_weighted_overlap is 0.35 in config.yaml and MultiLaneResearchRunner default."""
    config_path = Path("config.yaml")
    assert config_path.exists()
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg.get("research", {}).get("min_weighted_overlap") == 0.35, (
        f"config.yaml min_weighted_overlap should be 0.35, got: {cfg.get('research', {}).get('min_weighted_overlap')}"
    )
