"""Practitioner Lane Collector for Research Engine v2 (Phase 5).

Manages practitioner delivery observations strictly inside a dedicated SQLite
database (ledger/practitioner.db).

Constraints enforced:
1. Physical isolation: practitioner data is saved strictly to practitioner.db,
   which is gitignored.
2. Local only: Practitioner data never leaves the machine or reaches any remote service.
3. Abstraction protocol: Structured fields require abstraction confirmation before
   Gate 6 export.
4. Grade rules: Grade defaults to 'anecdote'. Observations count records repeat sightings
   but never lifts the grade on its own.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, Question, Review, Source
from src.ledger.repository import LedgerRepository

logger = logging.getLogger(__name__)


class PractitionerCollector:
    def __init__(
        self,
        db_path: str = "ledger/practitioner.db",
        migrations_dir: str = "ledger/migrations",
    ):
        self.db_path = db_path
        self.migrations_dir = migrations_dir
        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # Apply forward migrations to practitioner.db to keep durable schema identical to ledger.db
        apply_migrations(db_path=self.db_path, migrations_dir=self.migrations_dir)
        self.repo = LedgerRepository(db_path=self.db_path)

    def add_observation(
        self,
        question_id: str,
        situation: str,
        decision: str,
        action: str,
        outcome: str,
        sector: str,
        date: Optional[str] = None,
        metric: Optional[Dict[str, Any]] = None,
        abstraction_confirmed: bool = False,
        observations_count: int = 1,
        entity: Optional[str] = None,
        entity_match: str = "topic_level",
    ) -> Tuple[Source, Claim]:
        """Record an isolated practitioner observation with structured fields."""
        # 0. Ensure question exists to satisfy foreign key constraint
        if question_id and not self.repo.get_question(question_id):
            self.repo.insert_question(
                Question(
                    id=question_id,
                    text=question_id,
                    scope="practitioner",
                    time_window_months=24,
                    status="active",
                    version=1,
                )
            )
        obs_date = date or datetime.date.today().isoformat()
        src_id = f"src_prac_{uuid.uuid4().hex[:10]}"
        claim_id = f"claim_prac_{uuid.uuid4().hex[:10]}"

        # 1. Create Practitioner Source
        source = Source(
            id=src_id,
            lane="practitioner",
            source_type="practitioner_note",
            org=f"Practitioner Field Note ({sector})",
            title=f"Delivery Field Observation: {sector.capitalize()} ({obs_date})",
            venue="Practitioner Delivery Log",
            venue_tier="n/a",
            pub_date=obs_date,
            commercial_stake="none",
            extraction_depth="structured_data",
            status="active",
        )
        self.repo.insert_source(source)

        # 2. Formulate paraphrased atomic assertion
        paraphrased_text = (
            f"Practitioner field experience in {sector} indicates that "
            f"when addressing {situation.lower().rstrip('.')}, {action.lower().rstrip('.')} resulted in {outcome.lower().rstrip('.')}."
        )

        excerpt_summary = f"{situation[:50]} -> {action[:50]} -> {outcome[:50]}"
        # Ensure excerpt is max 25 words
        excerpt_words = excerpt_summary.split()
        if len(excerpt_words) > 25:
            excerpt_summary = " ".join(excerpt_words[:25])

        context_payload = {
            "situation": situation,
            "decision": decision,
            "action": action,
            "outcome": outcome,
            "sector": sector,
            "lane": "practitioner",
            "abstraction_confirmed": abstraction_confirmed,
            "metric": metric,
        }

        # 3. Create Claim
        # Grade strictly defaults to 'anecdote'
        claim = Claim(
            id=claim_id,
            question_id=question_id,
            source_id=src_id,
            text=paraphrased_text,
            source_excerpt=excerpt_summary,
            value_json=metric,
            entity=entity or "Enterprise Delivery",
            entity_match=entity_match,  # type: ignore
            study_type="practitioner_observation",
            context_json=context_payload,
            claim_date=obs_date,
            extraction_confidence=1.0,
            grade="anecdote",
            grade_reasons_json=[
                "practitioner lane",
                f"observations_count: {observations_count}",
                f"abstraction_confirmed: {abstraction_confirmed}",
            ],
            status="auto",
            observations_count=observations_count,
        )
        self.repo.insert_claim(claim)

        logger.info(
            f"Recorded practitioner observation {claim_id} for question {question_id} (abstraction: {abstraction_confirmed})"
        )
        return source, claim

    def list_observations(self, question_id: Optional[str] = None) -> List[Claim]:
        """List practitioner claims from practitioner.db."""
        return self.repo.list_claims(question_id=question_id)

    def export_abstracted_claim_to_ledger(
        self,
        claim_id: str,
        ledger_repo: LedgerRepository,
        reviewer: str = "human_operator",
    ) -> Claim:
        """Promote an abstracted practitioner claim into the shared ledger (Gate 6 Abstraction Gate).
        
        Strictly BLOCKS promotion if abstraction_confirmed is False.
        """
        claim = self.repo.get_claim(claim_id)
        if not claim:
            raise ValueError(f"Practitioner claim {claim_id} not found in practitioner.db")

        source = self.repo.get_source(claim.source_id)
        if not source:
            raise ValueError(f"Practitioner source {claim.source_id} not found in practitioner.db")

        # GATE 6 ABSTRACTION CHECK
        is_abstracted = bool(claim.context_json and claim.context_json.get("abstraction_confirmed") is True)
        if not is_abstracted:
            raise PermissionError(
                f"Gate 6 Abstraction Violation: Practitioner claim '{claim_id}' cannot be exported "
                "because abstraction_confirmed is False. Confirm removal of client and project names."
            )

        # Insert source into shared ledger
        ledger_repo.insert_source(source)
        # Ensure question exists in target ledger to satisfy foreign key constraint
        if claim.question_id and not ledger_repo.get_question(claim.question_id):
            q_src = self.repo.get_question(claim.question_id)
            if q_src:
                ledger_repo.insert_question(q_src)
        # Insert claim into shared ledger
        ledger_repo.insert_claim(claim)
        # Audit review
        ledger_repo.insert_review(
            Review(
                id=f"rev_{uuid.uuid4().hex[:10]}",
                gate="Gate 6",
                object_type="claim",
                object_id=claim.id,
                action="export_practitioner_claim",
                before_json=None,
                after_json={"claim_id": claim.id, "abstraction_confirmed": True},
                reason="Abstracted practitioner claim exported to main ledger",
                reviewer=reviewer,
            )
        )

        return claim
