"""Test suite for Phase 3: Enterprise Lane Collector, 5 Sources, and search_log.

Verifies:
- All 5 sources in sources_registry.yaml are verified for terms and robots.txt.
- search_log records prove 'searched, nothing found' when results are 0.
- Ingested enterprise claims carry speaker stake metadata.
- Vendor primary sources default to 'vendor_claim' grade unless independently corroborated.
"""

import os
import tempfile
import pytest
import yaml

from src.collectors.enterprise.collector import EnterpriseCollector
from src.ledger.models import Question
from src.ledger.repository import LedgerRepository


@pytest.fixture
def enterprise_env():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_ledger.db")
        collector = EnterpriseCollector(
            registry_path="collectors/enterprise/sources_registry.yaml",
            db_path=db_path,
        )
        yield collector, db_path


def test_registry_contains_five_verified_sources(enterprise_env):
    collector, _ = enterprise_env
    assert len(collector.registry_sources) == 5, f"Expected exactly 5 enterprise sources, got {len(collector.registry_sources)}"

    # Check required categories
    source_types = [s["source_type"] for s in collector.registry_sources]
    assert source_types.count("vendor_blog") == 3
    assert "filing" in source_types
    assert "analyst_survey" in source_types

    # Verify every source has verified terms
    for s in collector.registry_sources:
        assert collector.verify_source_terms(s), f"Source {s['id']} missing valid terms note"


def test_search_log_proves_searched_nothing_found(enterprise_env):
    collector, db_path = enterprise_env
    repo = LedgerRepository(db_path=db_path)

    question = Question(
        id="q-kiro-enterprise",
        text="What are enterprise delivery results from Amazon Kiro?",
        scope="kiro",
        time_window_months=24,
    )
    repo.insert_question(question)

    # Search with no matching items (0 results returned)
    claims = collector.search_and_ingest(
        question=question,
        query="Amazon Kiro multi-vendor case studies",
        run_id="run_test_empty",
        feed_data_override={},
    )
    assert len(claims) == 0

    # Verify search_log contains records with result_count = 0
    with repo._conn() as conn:
        cursor = conn.execute("SELECT * FROM search_log WHERE question_id = 'q-kiro-enterprise';")
        logs = cursor.fetchall()
        assert len(logs) == 5, f"Expected 5 search_log entries, found {len(logs)}"
        for log in logs:
            assert log["result_count"] == 0
            assert log["lane"] == "enterprise"
            assert log["query"] == "Amazon Kiro multi-vendor case studies"


def test_enterprise_claims_carry_stake_and_vendor_grade(enterprise_env):
    collector, db_path = enterprise_env
    repo = LedgerRepository(db_path=db_path)

    question = Question(
        id="q-ai-dev",
        text="What are enterprise adoption patterns for AI coding tools?",
        scope="enterprise",
        time_window_months=24,
    )
    repo.insert_question(question)

    # Feed data with vendor blog assertion
    feed_override = {
        "aws-dev-blog": [
            {
                "title": "Scaling Software Delivery with Autonomous Coding",
                "text": "The service automatically simplifies multi-tier cloud application development.",
                "year": 2026,
                "speaker": "vendor",
            }
        ],
        "dora-dev-survey": [
            {
                "title": "2025 State of DevOps Report",
                "text": "Teams adopting specification guardrails saw a 12% increase in deployment stability.",
                "year": 2025,
                "speaker": "independent",
            }
        ],
    }

    claims = collector.search_and_ingest(
        question=question,
        query="AI coding tool adoption",
        run_id="run_feed_1",
        feed_data_override=feed_override,
    )
    assert len(claims) > 0

    # Vendor claim must be graded 'vendor_claim'
    vendor_claims = [c for c in claims if c.context_json.get("source_stake") == "vendor"]
    assert len(vendor_claims) > 0
    for vc in vendor_claims:
        assert vc.grade == "vendor_claim", f"Expected vendor claim to have grade 'vendor_claim', got '{vc.grade}'"
        assert vc.context_json.get("speaker") == "vendor"

    # Independent survey claim should have higher grade (moderate/strong)
    indep_claims = [c for c in claims if c.context_json.get("speaker") == "independent"]
    assert len(indep_claims) > 0
    for ic in indep_claims:
        assert ic.grade in ("moderate", "strong"), f"Expected independent survey claim to be moderate/strong, got '{ic.grade}'"
