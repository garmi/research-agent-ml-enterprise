"""Test honest offline path, error logging, and extractive fallback (A2)."""

from pathlib import Path
import tempfile
import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner


def test_fallback_produces_extractive_claims_and_blocks_publication():
    """Verify that when the LLM provider fails, the runner uses extractive fallback,
    records generation_mode='extractive_fallback', logs exception details, and never
    marks the output as publish_ready.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_db = str(Path(tmpdir) / "test_ledger.db")
        prac_db = str(Path(tmpdir) / "test_prac.db")
        yaml_reg = str(Path(tmpdir) / "register.yaml")

        runner = MultiLaneResearchRunner(
            db_path=ledger_db,
            practitioner_db_path=prac_db,
            questions_yaml_path=yaml_reg,
        )
        # Thin fixture: this test checks drafting, not evidence volume (Check B thresholds, DEC-016).
        runner.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1}

        dummy_papers = [
            {
                "id": "p-01",
                "title": "Empirical Verification of AI Code",
                "abstract": "We observe that contract testing reduces defects by 30% across repositories.",
                "year": 2024,
                "venue": "ICSE",
                "url": "https://doi.org/10.1145/test",
                "relevance_score": 0.95,
            }
        ]

        # Call with an intentionally invalid provider that raises an exception
        result = runner.run_workflow(
            topic="How do automated verification gates affect software defects?",
            depth="Fast",
            tone="Executive",
            map_provider="invalid_provider_that_raises",
            reduce_provider="invalid_provider_that_raises",
            academic_papers_override=dummy_papers,
        )

        assert result is not None
        assert result.get("generation_mode") == "extractive_fallback", (
            f"Expected generation_mode='extractive_fallback', got {result.get('generation_mode')}"
        )
        assert result.get("is_fallback") is True

        # Error details must be present and capture class and message
        error_details = result.get("error_details")
        assert error_details is not None, "Expected 'error_details' in result payload"
        assert "error_class" in error_details
        assert "error_message" in error_details
        assert len(error_details["error_message"]) > 0

        # Run record in ledger must store error_details or generation_mode
        run_record = runner.repo.get_run(result["run_id"])
        assert run_record is not None
        assert run_record.config_json is not None
        assert "extractive_fallback" in str(run_record.config_json) or "error_class" in str(run_record.config_json)

        # Fallback output cannot be PUBLISH_READY
        quality = result.get("quality_scorecard", {})
        assert quality.get("band") != "PUBLISH_READY", (
            f"Fallback output must never be PUBLISH_READY, got {quality.get('band')}"
        )

        # Fallback must not write inferred recommendations or roadmap
        synthesis = result.get("synthesis", {})
        assert synthesis.get("recommendations") == [] or synthesis.get("recommendations") is None
        assert synthesis.get("strategic_roadmap") == [] or synthesis.get("strategic_roadmap") is None

        # Findings must be extractive claims with citations, not free-text inferences
        findings = result.get("findings", [])
        for f in findings:
            text = f.get("text", "")
            # Must reference a source/claim citation tag e.g. [P1] or [C_
            assert "[" in text and "]" in text, f"Extractive finding must contain citation: {text}"
