from __future__ import annotations

from typing import Any, Dict, Iterable, List


FOCUS_AREAS = {
    "ai": ["ai", "artificial intelligence", "machine learning", "ml", "llm", "model", "automation"],
    "enterprise": ["enterprise", "organization", "business", "governance", "strategy", "adoption"],
    "engineering": ["software engineering", "sdlc", "agile", "devops", "delivery", "platform"],
    "product": ["product", "roadmap", "value", "workflow", "process", "team"],
}


def detect_focus_areas(topic: str) -> Dict[str, List[str]]:
    lower = topic.lower()
    detected = {}
    for name, keywords in FOCUS_AREAS.items():
        matches = [kw for kw in keywords if kw in lower]
        if matches:
            detected[name] = matches
    return detected


def classify_papers(papers: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    buckets = {"ai": [], "enterprise": [], "engineering": [], "product": []}
    for paper in papers:
        text = " ".join([
            str(paper.get("title", "")),
            str(paper.get("abstract", "")),
            str(paper.get("venue", "")),
            str(paper.get("source", "")),
        ]).lower()
        for name, keywords in FOCUS_AREAS.items():
            if any(kw in text for kw in keywords):
                buckets[name].append(paper)
    return buckets
