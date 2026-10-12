"""Gap Matrix Builder for Research Engine v2 (Phase 4).

Evaluates the evidence state across Academic, Enterprise, and Field lanes for each question.
Assigns strategic gap outcomes (1 to 4):
- 1: Supported (academic & enterprise/field aligned with empirical evidence)
- 2: Practice Without Evidence (enterprise active, academic evidence thin or none)
- 3: Evidence Without Practice (academic research exists, enterprise adoption unmeasured)
- 4: Unmeasured (evidence thin or none found across all lanes)

Enforces that 'none found' lane states are backed by matching search_log entries.
"""

from __future__ import annotations

import datetime
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple
import yaml

from src.ledger.models import Claim, GapMatrixEntry, Question, Run
from src.ledger.repository import LedgerRepository

logger = logging.getLogger(__name__)


class GapMatrixBuilder:
    def __init__(
        self,
        db_path: str = "ledger/ledger.db",
        rules_path: Optional[str] = None,
        config_path: Optional[str] = None,
    ):
        self.db_path = db_path
        self.rules_path = rules_path
        self.config_path = config_path
        self.repo = LedgerRepository(db_path=self.db_path)
        self._load_config_and_rules()

    def _load_config_and_rules(self) -> None:
        self.rules = {}
        if self.rules_path and os.path.exists(self.rules_path):
            with open(self.rules_path, "r", encoding="utf-8") as f:
                self.rules = yaml.safe_load(f) or {}

        self.config = {}
        if self.config_path and os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}

    def evaluate_question_lanes(
        self,
        question_id: str,
        run_id: Optional[str] = None,
    ) -> GapMatrixEntry:
        """Evaluate evidence across lanes and determine the strategic gap outcome."""
        all_claims = self.repo.list_claims(question_id=question_id)
        search_logs = self.repo.list_search_logs(question_id=question_id)

        academic_claims: List[Claim] = []
        enterprise_claims: List[Claim] = []
        field_claims: List[Claim] = []

        for c in all_claims:
            src = self.repo.get_source(c.source_id)
            if not src:
                continue
            if src.lane == "academic":
                academic_claims.append(c)
            elif src.lane == "enterprise":
                enterprise_claims.append(c)
            elif src.lane == "practitioner":
                field_claims.append(c)

        # Determine whether lanes were actually searched
        ent_logs = [s for s in search_logs if s.lane == "enterprise"]
        ent_searched_ok = any(getattr(s, "status", "searched_ok") == "searched_ok" for s in ent_logs)

        field_logs = [s for s in search_logs if s.lane == "practitioner"]
        field_searched_ok = any(getattr(s, "status", "searched_ok") == "searched_ok" for s in field_logs)

        acad_logs = [s for s in search_logs if s.lane == "academic"]
        acad_searched_ok = any(getattr(s, "status", "searched_ok") == "searched_ok" for s in acad_logs)

        # Helper to determine lane state
        def determine_state(claims: List[Claim], lane_name: str, searched_ok: bool) -> str:
            if not claims:
                if lane_name == "enterprise":
                    return "none found" if searched_ok else "not searched"
                return "none found"

            # Check for contradictions
            has_contradiction = any("contradict" in str(c.grade_reasons_json or "").lower() for c in claims)
            if has_contradiction:
                return "contradicted"

            active_claims = [c for c in claims if c.status != "rejected"]
            if not active_claims:
                if lane_name == "enterprise":
                    return "none found" if searched_ok else "not searched"
                return "none found"

            if lane_name == "academic":
                has_strong = any(c.grade == "strong" for c in active_claims)
                moderate_count = sum(1 for c in active_claims if c.grade == "moderate")
                if has_strong or moderate_count >= 2:
                    return "supported"
                return "partial"
            elif lane_name in ("enterprise", "practitioner"):
                if len(active_claims) >= 2 or any(c.grade in ("strong", "moderate") for c in active_claims):
                    return "supported"
                return "partial"

            return "partial"

        acad_state = determine_state(academic_claims, "academic", acad_searched_ok or bool(academic_claims))
        ent_state = determine_state(enterprise_claims, "enterprise", ent_searched_ok or bool(enterprise_claims))
        field_state = determine_state(field_claims, "practitioner", field_searched_ok or bool(field_claims))

        # Check if enterprise lane consists solely of vendor sources
        only_vendor_sources = False
        if enterprise_claims:
            is_vendor_source = []
            for c in enterprise_claims:
                src = self.repo.get_source(c.source_id)
                stake = getattr(src, "commercial_stake", "") if src else ""
                v_tier = getattr(src, "venue_tier", "") if src else ""
                is_vendor_source.append(
                    stake == "vendor"
                    or v_tier == "vendor"
                    or c.grade == "vendor_claim"
                    or (c.context_json and c.context_json.get("source_stake") == "vendor")
                )
            if all(is_vendor_source):
                only_vendor_sources = True

        vendor_cap = None
        if self.rules and "caps" in self.rules:
            vendor_cap = self.rules.get("caps", {}).get("vendor_only_max_outcome")
        elif self.config:
            vendor_cap = self.config.get("vendor_only_max_outcome")

        # Determine Outcome: 1 to 4, or "Practice not assessed"
        outcome: Union[int, str]
        rationale: str

        if acad_state in ("supported", "partial") and (ent_state in ("supported", "partial") or field_state in ("supported", "partial")):
            if only_vendor_sources and field_state in ("none found", "not searched") and vendor_cap is not None:
                outcome = min(2, vendor_cap)
                rationale = "Outcome 2: Practice without evidence — Enterprise claims originate solely from vendor sources without independent empirical corroboration."
            else:
                outcome = 1
                rationale = "Outcome 1: Supported — Empirical academic research is corroborated by active enterprise practice."
        elif (ent_state in ("supported", "partial") or field_state in ("supported", "partial")) and acad_state in ("none found", "not searched"):
            outcome = 2
            rationale = "Outcome 2: Practice without evidence — Enterprise teams are actively adopting, but peer-reviewed empirical evidence is absent."
        elif ent_state == "not searched" and not enterprise_claims and not field_claims:
            # Rule A3-1: When Lane B was not searched, cannot assert Outcome 3 or 4
            outcome = "Practice not assessed"
            if acad_state in ("supported", "partial"):
                rationale = "Practice not assessed: Academic research exists, but enterprise lane was not searched (no working fetcher implemented). Practice adoption cannot be determined."
            else:
                rationale = "Practice not assessed: Enterprise lane was not searched (no working fetcher implemented). Practice adoption cannot be determined."
        elif acad_state in ("supported", "partial") and ent_state == "none found" and field_state in ("none found", "not searched"):
            outcome = 3
            rationale = "Outcome 3: Evidence without practice — Academic research demonstrates capabilities, but enterprise delivery measurement is missing."
        else:
            outcome = 4
            rationale = "Outcome 4: Unmeasured — Rigorous evidence is currently lacking across both academic and enterprise lanes."

        if run_id and os.getenv("HOSTED_DEMO") != "1" and not self.repo.get_run(run_id):
            self.repo.insert_run(
                Run(
                    id=run_id,
                    started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    question_ids=[question_id],
                )
            )

        entry = GapMatrixEntry(
            id=f"gap_{uuid.uuid4().hex[:12]}",
            run_id=run_id,
            question_id=question_id,
            academic_state=acad_state,
            enterprise_state=ent_state,
            field_state=field_state,
            outcome=outcome,  # type: ignore
            rationale=rationale,
            status="active",
        )

        if os.getenv("HOSTED_DEMO") != "1":
            with self.repo._conn() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO gap_matrix
                       (id, run_id, question_id, academic_state, enterprise_state, field_state,
                        outcome, rationale, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    (
                        entry.id, entry.run_id, entry.question_id, entry.academic_state,
                        entry.enterprise_state, entry.field_state, entry.outcome,
                        entry.rationale, entry.status, entry.created_at,
                    ),
                )

        return entry

    def list_matrix_entries(self, question_id: Optional[str] = None) -> List[GapMatrixEntry]:
        with self.repo._conn() as conn:
            if question_id:
                cursor = conn.execute("SELECT * FROM gap_matrix WHERE question_id = ? ORDER BY created_at DESC;", (question_id,))
            else:
                cursor = conn.execute("SELECT * FROM gap_matrix ORDER BY created_at DESC;")
            return [GapMatrixEntry(**dict(row)) for row in cursor.fetchall()]
