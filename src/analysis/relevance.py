from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set


TOPIC_HINTS = {
    "ai": ["ai", "artificial intelligence", "machine learning", "ml", "large language model", "llm"],
    "enterprise": ["enterprise", "business", "organization", "industry", "adoption", "strategy", "governance"],
    "engineering": ["software engineering", "sdlc", "agile", "devops", "platform", "architecture", "delivery"],
    "product": ["product", "roadmap", "value", "process", "workflow", "team", "organization"],
}


def normalize_text(value: Any) -> str:
    text = str(value or "")
    text = text.lower()
    text = text.replace("-", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def token_set(text: str) -> Set[str]:
    return set(normalize_text(text).split())


def score_paper(paper: Dict[str, Any], topic: str) -> float:
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")
    venue = paper.get("venue", "")
    source = paper.get("source", "")
    text = " ".join([title, abstract, venue, source])
    norm = normalize_text(text)
    tokens = set(norm.split())

    topic_tokens = set(normalize_text(topic).split())
    topic_score = sum(1 for token in topic_tokens if token in tokens)

    business_score = sum(1 for token in normalize_text("enterprise adoption business strategy governance market value").split() if token in tokens)
    engineering_score = sum(1 for token in normalize_text("software engineering agile sdlc devops platform architecture delivery workflow automation").split() if token in tokens)
    ai_score = sum(1 for token in normalize_text("ai ml machine learning llm intelligent automation analytics model").split() if token in tokens)

    score = topic_score * 3.0 + business_score * 1.5 + engineering_score * 1.5 + ai_score * 2.0

    year = paper.get("year")
    if isinstance(year, int):
        if year >= 2022:
            score += 0.8
        elif year >= 2020:
            score += 0.5

    if any(k in norm for k in ["enterprise", "organization", "industry", "adoption", "strategy"]):
        score += 1.0

    return round(score, 2)


def rank_papers(papers: Iterable[Dict[str, Any]], topic: str) -> List[Dict[str, Any]]:
    scored: List[Dict[str, Any]] = []
    for paper in papers:
        paper = dict(paper)
        paper["relevance_score"] = score_paper(paper, topic)
        scored.append(paper)
    scored.sort(key=lambda item: item.get("relevance_score", 0), reverse=True)
    return scored
