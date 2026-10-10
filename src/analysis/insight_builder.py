from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List


def derive_business_signal(topic: str, papers: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Data-derived signals only (no canned claims)."""
    paper_list = list(papers)
    if not paper_list:
        return {
            "topic": topic,
            "papers_analysed": 0,
            "note": "No papers retrieved for this topic.",
        }

    years = [p["year"] for p in paper_list if isinstance(p.get("year"), int)]
    recent = sum(1 for y in years if y >= 2023)
    sources = Counter(p.get("source", "unknown") for p in paper_list)
    scores = [float(p.get("relevance_score", 0)) for p in paper_list]

    return {
        "topic": topic,
        "papers_analysed": len(paper_list),
        "year_range": f"{min(years)}-{max(years)}" if years else "n/a",
        "recent_share_2023_plus": round(recent / len(years), 2) if years else None,
        "source_mix": dict(sources),
        "avg_relevance_score": round(sum(scores) / len(scores), 2) if scores else None,
        "sample_titles": [p.get("title", "") for p in paper_list[:5] if p.get("title")],
    }


def summarize_findings(paper_summaries: Iterable[Dict[str, Any]]) -> List[str]:
    """Pull per-paper findings from map-step summaries, tagged by paper id."""
    findings: List[str] = []
    for item in paper_summaries:
        text = (item.get("key_findings") or "").strip()
        if text and text.lower() != "not stated":
            findings.append(f"[{item.get('paper_id', '?')}] {text}")
    return findings[:8]
