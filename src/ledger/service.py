"""In-process service layer for Research Engine v2 local frontend.

Binds to 127.0.0.1 and encapsulates:
- Gate 1: Question Register management and YAML synchronization.
- Gate 2: Venue and Source tiering, rules updating, and claim re-grading.
- Gate 3: Claim Review Queue with uncertainty sorting, review actions, and strict audit logging.
Every human interaction writes an append-only row to the `reviews` table.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import yaml

from src.grade.grader import Grader
from src.ledger.db import get_connection
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, Question, Review, Source, VenueTier
from src.ledger.repository import LedgerRepository

logger = logging.getLogger(__name__)


def generate_review_id() -> str:
    return f"rev_{uuid.uuid4().hex[:12]}"


def dump_model(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj.dict()


class LedgerService:
    def __init__(
        self,
        db_path: str = "ledger/ledger.db",
        questions_yaml_path: str = "questions/register.yaml",
        venue_tiers_yaml_path: str = "grade/venue_tiers.yaml",
        rules_yaml_path: str = "grade/rules.yaml",
    ):
        self.db_path = db_path
        self.questions_yaml_path = questions_yaml_path
        self.venue_tiers_yaml_path = venue_tiers_yaml_path
        self.rules_yaml_path = rules_yaml_path

        # Ensure schema is ready
        apply_migrations(db_path=self.db_path)
        self.repo = LedgerRepository(db_path=self.db_path)
        self.grader = Grader(
            rules_path=self.rules_yaml_path,
            venue_tiers_path=self.venue_tiers_yaml_path,
        )

    # =========================================================================
    # GATE 1: Question Register
    # =========================================================================
    def load_questions_from_yaml(self) -> List[Question]:
        """Parse questions from YAML register in memory without modifying the database."""
        if not os.path.exists(self.questions_yaml_path):
            return []

        with open(self.questions_yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        questions_data = data.get("questions", [])
        return [Question(**q_dict) for q_dict in questions_data]

    def sync_questions_from_yaml(self) -> List[Question]:
        """Load questions from YAML register into SQLite database (or return in-memory in hosted demo mode)."""
        questions = self.load_questions_from_yaml()
        if os.getenv("HOSTED_DEMO") == "1":
            return questions
        for q in questions:
            self.repo.insert_question(q)
        return questions

    def sync_questions_to_yaml(self) -> None:
        """Dump active questions from SQLite to YAML register."""
        questions = self.repo.list_questions()
        data = {"questions": [dump_model(q) for q in questions]}
        with open(self.questions_yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)

    def create_question(
        self,
        question_id: str,
        text: str,
        scope: str = "enterprise",
        time_window_months: int = 36,
        reviewer: str = "human_operator",
        reason: str = "Initial creation",
    ) -> Question:
        q = Question(
            id=question_id,
            text=text,
            scope=scope,
            time_window_months=time_window_months,
            status="active",
            version=1,
        )
        self.repo.insert_question(q)
        self.sync_questions_to_yaml()

        # Audit review log
        rev = Review(
            id=generate_review_id(),
            gate="G1",
            object_type="question",
            object_id=q.id,
            action="create_question",
            before_json=None,
            after_json=dump_model(q),
            reason=reason,
            reviewer=reviewer,
        )
        self.repo.insert_review(rev)
        return q

    def update_question_status(
        self,
        question_id: str,
        new_status: str,
        reviewer: str,
        reason: str,
    ) -> Optional[Question]:
        q = self.repo.get_question(question_id)
        if not q:
            return None
        before = dump_model(q)
        q.status = new_status  # type: ignore
        q.version += 1
        self.repo.insert_question(q)
        self.sync_questions_to_yaml()

        rev = Review(
            id=generate_review_id(),
            gate="G1",
            object_type="question",
            object_id=q.id,
            action="update_question_status",
            before_json=before,
            after_json=dump_model(q),
            reason=reason,
            reviewer=reviewer,
        )
        self.repo.insert_review(rev)
        return q

    # =========================================================================
    # GATE 2: Venue and Source Tiering
    # =========================================================================
    def list_venues(self) -> List[Dict[str, Any]]:
        """List distinct venues from sources with their current tiers and source counts."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT venue, venue_tier, COUNT(*) as source_count
                   FROM sources
                   GROUP BY venue, venue_tier
                   ORDER BY venue_tier ASC, source_count DESC;"""
            )
            return [dict(row) for row in cursor.fetchall()]

    def tier_venue(
        self,
        venue_name: str,
        new_tier: VenueTier,
        reviewer: str,
        reason: str,
    ) -> int:
        """Update a venue's tier in YAML and DB, then re-grade affected claims.

        Returns:
            Number of sources updated.
        """
        norm_venue = venue_name.strip().lower()

        # 1. Update YAML configuration
        with open(self.venue_tiers_yaml_path, "r", encoding="utf-8") as f:
            tiers_data = yaml.safe_load(f)

        # Remove from previous matches if present
        for tier_key in ["verified", "reputable_preprint", "unverified", "vendor"]:
            matches = tiers_data.get("tiers", {}).get(tier_key, {}).get("matches", [])
            if norm_venue in matches:
                matches.remove(norm_venue)

        # Add to new tier
        if new_tier in tiers_data.get("tiers", {}):
            matches = tiers_data["tiers"][new_tier].setdefault("matches", [])
            if norm_venue not in matches:
                matches.append(norm_venue)

        with open(self.venue_tiers_yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(tiers_data, f, sort_keys=False)

        # Reload grader
        self.grader = Grader(
            rules_path=self.rules_yaml_path,
            venue_tiers_path=self.venue_tiers_yaml_path,
        )

        # 2. Update matching sources and re-grade claims cleanly
        all_sources = self.repo.list_sources()
        matching_sources = [s for s in all_sources if s.venue and s.venue.strip().lower() == norm_venue]

        for source in matching_sources:
            source.venue_tier = new_tier
            self.repo.insert_source(source)

            # Re-grade claims attached to this source
            for claim in self.repo.list_claims():
                if claim.source_id == source.id:
                    new_grade, new_reasons = self.grader.grade_claim(claim, source)
                    claim.grade = new_grade
                    claim.grade_reasons_json = new_reasons
                    self.repo.insert_claim(claim)

        # Record Review
        rev = Review(
            id=generate_review_id(),
            gate="G2",
            object_type="venue",
            object_id=venue_name,
            action="tier_venue",
            before_json={"venue": venue_name, "sources_affected": len(matching_sources)},
            after_json={"venue": venue_name, "new_tier": new_tier},
            reason=reason,
            reviewer=reviewer,
        )
        self.repo.insert_review(rev)

        return len(matching_sources)

    # =========================================================================
    # GATE 3: Claim Review Queue
    # =========================================================================
    def get_claim_review_queue(
        self,
        question_id: Optional[str] = None,
        sort_by: str = "uncertainty",
        status_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve claims for human review queue sorted by uncertainty or grade.

        Uncertainty sorting criteria:
        1. Low extraction confidence (< 0.80)
        2. Context warnings (e.g. corrupted terms)
        3. Grade boundary (weak vs moderate)
        4. Review status ('auto' first)
        """
        all_claims = self.repo.list_claims(question_id=question_id)
        if status_filter:
            all_claims = [c for c in all_claims if c.status == status_filter]

        queue_items = []
        for c in all_claims:
            src = self.repo.get_source(c.source_id)
            has_warnings = bool(c.context_json and c.context_json.get("warnings"))
            uncertainty_score = 0.0

            # Compute uncertainty priority (higher = more urgent to review)
            if c.extraction_confidence < 0.80:
                uncertainty_score += 50.0
            if has_warnings:
                uncertainty_score += 40.0
            if src and src.venue_tier == "unverified":
                uncertainty_score += 20.0
            if c.status == "auto":
                uncertainty_score += 10.0

            queue_items.append({
                "claim": c,
                "source": src,
                "uncertainty_score": uncertainty_score,
                "has_warnings": has_warnings,
            })

        if sort_by == "uncertainty":
            queue_items.sort(key=lambda x: x["uncertainty_score"], reverse=True)
        elif sort_by == "grade":
            grade_ranks = {"weak": 1, "vendor_claim": 2, "anecdote": 3, "moderate": 4, "strong": 5}
            queue_items.sort(key=lambda x: grade_ranks.get(x["claim"].grade, 0))

        return queue_items

    def approve_claim(self, claim_id: str, reviewer: str, reason: str = "Approved by reviewer") -> Claim:
        claim = self.repo.get_claim(claim_id)
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")
        before = dump_model(claim)
        claim.status = "approved"
        self.repo.insert_claim(claim)

        rev = Review(
            id=generate_review_id(),
            gate="G3",
            object_type="claim",
            object_id=claim.id,
            action="approve_claim",
            before_json=before,
            after_json=dump_model(claim),
            reason=reason,
            reviewer=reviewer,
        )
        self.repo.insert_review(rev)
        return claim

    def reject_claim(self, claim_id: str, reviewer: str, reason: str) -> Claim:
        if not reason or not reason.strip():
            raise ValueError("A reason is mandatory when rejecting a claim.")
        claim = self.repo.get_claim(claim_id)
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")
        before = dump_model(claim)
        claim.status = "rejected"
        self.repo.insert_claim(claim)

        rev = Review(
            id=generate_review_id(),
            gate="G3",
            object_type="claim",
            object_id=claim.id,
            action="reject_claim",
            before_json=before,
            after_json=dump_model(claim),
            reason=reason,
            reviewer=reviewer,
        )
        self.repo.insert_review(rev)
        return claim

    def edit_claim(
        self,
        claim_id: str,
        new_text: str,
        new_excerpt: Optional[str],
        reviewer: str,
        reason: str,
    ) -> Claim:
        claim = self.repo.get_claim(claim_id)
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")
        before = dump_model(claim)
        claim.text = new_text
        if new_excerpt:
            claim.source_excerpt = new_excerpt
        claim.status = "edited"
        self.repo.insert_claim(claim)

        rev = Review(
            id=generate_review_id(),
            gate="G3",
            object_type="claim",
            object_id=claim.id,
            action="edit_claim",
            before_json=before,
            after_json=dump_model(claim),
            reason=reason,
            reviewer=reviewer,
        )
        self.repo.insert_review(rev)
        return claim

    def change_claim_grade(
        self,
        claim_id: str,
        new_grade: str,
        reason: str,
        reviewer: str,
    ) -> Claim:
        if not reason or not reason.strip():
            raise ValueError("A reason is mandatory when changing a claim grade.")
        claim = self.repo.get_claim(claim_id)
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")
        before = dump_model(claim)
        claim.grade = new_grade  # type: ignore
        claim.status = "edited"
        if not claim.grade_reasons_json:
            claim.grade_reasons_json = []
        claim.grade_reasons_json.append(f"Human grade override by {reviewer}: {reason}")
        self.repo.insert_claim(claim)

        rev = Review(
            id=generate_review_id(),
            gate="G3",
            object_type="claim",
            object_id=claim.id,
            action="change_claim_grade",
            before_json=before,
            after_json=dump_model(claim),
            reason=reason,
            reviewer=reviewer,
        )
        self.repo.insert_review(rev)
        return claim

    def change_claim_entity_match(
        self,
        claim_id: str,
        new_entity_match: str,
        reason: str,
        reviewer: str,
    ) -> Claim:
        if not reason or not reason.strip():
            raise ValueError("A reason is mandatory when changing entity match.")
        claim = self.repo.get_claim(claim_id)
        if not claim:
            raise ValueError(f"Claim {claim_id} not found")
        before = dump_model(claim)
        claim.entity_match = new_entity_match  # type: ignore
        claim.status = "edited"
        self.repo.insert_claim(claim)

        rev = Review(
            id=generate_review_id(),
            gate="G3",
            object_type="claim",
            object_id=claim.id,
            action="change_claim_entity_match",
            before_json=before,
            after_json=dump_model(claim),
            reason=reason,
            reviewer=reviewer,
        )
        self.repo.insert_review(rev)
        return claim

    def bulk_approve_claims(
        self,
        claim_ids: List[str],
        reviewer: str,
        reason: str = "Bulk approved",
    ) -> List[Claim]:
        """Bulk approve claims only if they share identical source, grade, and study_type.

        Prompt constraint: 'Bulk approve only for identical source + grade + study type.'
        """
        if not claim_ids:
            return []

        claims = [self.repo.get_claim(cid) for cid in claim_ids]
        valid_claims = [c for c in claims if c is not None]
        if not valid_claims:
            return []

        # Check homogeneity constraint
        first = valid_claims[0]
        for c in valid_claims[1:]:
            if (
                c.source_id != first.source_id
                or c.grade != first.grade
                or c.study_type != first.study_type
            ):
                raise ValueError(
                    f"Bulk approve rejected: claims do not have identical source, grade, and study type. "
                    f"({c.id} vs {first.id})"
                )

        approved = []
        for c in valid_claims:
            before = dump_model(c)
            c.status = "approved"
            self.repo.insert_claim(c)
            rev = Review(
                id=generate_review_id(),
                gate="G3",
                object_type="claim",
                object_id=c.id,
                action="bulk_approve_claim",
                before_json=before,
                after_json=dump_model(c),
                reason=reason,
                reviewer=reviewer,
            )
            self.repo.insert_review(rev)
            approved.append(c)

        return approved
