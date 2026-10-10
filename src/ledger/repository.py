"""Repository layer for interacting with SQLite ledger database."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

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

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    # --- Questions ---
    def insert_question(self, q: Question) -> None:
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

    # --- Reviews (Append-only audit) ---
    def insert_review(self, r: Review) -> None:
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
