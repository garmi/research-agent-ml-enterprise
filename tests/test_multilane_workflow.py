"""Unit and Integration tests for MultiLaneResearchRunner."""

import tempfile
from pathlib import Path
import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner


def test_multilane_workflow_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_db = str(Path(tmpdir) / "test_ledger.db")
        prac_db = str(Path(tmpdir) / "test_prac.db")
        yaml_reg = str(Path(tmpdir) / "register.yaml")

        runner = MultiLaneResearchRunner(
            db_path=ledger_db,
            practitioner_db_path=prac_db,
            questions_yaml_path=yaml_reg,
        )

        dummy_papers = [
            {
                "id": "p-empirical-01",
                "title": "Empirical Evaluation of AI Coding Assistants in Financial Software Delivery",
                "abstract": "Controlled experiment with 80 developers demonstrates that specification-driven test suites reduce hallucinated bugs by 42% while improving velocity by 25%.",
                "year": 2024,
                "venue": "ICSE",
                "url": "https://doi.org/10.1145/example",
                "relevance_score": 0.95,
            },
            {
                "id": "p-arch-02",
                "title": "Architectural Drift and Governance in Autonomous Agent Workflows",
                "abstract": "We study agentic code generation across 50 production repositories. The study finds that without automated contracts, architectural consistency degrades over time.",
                "year": 2024,
                "venue": "IEEE Software",
                "url": "https://doi.org/10.1109/example",
                "relevance_score": 0.90,
            },
        ]

        result = runner.run_workflow(
            topic="How do AI coding assistants impact developer productivity in enterprise software delivery?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=dummy_papers,
        )

        assert result is not None
        assert "verdict" in result
        assert "gap_matrix" in result
        assert "lane_breakdown" in result
        assert result["lane_breakdown"]["academic_count"] == 2
        assert result["lane_breakdown"]["enterprise_claims_count"] > 0
        assert result["lane_breakdown"]["practitioner_claims_count"] > 0
        assert len(result["claims"]) > 0
        assert "quality_scorecard" in result
        assert "gates_audit" in result

        # Verify Gap Matrix outcome
        assert result["gap_matrix"]["outcome"] in (1, 2, 3, 4)
        assert len(result["sentence_traces"]) > 0
