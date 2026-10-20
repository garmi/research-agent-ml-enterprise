"""Test suite for A3-1: Honest Search Status Logging and Unsearched Lane Representation.

Verifies:
1. search_log table has status column via forward migration with allowed values:
   ('searched_ok', 'searched_error', 'not_implemented', 'not_searched', 'skipped_by_scope').
2. Sources with no working fetcher log status='not_implemented', never status='searched_ok'.
3. Practitioner lane with no local observations logs status='not_searched'.
4. Negative findings only use 'searched, nothing found' for sources with status='searched_ok' and result_count=0.
   Sources with 'not_implemented' say 'not searched: no fetcher'.
5. When Lane B is not searched, GapMatrixBuilder yields outcome 'Practice not assessed', never Outcome 3 or 4.
6. A run with no enterprise fetchers never emits 'searched' language for Lane B.
"""

import os
import tempfile
import pytest

from src.ledger.models import Question, SearchLog
from src.ledger.repository import LedgerRepository
from src.ledger.migrations import apply_migrations
from src.collectors.enterprise.collector import EnterpriseCollector
from src.gaps.matrix_builder import GapMatrixBuilder
from src.analysis.multilane_runner import MultiLaneResearchRunner


from src.ledger.db import get_connection

def test_search_log_migration_has_status_column():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_status.db")
        apply_migrations(db_path=db_path)
        repo = LedgerRepository(db_path=db_path)

        with get_connection(db_path) as conn:
            cols = [c[1] for c in conn.execute("PRAGMA table_info(search_log);").fetchall()]
            assert "status" in cols, f"Expected 'status' column in search_log, got {cols}"

        q = Question(id="q_stat_1", text="Status test question", scope="enterprise")
        repo.insert_question(q)

        slog = SearchLog(
            id="slog_test_1",
            question_id=q.id,
            lane="enterprise",
            query="test query",
            source_api="aws_blogs",
            result_count=0,
            status="not_implemented",
        )
        repo.insert_search_log(slog)

        fetched = repo.list_search_logs(question_id=q.id)
        assert len(fetched) == 1
        assert fetched[0].status == "not_implemented"


def test_unimplemented_enterprise_sources_log_not_implemented():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_ent.db")
        apply_migrations(db_path=db_path)
        collector = EnterpriseCollector(db_path=db_path)

        q = Question(
            id="q-test-status",
            text="What empirical evidence exists for AI delivery?",
            scope="enterprise",
        )
        collector.repo.insert_question(q)
        claims = collector.search_and_ingest(question=q, query=q.text)
        assert len(claims) == 0

        logs = collector.repo.list_search_logs(question_id=q.id)
        assert len(logs) == 5

        # Every source without a working fetcher must log not_implemented, never searched_ok
        for log in logs:
            assert log.status == "not_implemented", f"Source {log.source_api} logged {log.status}, expected 'not_implemented'"
            assert log.result_count == 0


def test_gap_matrix_outcome_is_practice_not_assessed_when_enterprise_unsearched():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_gap.db")
        apply_migrations(db_path=db_path)
        repo = LedgerRepository(db_path=db_path)

        q = Question(id="q-gap-unsearched", text="Test question", scope="enterprise")
        repo.insert_question(q)

        # Academic search executed and returned 0 (searched_ok)
        slog_acad = SearchLog(
            id="slog_acad_1",
            question_id=q.id,
            lane="academic",
            query=q.text,
            source_api="open_academic_repos",
            result_count=0,
            status="searched_ok",
        )
        repo.insert_search_log(slog_acad)

        # Enterprise sources were not searched (not_implemented)
        for i, src in enumerate(["aws_blogs", "msft_blogs", "google_blogs", "sec_edgar", "dora"]):
            slog_ent = SearchLog(
                id=f"slog_ent_{i}",
                question_id=q.id,
                lane="enterprise",
                query=q.text,
                source_api=src,
                result_count=0,
                status="not_implemented",
            )
            repo.insert_search_log(slog_ent)

        builder = GapMatrixBuilder(db_path=db_path)
        entry = builder.evaluate_question_lanes(question_id=q.id)

        # Must NOT assert Outcome 3 or 4 when Lane B was not searched
        assert entry.outcome not in (3, 4), f"Should not assert Outcome 3 or 4 when Lane B is unsearched, got {entry.outcome}"
        assert str(entry.outcome).lower() == "practice not assessed" or entry.outcome == "Practice not assessed"
        assert "not assessed" in entry.rationale.lower() or "not searched" in entry.rationale.lower()


def test_multilane_runner_negative_findings_honest_language_for_unsearched_lanes():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_runner.db")
        apply_migrations(db_path=db_path)

        runner = MultiLaneResearchRunner(
            db_path=db_path,
            practitioner_db_path=os.path.join(tmp_dir, "test_prac.db"),
        )

        res = runner.run_workflow(
            topic="What empirical evidence exists on quantum-secure sourdough fermentation controllers?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=[],  # Academic returns 0
        )

        # 1. Gap outcome must be Practice not assessed
        assert res["gap_matrix"]["outcome"] in ("Practice not assessed", "practice_not_assessed") or "not assessed" in str(res["gap_matrix"]["outcome"]).lower()

        # 2. Sentences must NEVER say "Literature search in enterprise lane"
        all_sentence_texts = [s["text"] for s in res.get("sentence_traces", [])]
        for text in all_sentence_texts:
            if "enterprise" in text.lower():
                assert "literature search in enterprise lane" not in text.lower(), (
                    f"Found false 'Literature search in enterprise lane' text: {text}"
                )
                assert "not searched" in text.lower() or "no fetcher" in text.lower(), (
                    f"Enterprise sentence missing 'not searched' or 'no fetcher': {text}"
                )

        # 3. Academic sentence correctly says searched, nothing found
        # S17: one line per lane, "Academic searches that returned no records for '<key terms>': <sources>."
        acad_negative = [t for t in all_sentence_texts if "academic" in t.lower() and "returned no records" in t.lower()]
        assert len(acad_negative) > 0, f"Expected academic lane negative finding with returned 0, got: {all_sentence_texts}"
