"""Tests for QuestionFormulationAgent."""

import tempfile
from pathlib import Path
import pytest
import yaml

from src.analysis.question_formulator import FormulatedQuestion, QuestionFormulationAgent
from src.ledger.service import LedgerService


def test_question_formulator_heuristic():
    agent = QuestionFormulationAgent()
    
    # Test 1: Security/Vulnerability problem statement
    res1 = agent.formulate("Our teams are adopting Copilot and Kiro, but we are worried about security vulnerabilities, code leaks, and IP compliance.")
    assert isinstance(res1, FormulatedQuestion)
    assert res1.scope == "security"
    assert "security vulnerabilities" in res1.strategic_question.lower() or "mitigate" in res1.strategic_question.lower()
    assert len(res1.sub_questions) == 3
    assert "Amazon Kiro" in res1.target_entities or "GitHub Copilot" in res1.target_entities

    # Test 2: ROI/Productivity problem statement
    res2 = agent.formulate("We need to justify the cost and measure real developer velocity and ROI of generative AI assistants.")
    assert res2.scope == "productivity"
    assert len(res2.sub_questions) == 3

    # Test 3: Governance problem statement
    res3 = agent.formulate("How to prevent architectural drift and maintain specification-driven contracts with autonomous agent swarms?")
    assert res3.scope == "governance"
    assert "governance" in res3.strategic_question.lower() or "specification-driven" in res3.strategic_question.lower()


def test_question_formulator_registration():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.db")
        yaml_path = str(Path(tmpdir) / "register.yaml")

        service = LedgerService(db_path=db_path, questions_yaml_path=yaml_path)
        agent = QuestionFormulationAgent()

        formulated = agent.formulate("Evaluating Kiro adoption in large multi-vendor banking platforms.")
        q_obj = agent.register_question_in_register(
            formulated=formulated,
            service=service,
            yaml_path=yaml_path,
        )

        assert q_obj.id == formulated.suggested_id
        assert q_obj.text == formulated.strategic_question

        # Verify YAML content
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert len(data["questions"]) == 1
        assert data["questions"][0]["id"] == formulated.suggested_id
        assert data["questions"][0]["text"] == formulated.strategic_question

        # Verify DB content
        stored_q = service.repo.get_question(formulated.suggested_id)
        assert stored_q is not None
        assert stored_q.text == formulated.strategic_question
