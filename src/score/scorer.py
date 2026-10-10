"""Quality Scorer for Research Engine v2 outputs.

Calculates components S1 through S7 and overall composite score (0-100).
Identifies the top 3 high-impact changes to improve output quality.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Set, Tuple
import yaml

from src.ledger.models import Claim, OutputSentence, Question, Source
from src.score.checker import GateCheckResult

logger = logging.getLogger(__name__)

GRADE_VALUES = {
    "strong": 1.0,
    "moderate": 0.7,
    "weak": 0.4,
    "vendor_claim": 0.3,
    "anecdote": 0.2,
}


class QualityScorer:
    def __init__(self, scoring_cfg_path: str = "score/scoring.yaml"):
        self.scoring_cfg_path = scoring_cfg_path
        self._load_config()

    def _load_config(self) -> None:
        if os.path.exists(self.scoring_cfg_path):
            with open(self.scoring_cfg_path, "r", encoding="utf-8") as f:
                self.cfg = yaml.safe_load(f)
        else:
            self.cfg = {
                "weights": {
                    "S1_evidence_strength": 30,
                    "S2_corroboration_diversity": 15,
                    "S3_question_coverage": 15,
                    "S4_gap_disclosure": 10,
                    "S5_freshness_scope": 10,
                    "S6_human_review": 10,
                    "S7_reproducibility": 10,
                },
                "bands": {"publish_ready": 85, "revise": 70},
            }

    def calculate_score(
        self,
        gate_result: GateCheckResult,
        sentences: List[OutputSentence],
        ledger_claims: Dict[str, Claim],
        sources: Dict[str, Source],
        questions: List[Question],
        reviewed_claim_ids: Optional[Set[str]] = None,
        gates_completed_count: int = 0,
        gap_outcomes_disclosed: float = 1.0,
        reproducibility_agreement: float = 1.0,
    ) -> Dict[str, Any]:
        """Compute all 7 quality score components and composite score."""
        assertive_sentences = [s for s in sentences if s.type == "assertive"]
        weights = self.cfg.get("weights", {})

        # S1: Evidence strength (Weight: 30)
        # Mean over assertive sentences of min(1, grade_value(sentence) / best_grade_available)
        s1_values = []
        best_available_grade = 1.0  # Normalized reference
        for s in assertive_sentences:
            cited = [ledger_claims[cid] for cid in (s.claim_ids_json or []) if cid in ledger_claims]
            if cited:
                min_val = min(GRADE_VALUES.get(c.grade, 0.2) for c in cited)
                s1_values.append(min(1.0, min_val / best_available_grade))
            else:
                s1_values.append(0.0)

        s1_score = (sum(s1_values) / len(s1_values) if s1_values else 0.0) * weights.get("S1_evidence_strength", 30)

        # S2: Corroboration & Diversity (Weight: 15)
        # 0.7 * share of findings supported by 2+ independent sources + 0.3 * share spanning 2+ lanes
        corroborated_count = 0
        multi_lane_count = 0
        for s in assertive_sentences:
            cids = [cid for cid in (s.claim_ids_json or []) if cid in ledger_claims]
            src_ids = {ledger_claims[cid].source_id for cid in cids}
            lanes = {sources[sid].lane for sid in src_ids if sid in sources}
            if len(src_ids) >= 2:
                corroborated_count += 1
            if len(lanes) >= 2:
                multi_lane_count += 1

        share_corrob = corroborated_count / len(assertive_sentences) if assertive_sentences else 0.0
        share_lanes = multi_lane_count / len(assertive_sentences) if assertive_sentences else 0.0
        s2_score = (0.7 * share_corrob + 0.3 * share_lanes) * weights.get("S2_corroboration_diversity", 15)

        # S3: Question coverage (Weight: 15)
        # Share of question cells covered
        covered_questions = 0
        all_cited_claim_ids = {cid for s in assertive_sentences for cid in (s.claim_ids_json or [])}
        cited_question_ids = {ledger_claims[cid].question_id for cid in all_cited_claim_ids if cid in ledger_claims}
        if questions:
            covered_questions = len(cited_question_ids.intersection({q.id for q in questions})) / len(questions)
        s3_score = covered_questions * weights.get("S3_question_coverage", 15)

        # S4: Gap disclosure (Weight: 10)
        s4_score = gap_outcomes_disclosed * weights.get("S4_gap_disclosure", 10)

        # S5: Freshness & scope (Weight: 10)
        fresh_claims = 0
        for cid in all_cited_claim_ids:
            c = ledger_claims.get(cid)
            if c:
                # Default 36 months / 3 years: 2023 or later
                claim_year = int(c.claim_date) if c.claim_date and c.claim_date.isdigit() else 2026
                if claim_year >= 2023:
                    fresh_claims += 1
        freshness_ratio = fresh_claims / len(all_cited_claim_ids) if all_cited_claim_ids else 1.0
        s5_score = freshness_ratio * weights.get("S5_freshness_scope", 10)

        # S6: Human review (Weight: 10)
        # 0.6 * share of cited claims reviewed at Gate 3 + 0.4 * share of Gates 1-6 completed
        reviewed_claims = reviewed_claim_ids or set()
        share_reviewed = len(all_cited_claim_ids.intersection(reviewed_claims)) / len(all_cited_claim_ids) if all_cited_claim_ids else 0.0
        share_gates = min(1.0, gates_completed_count / 6.0)
        s6_score = (0.6 * share_reviewed + 0.4 * share_gates) * weights.get("S6_human_review", 10)

        # S7: Reproducibility (Weight: 10)
        s7_score = reproducibility_agreement * weights.get("S7_reproducibility", 10)

        total_score = round(s1_score + s2_score + s3_score + s4_score + s5_score + s6_score + s7_score, 1)

        # Determine band
        if not gate_result.passed:
            band = "BLOCKED"
        elif total_score >= self.cfg.get("bands", {}).get("publish_ready", 85):
            band = "PUBLISH_READY"
        elif total_score >= self.cfg.get("bands", {}).get("revise", 70):
            band = "REVISE"
        else:
            band = "DO_NOT_PUBLISH"

        # Generate top 3 high-impact improvement recommendations
        recommendations = []
        if not gate_result.passed:
            recommendations.append("Resolve hard gate violations (G1-G6) to unblock publication.")
        if s1_score < 20:
            recommendations.append("Upgrade claim evidence base: replace weak/unverified sources with empirical studies from verified venues.")
        if s2_score < 8:
            recommendations.append("Increase corroboration: support key findings with at least 2 independent sources or across academic & enterprise lanes.")
        if s6_score < 6:
            recommendations.append("Complete human review: sign off on pending claims in Claim Review Queue (Gate 3).")
        if len(recommendations) < 3:
            recommendations.append("Ensure in-scope questions have complete coverage and explicit gap matrix disclosures.")

        return {
            "total_score": total_score,
            "band": band,
            "is_blocked": not gate_result.passed,
            "components": {
                "S1_evidence_strength": round(s1_score, 1),
                "S2_corroboration_diversity": round(s2_score, 1),
                "S3_question_coverage": round(s3_score, 1),
                "S4_gap_disclosure": round(s4_score, 1),
                "S5_freshness_scope": round(s5_score, 1),
                "S6_human_review": round(s6_score, 1),
                "S7_reproducibility": round(s7_score, 1),
            },
            "top_3_improvements": recommendations[:3],
        }
