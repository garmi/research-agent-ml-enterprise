"""Deterministic Rule-Based Claim Grader for Research Engine v2.

Implements rules defined in grade/rules.yaml and venue tiers from grade/venue_tiers.yaml:
- strong: verified peer-reviewed venue + empirical study type + entity match adequate + no unresolved contradiction, OR independently measured by 2+ independent sources.
- moderate: reputable preprint or peer-reviewed with empirical method but narrow context, OR 2+ independent customer claims.
- weak: position paper, conceptual framework, unverified venue, or abstract-only extraction with no method detail.
- vendor_claim: source org has a commercial stake, unless independently corroborated.
- anecdote: single case, practitioner lane, or social post.
- Caps: abstract-only caps at moderate; unresolved contradiction caps at weak; unverified venue caps at weak.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import yaml

from src.ledger.models import Claim, ClaimGrade, Source, VenueTier

logger = logging.getLogger(__name__)


class Grader:
    def __init__(
        self,
        rules_path: str = "grade/rules.yaml",
        venue_tiers_path: str = "grade/venue_tiers.yaml",
    ):
        self.rules_path = rules_path
        self.venue_tiers_path = venue_tiers_path
        self._load_configs()

    def _load_configs(self) -> None:
        with open(self.rules_path, "r", encoding="utf-8") as f:
            self.rules = yaml.safe_load(f)
        with open(self.venue_tiers_path, "r", encoding="utf-8") as f:
            self.venue_tiers = yaml.safe_load(f)

    def resolve_venue_tier(self, venue: Optional[str], source_type: Optional[str] = None) -> VenueTier:
        """Resolve venue tier deterministically using substring matching."""
        if not venue:
            if source_type == "preprint":
                return "reputable_preprint"
            if source_type in ("vendor_blog", "filing"):
                return "vendor"
            if source_type == "practitioner_note":
                return "n/a"
            return "unverified"

        norm = venue.strip().lower()

        # Check verified tier
        for pattern in self.venue_tiers["tiers"]["verified"]["matches"]:
            if pattern in norm:
                return "verified"

        # Check reputable preprint
        for pattern in self.venue_tiers["tiers"]["reputable_preprint"]["matches"]:
            if pattern in norm:
                return "reputable_preprint"

        # Check unverified tier
        for pattern in self.venue_tiers["tiers"]["unverified"]["matches"]:
            if pattern in norm:
                return "unverified"

        # Check vendor tier
        for pattern in self.venue_tiers["tiers"]["vendor"]["matches"]:
            if pattern in norm:
                return "vendor"

        # Default to unverified for unknown venues
        return "unverified"

    def grade_claim(
        self,
        claim: Claim,
        source: Source,
        corroborating_source_count: int = 1,
        has_unresolved_contradiction: bool = False,
    ) -> Tuple[ClaimGrade, List[str]]:
        """Grade an individual claim according to deterministic rules and caps.

        Returns:
            (assigned_grade, list of rule reasons that fired)
        """
        reasons: List[str] = []
        empirical_types = self.rules.get("study_types", {}).get("empirical", [])
        observational_types = self.rules.get("study_types", {}).get("observational", [])

        # 1. Base grade determination
        assigned_grade: ClaimGrade = "weak"

        # Check vendor claim
        if source.commercial_stake in ("vendor", "sponsored") or source.source_type == "vendor_blog":
            if corroborating_source_count >= 2:
                assigned_grade = "moderate"
                reasons.append("Vendor claim upgraded to moderate via independent corroboration (2+ sources)")
            else:
                assigned_grade = "vendor_claim"
                reasons.append(f"Commercial stake ({source.commercial_stake}) identified without independent corroboration")
                return assigned_grade, reasons

        # Check anecdote
        if source.lane == "practitioner" or claim.study_type == "practitioner_observation" or claim.study_type == "case_study" and source.venue_tier == "unverified":
            assigned_grade = "anecdote"
            reasons.append("Single observation or practitioner observation defaults to anecdote")

        elif source.venue_tier == "verified":
            if claim.study_type in empirical_types:
                if claim.entity_match in ("exact", "family"):
                    assigned_grade = "strong"
                    reasons.append(f"Verified venue ({source.venue}) with empirical study ({claim.study_type}) and adequate entity match ({claim.entity_match})")
                else:
                    assigned_grade = "moderate"
                    reasons.append(f"Verified venue with empirical study, but topic-level entity match restricts to moderate")
            else:
                assigned_grade = "moderate"
                reasons.append(f"Verified venue ({source.venue}) with non-empirical study ({claim.study_type})")

        elif source.venue_tier == "reputable_preprint":
            assigned_grade = "moderate"
            reasons.append(f"Reputable preprint server ({source.venue or 'arXiv'})")

        elif source.venue_tier == "unverified":
            assigned_grade = "weak"
            reasons.append(f"CAP APPLIED: Unverified venue ({source.venue or 'unknown'}) caps grade at weak")

        else:
            assigned_grade = "weak"
            reasons.append(f"Defaulting to weak for study type {claim.study_type} and venue tier {source.venue_tier}")

        # Check multi-source independent corroboration upgrade
        if corroborating_source_count >= 2 and assigned_grade in ("moderate", "weak"):
            assigned_grade = "strong"
            reasons.append(f"Upgraded to strong via 2+ independent corroborating sources ({corroborating_source_count})")

        # 2. Apply Caps
        # Cap: Abstract-only extraction caps at moderate
        if source.extraction_depth == "abstract_only" and assigned_grade == "strong":
            assigned_grade = "moderate"
            reasons.append("CAP APPLIED: Abstract-only extraction depth caps grade at moderate")

        # Cap: Unverified venue cannot exceed weak
        if source.venue_tier == "unverified" and assigned_grade in ("strong", "moderate"):
            assigned_grade = "weak"
            reasons.append(f"CAP APPLIED: Unverified venue ({source.venue}) caps grade at weak")

        # Cap: Unresolved contradiction caps at weak
        if has_unresolved_contradiction and assigned_grade in ("strong", "moderate"):
            assigned_grade = "weak"
            reasons.append("CAP APPLIED: Unresolved contradiction in evidence ledger caps grade at weak")

        return assigned_grade, reasons
