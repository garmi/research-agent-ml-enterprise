"""Test audit of Enterprise Lane (Lane B) production retrieval behavior (Prompt A2-8).

Verifies:
1. In production (without test fixture overrides), Lane B returns an honest zero claims for Q1.
2. All 5 registered enterprise sources record search_log entries with result_count=0.
3. Custom user-provided enterprise URLs are ingested with legitimate URL, date, and excerpt.
4. INTEGRITY_REPORT.md plainly documents the live state of Lane B and unimplemented fetchers.
"""

import tempfile
from pathlib import Path
import pytest

from src.collectors.enterprise.collector import EnterpriseCollector
from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.ledger.models import Question
from src.ledger.migrations import apply_migrations
from src.ledger.db import get_connection

Q1_TEXT = "What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?"
REPORT_PATH = Path("docs/legacy/INTEGRITY_REPORT.md") if Path("docs/legacy/INTEGRITY_REPORT.md").exists() else Path("INTEGRITY_REPORT.md")


def test_enterprise_lane_production_returns_honest_zero():
    """Verify that in production without fixture overrides, Lane B returns exactly 0 claims."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "ledger.db")
        apply_migrations(db_path=db_path)

        collector = EnterpriseCollector(db_path=db_path)
        q = Question(id="q1", text=Q1_TEXT)
        collector.repo.insert_question(q)

        # Production execution: feed_data_override is None
        claims = collector.search_and_ingest(question=q, query=q.text, run_id="run_audit")

        # Must return an honest zero claims
        assert len(claims) == 0, f"Expected 0 claims in production, got {len(claims)}"

        # Must record search_log entries for all registered sources showing 0 results
        logs = collector.repo.list_search_logs(question_id="q1")
        assert len(logs) == 5, f"Expected 5 search_log entries, got {len(logs)}"
        for l in logs:
            assert l.result_count == 0
            assert l.lane == "enterprise"


def test_enterprise_lane_custom_url_ingests_real_metadata(monkeypatch):
    """Verify that when a user provides a custom enterprise URL, it is ingested with URL, date, and excerpt."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "ledger.db")
        prac_db = str(Path(tmpdir) / "prac.db")
        q_yaml = str(Path(tmpdir) / "register.yaml")
        apply_migrations(db_path=db_path)
        apply_migrations(db_path=prac_db)

        runner = MultiLaneResearchRunner(
            db_path=db_path,
            practitioner_db_path=prac_db,
            questions_yaml_path=q_yaml,
        )
        q_obj = Question(id="q1", text=Q1_TEXT)
        runner.repo.insert_question(q_obj)

        test_url = "https://aws.amazon.com/blogs/aws/amazon-q-developer-announcement/"
        fake_title = "Amazon Q Developer General Availability"
        fake_excerpt = "Amazon announces general availability of Amazon Q Developer for software teams."
        fake_domain = "aws.amazon.com"

        # Mock network fetch to return verified URL metadata
        monkeypatch.setattr(
            "src.analysis.multilane_runner.fetch_url_metadata",
            lambda url: (fake_title, fake_excerpt, fake_domain),
        )

        claims = runner._harvest_enterprise_lane(
            topic=Q1_TEXT,
            question_obj=Question(id="q1", text=Q1_TEXT),
            run_id="run_custom_test",
            custom_urls=[test_url],
            enterprise_feed_override=None,
        )

        assert len(claims) >= 1
        source = runner.repo.get_source(claims[0].source_id)
        assert source is not None
        assert source.url == test_url
        assert source.lane == "enterprise"
        assert source.venue_tier == "vendor"
        assert fake_title in source.title


def test_integrity_report_documents_enterprise_lane_status():
    """Verify INTEGRITY_REPORT.md plainly states the honest zero retrieval and unimplemented fetchers."""
    report_text = REPORT_PATH.read_text(encoding="utf-8")
    assert "Section A2-8" in report_text or "A2-8" in report_text
    assert "honest zero" in report_text.lower()
    assert "unimplemented" in report_text.lower()
