"""Explainable Unused Sources Accounting (Step 4 Evidence & Step 5 Draft).

Classifies and explains in plain English why a retrieved source was not cited
in the final research draft, preventing confusion and maintaining total auditability:
- unverified_venue: unrefereed or predatory venue capped by tier policy
- vendor_claim_unsupported: vendor assertion lacking empirical verification
- user_excluded: explicitly deselected by reviewer during evidence examination
- off_topic: relevance below entity fidelity threshold
- no_empirical_data: conceptual or position paper lacking empirical findings
- paywall: full-text extraction blocked or unavailable
- not_selected_by_synthesizer: valid evidence deprioritized for stronger corroborating papers
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Set


@dataclass
class UnusedSourceExplanation:
    source_id: str
    source_title: str
    category: str
    plain_english_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def explain_unused_sources(
    all_sources: List[Dict[str, Any]],
    cited_source_ids: Set[str],
    claims: Optional[List[Dict[str, Any]]] = None,
) -> List[UnusedSourceExplanation]:
    """Examine all fetched sources and return plain-English explanations for uncited ones."""
    claims_by_source: Dict[str, List[Dict[str, Any]]] = {}
    if claims:
        for c in claims:
            s_id = c.get("source_id")
            if s_id:
                claims_by_source.setdefault(s_id, []).append(c)

    explanations: List[UnusedSourceExplanation] = []

    for src in all_sources:
        src_id = src.get("id") or ""
        if not src_id or src_id in cited_source_ids:
            continue

        title = src.get("title") or "Untitled Source"
        venue_tier = src.get("venue_tier") or "unverified"
        src_claims = claims_by_source.get(src_id, [])

        # 1. User deselection in evidence review
        if any(c.get("status") == "rejected" for c in src_claims):
            category = "user_excluded"
            reason = "Excluded by user during evidence examination."
        # 2. Vendor claim without empirical backing
        elif venue_tier == "vendor" or any(c.get("grade") == "vendor_claim" for c in src_claims):
            category = "vendor_claim_unsupported"
            reason = "Graded as vendor claim without independent corroborating empirical data."
        # 3. Unverified or predatory venue
        elif venue_tier == "unverified" or any(c.get("grade") == "weak" for c in src_claims):
            category = "unverified_venue"
            reason = "Published in unverified venue or low-refereed publication."
        # 4. Off-topic entity mismatch
        elif any(c.get("entity_match") in ("mismatch", "topic_level") for c in src_claims):
            category = "off_topic"
            reason = "Discusses broad topic but lacks specific entity data matching the question."
        # 5. Paywall / extraction limitation
        elif src.get("status") == "paywalled" or (not src_claims and src.get("extraction_depth") == "abstract_only"):
            category = "paywall"
            reason = "Full-text study unavailable behind paywall; abstract lacked extractable findings."
        # 6. Valid but deprioritized
        else:
            category = "not_selected_by_synthesizer"
            reason = "Evidence was extracted and validated, but prioritized behind higher-grade corroborating sources in synthesis."

        explanations.append(
            UnusedSourceExplanation(
                source_id=src_id,
                source_title=title,
                category=category,
                plain_english_reason=reason,
            )
        )

    return explanations
