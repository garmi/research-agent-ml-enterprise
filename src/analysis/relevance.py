from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set

STOPWORDS = {
    "how", "can", "is", "are", "was", "were", "being", "been", "used", "use",
    "using", "for", "by", "what", "which", "who", "whom", "this", "that", "these",
    "those", "we", "our", "you", "your", "they", "their", "the", "a", "an", "in",
    "on", "at", "to", "of", "with", "do", "does", "did", "effectively", "maximize",
    "maximise", "pro", "license", "best", "give", "show", "tell", "about",
}

TOPIC_HINTS = {
    "ai": ["ai", "artificial intelligence", "machine learning", "ml", "large language model", "llm", "agent", "agents", "coding"],
    "enterprise": ["enterprise", "business", "organization", "industry", "adoption", "strategy", "governance", "roi"],
    "engineering": ["software engineering", "sdlc", "agile", "devops", "platform", "architecture", "delivery", "productivity", "developer"],
    "product": ["product", "roadmap", "value", "process", "workflow", "team", "teams", "organization"],
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
    text = " ".join([title, abstract, str(venue or ""), str(source or "")])
    norm = normalize_text(text)
    tokens = set(norm.split())

    # Score against meaningful topic keywords (excluding stopwords)
    topic_tokens = [t for t in normalize_text(topic).split() if t not in STOPWORDS]
    if not topic_tokens:
        topic_tokens = normalize_text(topic).split()

    topic_score = sum(1 for token in topic_tokens if token in tokens)

    business_score = sum(1 for token in normalize_text("enterprise adoption business strategy governance market value roi productivity").split() if token in tokens)
    engineering_score = sum(1 for token in normalize_text("software engineering agile sdlc devops platform architecture delivery workflow automation developer teams").split() if token in tokens)
    ai_score = sum(1 for token in normalize_text("ai ml machine learning llm intelligent automation analytics model agent agents coding").split() if token in tokens)

    score = topic_score * 3.5 + business_score * 1.5 + engineering_score * 1.5 + ai_score * 2.0

    # Title match bonus
    title_norm = normalize_text(title)
    if any(token in title_norm for token in topic_tokens):
        score += 2.0

    year = paper.get("year")
    if isinstance(year, int):
        if year >= 2023:
            score += 1.2
        elif year >= 2020:
            score += 0.6

    if any(k in norm for k in ["enterprise", "organization", "industry", "adoption", "strategy", "productivity"]):
        score += 1.0

    return round(score, 2)


def rank_papers(papers: Iterable[Dict[str, Any]], topic: str) -> List[Dict[str, Any]]:
    scored: List[Dict[str, Any]] = []
    for paper in papers:
        p = dict(paper)
        p["relevance_score"] = score_paper(p, topic)
        scored.append(p)
    scored.sort(key=lambda item: item.get("relevance_score", 0), reverse=True)
    return scored
