from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


def derive_business_signal(topic: str, papers: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    paper_list = list(papers)
    if not paper_list:
        return {
            "topic": topic,
            "business_signal": "No papers retrieved for this topic.",
            "market_signal": "No market signal available.",
            "enterprise_implication": "No enterprise implication available.",
            "opportunity": "No strategic opportunity identified.",
        }

    titles = [paper.get("title", "") for paper in paper_list if paper.get("title")]
    signals = [
        "enterprise adoption is a recurring theme",
        "governance and operational maturity appear critical",
        "AI and software delivery quality remain tightly linked",
        "organizational readiness is often as important as technical capability",
    ]

    return {
        "topic": topic,
        "business_signal": signals[0],
        "market_signal": f"Recent literature on {topic} suggests demand is accelerating across enterprise and engineering contexts.",
        "enterprise_implication": "Organizations need stronger governance, adoption maturity, and delivery process alignment to capture value.",
        "opportunity": "The highest-value opportunity is to combine technology readiness, process maturity, and business capability transformation.",
        "sample_titles": titles[:5],
    }


def summarize_findings(papers: Iterable[Dict[str, Any]]) -> List[str]:
    suggestions = [
        "Adoption is more dependent on operating model, governance, and workflow maturity than pure model capability.",
        "The strongest value emerges when AI capability is aligned to software delivery, product, and platform transformation.",
        "Enterprise teams continue to face gaps in measurement, governance, and organizational readiness.",
        "Research often points to the need for organizational capability building before broad-scale scaling.",
    ]
    return suggestions
