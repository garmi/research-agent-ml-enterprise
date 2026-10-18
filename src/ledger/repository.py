"""Repository layer for interacting with SQLite ledger database."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from src.ledger.db import get_connection
from src.ledger.models import (
    Claim,
    ClaimLink,
    GapMatrixEntry,
    OutputDoc,
    OutputSentence,
    Question,
    Review,
    Run,
    SearchLog,
    Source,
)


class LedgerRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def _check_write_permission(self) -> None:
        if os.getenv("HOSTED_DEMO") == "1":
            raise PermissionError("Ledger writes are disabled in hosted demo mode: no private data is stored.")

    def _conn(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='questions';")
        if not cur.fetchone():
            conn.close()
            from src.ledger.db import default_ledger_path
            from src.ledger.migrations import apply_migrations
            apply_migrations(db_path=self.db_path or default_ledger_path())
            conn = get_connection(self.db_path)
        return conn

    # --- Questions ---
    def insert_question(self, q: Question) -> None:
        self._check_write_permission()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO questions 
                   (id, text, scope, time_window_months, status, version, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?);""",
                (q.id, q.text, q.scope, q.time_window_months, q.status, q.version, q.created_at),
            )

    def get_question(self, q_id: str) -> Optional[Question]:
        with self._conn() as conn:
            cursor = conn.execute("SELECT * FROM questions WHERE id = ?;", (q_id,))
            row = cursor.fetchone()
            if row:
                return Question(**dict(row))
            return None

    def list_questions(self, status: Optional[str] = None) -> List[Question]:
        with self._conn() as conn:
            if status:
                cursor = conn.execute("SELECT * FROM questions WHERE status = ?;", (status,))
            else:
                cursor = conn.execute("SELECT * FROM questions;")
            return [Question(**dict(row)) for row in cursor.fetchall()]

    # --- Sources ---
    def insert_source(self, s: Source) -> None:
        self._check_write_permission()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sources
                   (id, lane, source_type, org, title, url, doi, venue, venue_tier,
                    pub_date, retrieved_at, content_hash, extraction_depth,
                    commercial_stake, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                (
                    s.id, s.lane, s.source_type, s.org, s.title, s.url, s.doi, s.venue,
                    s.venue_tier, s.pub_date, s.retrieved_at, s.content_hash,
                    s.extraction_depth, s.commercial_stake, s.status, s.created_at,
                ),
            )

    def get_source(self, s_id: str) -> Optional[Source]:
        with self._conn() as conn:
            cursor = conn.execute("SELECT * FROM sources WHERE id = ?;", (s_id,))
            row = cursor.fetchone()
            if row:
                return Source(**dict(row))
            return None

    def list_sources(self, lane: Optional[str] = None) -> List[Source]:
        with self._conn() as conn:
            if lane:
                cursor = conn.execute("SELECT * FROM sources WHERE lane = ?;", (lane,))
            else:
                cursor = conn.execute("SELECT * FROM sources;")
            return [Source(**dict(row)) for row in cursor.fetchall()]

    # --- Claims ---
    def insert_claim(self, c: Claim) -> None:
        self._check_write_permission()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO claims
                   (id, question_id, source_id, text, source_excerpt, value_json,
                    entity, entity_match, study_type, context_json, claim_date,
                    extraction_model, extraction_confidence, grade, grade_reasons_json,
                    status, observations_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                (
                    c.id, c.question_id, c.source_id, c.text, c.source_excerpt,
                    json.dumps(c.value_json) if c.value_json is not None else None,
                    c.entity, c.entity_match, c.study_type,
                    json.dumps(c.context_json) if c.context_json is not None else None,
                    c.claim_date, c.extraction_model, c.extraction_confidence,
                    c.grade,
                    json.dumps(c.grade_reasons_json) if c.grade_reasons_json is not None else None,
                    c.status, c.observations_count, c.created_at,
                ),
            )

    def get_claim(self, c_id: str) -> Optional[Claim]:
        with self._conn() as conn:
            cursor = conn.execute("SELECT * FROM claims WHERE id = ?;", (c_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("value_json"):
                d["value_json"] = json.loads(d["value_json"])
            if d.get("context_json"):
                d["context_json"] = json.loads(d["context_json"])
            if d.get("grade_reasons_json"):
                d["grade_reasons_json"] = json.loads(d["grade_reasons_json"])
            return Claim(**d)

    def list_claims(self, question_id: Optional[str] = None) -> List[Claim]:
        with self._conn() as conn:
            if question_id:
                cursor = conn.execute("SELECT * FROM claims WHERE question_id = ?;", (question_id,))
            else:
                cursor = conn.execute("SELECT * FROM claims;")
            claims = []
            for row in cursor.fetchall():
                d = dict(row)
                if d.get("value_json"):
                    d["value_json"] = json.loads(d["value_json"])
                if d.get("context_json"):
                    d["context_json"] = json.loads(d["context_json"])
                if d.get("grade_reasons_json"):
                    d["grade_reasons_json"] = json.loads(d["grade_reasons_json"])
                claims.append(Claim(**d))
            return claims

    # --- Search Log ---
    def insert_search_log(self, log: SearchLog) -> None:
        self._check_write_permission()
        with self._conn() as conn:
            details_str = json.dumps(log.details_json) if log.details_json else None
            columns = [c[1] for c in conn.execute("PRAGMA table_info(search_log);").fetchall()]
            log_status = getattr(log, "status", "searched_ok") or "searched_ok"
            if "status" in columns and "rejected_reason" in columns:
                conn.execute(
                    """INSERT OR REPLACE INTO search_log
                       (id, run_id, question_id, lane, query, source_api, result_count, status, executed_at, created_at, rejected_reason, details_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    (
                        log.id, log.run_id, log.question_id, log.lane, log.query,
                        log.source_api, log.result_count, log_status, log.executed_at, log.created_at,
                        log.rejected_reason, details_str,
                    ),
                )
            elif "rejected_reason" in columns:
                conn.execute(
                    """INSERT OR REPLACE INTO search_log
                       (id, run_id, question_id, lane, query, source_api, result_count, executed_at, created_at, rejected_reason, details_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    (
                        log.id, log.run_id, log.question_id, log.lane, log.query,
                        log.source_api, log.result_count, log.executed_at, log.created_at,
                        log.rejected_reason, details_str,
                    ),
                )
            else:
                conn.execute(
                    """INSERT OR REPLACE INTO search_log
                       (id, run_id, question_id, lane, query, source_api, result_count, executed_at, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    (
                        log.id, log.run_id, log.question_id, log.lane, log.query,
                        log.source_api, log.result_count, log.executed_at, log.created_at,
                    ),
                )

    def list_search_logs(self, question_id: Optional[str] = None) -> List[SearchLog]:
        with self._conn() as conn:
            if question_id:
                cursor = conn.execute("SELECT * FROM search_log WHERE question_id = ? ORDER BY executed_at DESC;", (question_id,))
            else:
                cursor = conn.execute("SELECT * FROM search_log ORDER BY executed_at DESC;")
            logs = []
            for row in cursor.fetchall():
                d = dict(row)
                if not d.get("status"):
                    d["status"] = "searched_ok"
                if d.get("details_json") and isinstance(d["details_json"], str):
                    try:
                        d["details_json"] = json.loads(d["details_json"])
                    except Exception:
                        pass
                logs.append(SearchLog(**d))
            return logs

    # --- Runs ---
    def insert_run(self, run: Run) -> None:
        self._check_write_permission()
        with self._conn() as conn:
            # Upsert so a re-insert (e.g. adding config_json) never wipes runs.status.
            conn.execute(
                """INSERT INTO runs
                   (id, started_at, config_json, code_version, model_ids, question_ids, seed, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     started_at = excluded.started_at,
                     config_json = excluded.config_json,
                     code_version = excluded.code_version,
                     model_ids = excluded.model_ids,
                     question_ids = excluded.question_ids,
                     seed = excluded.seed;""",
                (
                    run.id, run.started_at,
                    json.dumps(run.config_json) if run.config_json else None,
                    run.code_version,
                    json.dumps(run.model_ids) if run.model_ids else None,
                    json.dumps(run.question_ids) if run.question_ids else None,
                    run.seed, run.created_at,
                ),
            )

    def get_run(self, run_id: str) -> Optional[Run]:
        with self._conn() as conn:
            cursor = conn.execute("SELECT * FROM runs WHERE id = ?;", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("config_json"):
                d["config_json"] = json.loads(d["config_json"])
            if d.get("model_ids"):
                d["model_ids"] = json.loads(d["model_ids"])
            if d.get("question_ids"):
                d["question_ids"] = json.loads(d["question_ids"])
            return Run(**d)

    def set_run_status(self, run_id: str, status: str, reason: Optional[str] = None) -> None:
        """Persist the run-level status (RUNNING, NOT_PUBLISHABLE, BLOCKED, ...) on the runs row."""
        self._check_write_permission()
        with self._conn() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, status_reason = ? WHERE id = ?;",
                (str(status).upper(), reason, run_id),
            )

    def get_run_status(self, run_id: str) -> Tuple[Optional[str], Optional[str]]:
        with self._conn() as conn:
            row = conn.execute("SELECT status, status_reason FROM runs WHERE id = ?;", (run_id,)).fetchone()
            if not row:
                return None, None
            return row["status"], row["status_reason"]

    def reject_claims(self, claim_ids: List[str]) -> None:
        """Mark claims as rejected (kept for audit, excluded from findings)."""
        if not claim_ids:
            return
        self._check_write_permission()
        with self._conn() as conn:
            conn.executemany("UPDATE claims SET status = 'rejected' WHERE id = ?;", [(cid,) for cid in claim_ids])

    # --- Handoff check verdicts ---
    def insert_check_verdict(self, row: Dict[str, Any]) -> None:
        self._check_write_permission()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO check_verdicts
                   (id, check_id, run_id, object_type, object_id, model_verdict, rule_verdict,
                    rule_decisive, final, reason_plain, attempt, model_id, prompt_hash, details_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                (
                    row["id"], row["check_id"], row["run_id"], row["object_type"], row["object_id"],
                    row.get("model_verdict"), row.get("rule_verdict"), int(bool(row.get("rule_decisive"))),
                    row["final"], row["reason_plain"], int(row.get("attempt", 0)),
                    row.get("model_id"), row.get("prompt_hash"),
                    json.dumps(row["details_json"]) if row.get("details_json") is not None else None,
                    row["created_at"],
                ),
            )

    def list_check_verdicts(self, run_id: str, check_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            if check_id:
                cursor = conn.execute(
                    "SELECT * FROM check_verdicts WHERE run_id = ? AND check_id = ? ORDER BY created_at, rowid;",
                    (run_id, check_id),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM check_verdicts WHERE run_id = ? ORDER BY created_at, rowid;", (run_id,)
                )
            rows = []
            for r in cursor.fetchall():
                d = dict(r)
                d["rule_decisive"] = bool(d.get("rule_decisive"))
                if d.get("details_json"):
                    d["details_json"] = json.loads(d["details_json"])
                rows.append(d)
            return rows

    # --- Reviews (Append-only audit) ---
    def insert_review(self, r: Review) -> None:
        self._check_write_permission()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO reviews
                   (id, gate, object_type, object_id, action, before_json, after_json,
                    reason, reviewer, ts, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                (
                    r.id, r.gate, r.object_type, r.object_id, r.action,
                    json.dumps(r.before_json) if r.before_json is not None else None,
                    json.dumps(r.after_json) if r.after_json is not None else None,
                    r.reason, r.reviewer, r.ts, r.created_at,
                ),
            )

    # --- Outputs and Sentences ---
    def insert_output(self, out: OutputDoc) -> None:
        self._check_write_permission()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO outputs
                   (id, run_id, kind, version, path, status, score_json, gates_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                (
                    out.id, out.run_id, out.kind, out.version, out.path, out.status,
                    json.dumps(out.score_json) if out.score_json is not None else None,
                    json.dumps(out.gates_json) if out.gates_json is not None else None,
                    out.created_at,
                ),
            )

    def insert_output_sentence(self, s: OutputSentence) -> None:
        self._check_write_permission()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO output_sentences
                   (id, output_id, ordinal, text, type, claim_ids_json, strength_verb, checks_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                (
                    s.id, s.output_id, s.ordinal, s.text, s.type,
                    json.dumps(s.claim_ids_json) if s.claim_ids_json is not None else None,
                    s.strength_verb,
                    json.dumps(s.checks_json) if s.checks_json is not None else None,
                    s.created_at,
                ),
            )

    def list_output_sentences(self, output_id: str) -> List[OutputSentence]:
        with self._conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM output_sentences WHERE output_id = ? ORDER BY ordinal ASC;",
                (output_id,),
            )
            res = []
            for row in cursor.fetchall():
                d = dict(row)
                if d.get("claim_ids_json"):
                    d["claim_ids_json"] = json.loads(d["claim_ids_json"])
                if d.get("checks_json"):
                    d["checks_json"] = json.loads(d["checks_json"])
                res.append(OutputSentence(**d))
            return res

    def get_output(self, output_id: str) -> Optional[OutputDoc]:
        with self._conn() as conn:
            cursor = conn.execute("SELECT * FROM outputs WHERE id = ?;", (output_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("score_json"):
                d["score_json"] = json.loads(d["score_json"])
            if d.get("gates_json"):
                d["gates_json"] = json.loads(d["gates_json"])
            return OutputDoc(**d)

    def list_outputs(self, run_id: Optional[str] = None) -> List[OutputDoc]:
        with self._conn() as conn:
            if run_id:
                cursor = conn.execute("SELECT * FROM outputs WHERE run_id = ? ORDER BY created_at DESC;", (run_id,))
            else:
                cursor = conn.execute("SELECT * FROM outputs ORDER BY created_at DESC;")
            res = []
            for row in cursor.fetchall():
                d = dict(row)
                if d.get("score_json"):
                    d["score_json"] = json.loads(d["score_json"])
                if d.get("gates_json"):
                    d["gates_json"] = json.loads(d["gates_json"])
                res.append(OutputDoc(**d))
            return res
