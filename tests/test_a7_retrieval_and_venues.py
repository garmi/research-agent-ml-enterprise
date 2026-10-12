"""Test A7: Retrieval quality, venue metadata honesty, and filtering.

Verifies:
1. Venue display shows actual venue name, NEVER the API provider (Crossref, Semantic Scholar).
2. Real source types: Peer-Reviewed Journal, Conference, Preprint (never blanket 'Open Pre-print').
3. Missing date renders 'Date unknown', never 'Published: None'.
4. Year filter enforced at retrieval time: papers with year < min_year (2020) are rejected and logged.
5. Off-topic papers rejected deterministically by term overlap and logged with rejected_reason.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.ledger.migrations import apply_migrations
from src.ledger.models import Question
from src.ledger.repository import LedgerRepository


def test_venue_never_displays_api_provider_and_real_source_types():
    """Verify venue never shows API provider name and real source types are assigned."""
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
            {
                "id": "p-crossref-01",
                "title": "Empirical Analysis of Autonomous Code Review",
                "abstract": "We evaluate automated code review agents across enterprise repositories.",
                "year": 2024,
                "venue": "Crossref",  # API provider name previously leaked as venue
                "source": "Crossref",
                "container_title": "IEEE Transactions on Software Engineering",
                "url": "https://doi.org/10.1109/TSE.2024.12345",
                "relevance_score": 0.95,
            },
            {
                "id": "p-arxiv-01",
                "title": "Benchmarking LLM Assisted Coding in Production",
                "abstract": "We measure task latency and code completions in production systems.",
                "year": 2023,
                "venue": "arXiv",
                "source": "arXiv",
                "url": "https://arxiv.org/abs/2301.00001",
                "relevance_score": 0.90,
            },
            {
                "id": "p-conf-01",
                "title": "Proceedings of the ACM Conference on Software Engineering",
                "abstract": "Controlled experiment measuring enterprise coding assistants and developer productivity.",
                "year": None,  # Missing date
                "venue": "ACM ICSE 2024 Conference Proceedings",
                "source": "OpenAlex",
                "url": "https://doi.org/10.1145/example",
                "relevance_score": 0.92,
            },
        ]

        results = runner.run_workflow(
            topic="How do AI coding assistants perform in enterprise production?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=test_papers,
        )

        papers = results["papers"]
        assert len(papers) == 3

        # 1. First paper must not show "Crossref" as venue
        p1 = papers[0]
        assert p1["venue"] != "Crossref", f"Venue must not be API provider name 'Crossref', got '{p1['venue']}'"
        assert "IEEE" in p1["venue"] or "Transactions" in p1["venue"], f"Expected real venue, got '{p1['venue']}'"
        assert p1["type"] in ("Peer-Reviewed Journal", "Peer-Reviewed Conference"), f"Expected Peer-Reviewed Journal/Conference, got {p1['type']}"
        assert p1["type"] != "Open Pre-print", "Must not blanket label journal paper as Open Pre-print"

        # 2. ArXiv paper must be Preprint
        p2 = papers[1]
        assert p2["type"] == "Preprint"
        assert p2["venue"] == "arXiv"

        # 3. Third paper: Missing year must not show 'None' or 'Published: None'
        p3 = papers[2]
        assert p3["year"] != "None", f"Missing year must not be string 'None', got '{p3['year']}'"
        assert p3["year"] in ("Date unknown", None), f"Expected 'Date unknown' or None, got '{p3['year']}'"
        assert p3["type"] in ("Conference", "Peer-Reviewed Conference")


def test_retrieval_filters_by_min_year_and_logs_rejected_stale_papers():
    """Verify papers older than min_year (2020) are excluded from ledger and logged to search_log."""
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

        mixed_papers = [
            {
                "id": "p-current-2024",
                "title": "Modern LLM Developer Velocity",
                "abstract": "Empirical metrics of modern generative assistant adoption.",
                "year": 2024,
                "venue": "ICSE",
                "url": "https://doi.org/10.1145/p2024",
                "relevance_score": 0.95,
            },
            {
                "id": "p-stale-2008",
                "title": "A 2008 Technology Acceptance Study of Legacy IDEs",
                "abstract": "We survey developers using early desktop IDE plugins in 2008.",
                "year": 2008,
                "venue": "Legacy Journal 2008",
                "url": "https://doi.org/10.1145/p2008",
                "relevance_score": 0.85,
            },
        ]

        results = runner.run_workflow(
            topic="What empirical evidence exists regarding AI coding assistant adoption?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=mixed_papers,
        )

        repo = LedgerRepository(db_path=db_path)

        # Stale paper must not be in ingested papers or ledger sources
        paper_ids = [p["id"] for p in results["papers"]]
        assert "p-stale-2008" not in paper_ids, "2008 paper must be rejected by min_year filter"
        assert "p-current-2024" in paper_ids

        ledger_sources = repo.list_sources()
        source_ids = [s.id for s in ledger_sources]
        assert "p-stale-2008" not in source_ids, "Rejected stale paper must not be inserted into sources"

        # Search log must record rejection
        search_logs = repo.list_search_logs()
        stale_rejections = [
            sl for sl in search_logs
            if sl.rejected_reason and "year" in sl.rejected_reason.lower()
        ]
        assert len(stale_rejections) > 0, "Expected search_log entry recording rejection due to year filter"


def test_retrieval_rejects_off_topic_papers_by_term_overlap():
    """Verify completely off-topic paper (e.g. OECD Trade Economics) is rejected and logged."""
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

        mixed_topic_papers = [
            {
                "id": "p-ontopic-01",
                "title": "Productivity and Velocity in Enterprise Software Teams using AI",
                "abstract": "Empirical measurement of developer productivity and velocity.",
                "year": 2024,
                "venue": "ICSE",
                "url": "https://doi.org/10.1145/ontopic",
                "relevance_score": 0.95,
            },
            {
                "id": "p-offtopic-oecd",
                "title": "OECD Trade Economics and Tariff Policies in Developing Nations",
                "abstract": "Macroeconomic review of grain tariffs, trade barriers, and fiscal balance in agriculture.",
                "year": 2023,
                "venue": "Journal of Agricultural Trade Economics",
                "url": "https://doi.org/10.1145/oecd",
                "relevance_score": 0.10,
            },
        ]

        results = runner.run_workflow(
            topic="What empirical evidence measures productivity and velocity in software engineering?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=mixed_topic_papers,
        )

        repo = LedgerRepository(db_path=db_path)

        # Off-topic paper must not be in ingested papers or ledger sources
        paper_ids = [p["id"] for p in results["papers"]]
        assert "p-offtopic-oecd" not in paper_ids, "Off-topic OECD trade paper must be rejected"

        ledger_sources = repo.list_sources()
        source_ids = [s.id for s in ledger_sources]
        assert "p-offtopic-oecd" not in source_ids, "Off-topic paper must not be inserted into sources"

        # Search log must record off-topic rejection
        search_logs = repo.list_search_logs()
        topic_rejections = [
            sl for sl in search_logs
            if sl.rejected_reason and ("topic" in sl.rejected_reason.lower() or "relevance" in sl.rejected_reason.lower())
        ]
        assert len(topic_rejections) > 0, "Expected search_log entry recording off-topic rejection"


def test_off_topic_filter_rejects_generic_trade_and_regulatory_papers_against_q1():
    """Verify generic research papers sharing only generic words are rejected with off_topic_low_relevance against Q1."""
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
            {
                "id": "p-trade-tam",
                "title": "An Empirical Study on the Information Productivity of Trade Practice for Technology Acceptance Model Adoption",
                "abstract": "We analyze technology acceptance model adoption in international trade practice and information productivity.",
                "year": 2024,
                "venue": "Journal of Trade Studies",
                "url": "https://doi.org/10.1000/trade-tam",
                "relevance_score": 0.88,
            },
            {
                "id": "p-trade-gains",
                "title": "Dissecting Productivity Gains from Trade",
                "abstract": "Econometric decomposition of manufacturing productivity gains resulting from bilateral tariff reductions.",
                "year": 2023,
                "venue": "Quarterly Journal of Economics",
                "url": "https://doi.org/10.1000/trade-gains",
                "relevance_score": 0.85,
            },
            {
                "id": "p-oecd-reforms",
                "title": "Figure 2.26. Regulatory reforms matter for digital adoption and productivity gains",
                "abstract": "Statistical chart showing OECD cross-country variance in digital adoption and productivity gains under regulatory reform.",
                "year": 2022,
                "venue": "OECD Digital Economy Outlook",
                "url": "https://doi.org/10.1000/oecd-2.26",
                "relevance_score": 0.80,
            },
            {
                "id": "p-kiro-genuine",
                "title": "Empirical Evaluation of Amazon Kiro and Generative Assistants in Software Delivery",
                "abstract": "Developer velocity increases by 32% with Amazon Kiro in standard software delivery tasks.",
                "year": 2024,
                "venue": "IEEE Transactions on Software Engineering",
                "url": "https://doi.org/10.1109/tse.2024",
                "relevance_score": 0.95,
            },
            {
                "id": "p-spec-driven",
                "title": "Spec-Driven Development for Generative Assistants in Enterprise Engineering",
                "abstract": "Bounded autonomy contracts and spec-driven development eliminate out-of-band regression in enterprise teams.",
                "year": 2024,
                "venue": "ACM Transactions on Software Engineering and Methodology",
                "url": "https://doi.org/10.1145/tosem.2024",
                "relevance_score": 0.93,
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

        # All 3 generic off-topic papers MUST be rejected
        assert "p-trade-tam" not in accepted_paper_ids, f"Trade TAM paper must be rejected, got accepted: {accepted_paper_ids}"
        assert "p-trade-gains" not in accepted_paper_ids, f"Trade gains paper must be rejected, got accepted: {accepted_paper_ids}"
        assert "p-oecd-reforms" not in accepted_paper_ids, f"OECD reforms paper must be rejected, got accepted: {accepted_paper_ids}"

        # Genuine Kiro and Spec-Driven papers MUST pass
        assert "p-kiro-genuine" in accepted_paper_ids, "Genuine Kiro paper must pass"
        assert "p-spec-driven" in accepted_paper_ids, "Spec-driven development paper must pass"

        # Search log must record off_topic_low_relevance for all three
        search_logs = repo.list_search_logs()
        rejected_logs = {
            sl.details_json.get("paper_id"): sl.rejected_reason
            for sl in search_logs
            if sl.details_json and "paper_id" in sl.details_json
        }
        for pid in ("p-trade-tam", "p-trade-gains", "p-oecd-reforms"):
            reason = rejected_logs.get(pid, "")
            assert "off_topic_low_relevance" in reason, f"Paper {pid} must have off_topic_low_relevance reason, got: {reason}"
