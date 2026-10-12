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
        human_gates_completed_count: Optional[int] = None,
        gap_outcomes_disclosed: Optional[float] = None,
        reproducibility_agreement: Optional[float] = None,
        cached_papers: Optional[List[Dict[str, Any]]] = None,
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
        # Computed from gap outcomes stated and ledger contradictions mentioned
        if gap_outcomes_disclosed is not None:
            s4_score = gap_outcomes_disclosed * weights.get("S4_gap_disclosure", 10)
        else:
            gap_outcomes_count = sum(
                1 for s in sentences
                if s.type == "negative_finding"
                or any(p in s.text.lower() for p in (
                    "outcome 1", "outcome 2", "outcome 3", "outcome 4",
                    "practice not assessed", "strategic gap", "gap matrix", "evidence does not support",
                    "unsupported", "what the evidence does not support"
                ))
            )
            target_gaps = max(1, len(questions))
            gap_ratio = min(1.0, gap_outcomes_count / target_gaps)

            known_contradictions = sum(
                1 for c in ledger_claims.values()
                if (c.context_json and c.context_json.get("has_contradiction")) or getattr(c, "has_contradiction", False)
            )
            contradictions_mentioned = sum(
                1 for s in sentences
                if any(w in s.text.lower() for w in (
                    "contradict", "diverg", "conflict", "discrepan", "tension", "inconsistent", "unresolved"
                ))
            )
            if known_contradictions > 0:
                contradiction_ratio = min(1.0, contradictions_mentioned / known_contradictions)
            else:
                contradiction_ratio = 1.0 if (gap_outcomes_count > 0 or contradictions_mentioned > 0) else 0.5

            s4_ratio = 0.6 * gap_ratio + 0.4 * contradiction_ratio
            s4_score = s4_ratio * weights.get("S4_gap_disclosure", 10)

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
        # Count claims actually reviewed by a human and human gates completed, not automated gates passed.
        reviewed_claims = reviewed_claim_ids or set()
        cited_reviewed = all_cited_claim_ids.intersection(reviewed_claims)
        share_reviewed = len(cited_reviewed) / len(all_cited_claim_ids) if all_cited_claim_ids else 0.0

        if human_gates_completed_count is not None:
            effective_human_gates = human_gates_completed_count
        else:
            effective_human_gates = 0
        share_gates = min(1.0, effective_human_gates / 3.0)
        s6_score = (0.6 * share_reviewed + 0.4 * share_gates) * weights.get("S6_human_review", 10)

        # S7: Reproducibility (Weight: 10)
        # Re-run extraction and grading from cached sources and compute agreement,
        # or mark S7 'not measured' and cap band at REVISE.
        s7_measured = False
        s7_agreement = 0.0
        if reproducibility_agreement is not None:
            s7_measured = True
            s7_agreement = float(reproducibility_agreement)
        elif cached_papers is not None:
            s7_agreement = self.compute_reproducibility(cached_papers, ledger_claims)
            s7_measured = True

        if s7_measured:
            s7_score = s7_agreement * weights.get("S7_reproducibility", 10)
            s7_display: Any = round(s7_score, 1)
        else:
            s7_score = 0.0
            s7_display = "not measured"

        total_score = round(s1_score + s2_score + s3_score + s4_score + s5_score + s6_score + (s7_score if s7_measured else 0.0), 1)

        # Determine band
        if not gate_result.passed:
            band = "BLOCKED"
        elif not s7_measured:
            # Band is capped at REVISE while any component is unmeasured
            if total_score >= self.cfg.get("bands", {}).get("revise", 70):
                band = "REVISE"
            else:
                band = "NOT_PUBLISHABLE"
        elif total_score >= self.cfg.get("bands", {}).get("publish_ready", 85):
            band = "PUBLISH_READY"
        elif total_score >= self.cfg.get("bands", {}).get("revise", 70):
            band = "REVISE"
        else:
            band = "NOT_PUBLISHABLE"

        # Generate top 3 high-impact improvement recommendations
        recommendations = []
        if not gate_result.passed:
            recommendations.append("Resolve hard gate violations (G1-G6) to unblock publication.")
        if not s7_measured:
            recommendations.append("Measure extraction determinism: re-run extraction and grading from cached sources to verify agreement (measures local cache extraction determinism, not external reproducibility).")
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
                "S7_reproducibility": s7_display,
                "S7_extraction_determinism": s7_display,
            },
            "top_3_improvements": recommendations[:3],
        }

    def compute_reproducibility(
        self,
        cached_papers: List[Dict[str, Any]],
        ledger_claims: Dict[str, Claim],
    ) -> float:
        """Re-run extraction and grading from cached sources and compute agreement."""
        if not cached_papers and not ledger_claims:
            return 1.0
        if not cached_papers or not ledger_claims:
            return 0.0

        from src.extract.claim_extractor import extract_claims_from_paper
        from src.grade.grader import Grader

        grader = Grader()
        re_extracted_claims: List[Claim] = []
        for paper in cached_papers:
            extracted = extract_claims_from_paper(paper)
            venue = paper.get("venue")
            source_type = "peer_reviewed" if paper.get("doi") else "preprint"
            venue_tier = grader.resolve_venue_tier(venue, source_type)
            source_obj = Source(
                id=paper.get("id") or "src_cached",
                lane="academic",
                source_type=source_type,
                title=paper.get("title", "Untitled"),
                venue=venue,
                venue_tier=venue_tier,
                pub_date=str(paper.get("year", "2024")),
            )
            for c in extracted:
                c.grade, c.grade_reasons_json = grader.grade_claim(c, source_obj)
                re_extracted_claims.append(c)

        if not re_extracted_claims:
            return 0.0

        matches = 0
        for c in ledger_claims.values():
            for r in re_extracted_claims:
                if r.source_id == c.source_id and r.source_excerpt == c.source_excerpt:
                    matches += 1
                    break

        agreement = matches / max(len(ledger_claims), len(re_extracted_claims))
        return round(min(1.0, agreement), 4)

