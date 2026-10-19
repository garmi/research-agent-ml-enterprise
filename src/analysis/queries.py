"""Search queries for the academic lane (S11, S13): built from the approved question and its sub-questions.

Search APIs rank long natural-language questions poorly, so each question is condensed to its key
terms (stopwords, filler such as "evidence" and generic wording such as "required" dropped; common
phrases written short, e.g. "artificial intelligence" -> AI). The subject's anchor terms (configured
technology words such as AI, LLM, code generation) are always kept, and a sub-question that lacks them
gets the main question's, so every query searches the same subject (S13: without them the searches
drifted to building design and business-process papers).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from src.analysis.relevance import STOPWORDS
from src.app import build_topic_queries
from src.engine.check_a_on_topic import FILLER_WORDS

MAX_QUERY_TERMS = 10

# Wording that says how much, not what: it narrows nothing in a literature search.
QUERY_FILLER = {
    "required", "require", "requires", "progress", "progressing", "strategically", "strategic", "differentiated",
    "standalone", "specialized", "specialised", "various", "key", "specific", "effective", "critical", "enable",
    "enables", "ensure", "need", "needed", "needs", "beyond", "toward", "towards", "way", "ways",
}
PHRASES = (
    (r"\bartificial[\s-]+intelligence\b", "AI"),
    (r"\blarge[\s-]+language[\s-]+models?\b", "LLM"),
    (r"\bmachine[\s-]+learning\b", "ML"),
    (r"\bgenerative[\s-]+ai\b", "GenAI"),
)
DEFAULT_ANCHORS = (
    "ai", "genai", "llm", "ml", "code generation", "code", "coding", "software", "agent", "agents", "agentic",
    "copilot", "assistant", "assistants", "devops", "devsecops",
)


def _anchors() -> Sequence[str]:
    try:
        from src.config import load_config

        configured = ((load_config() or {}).get("research") or {}).get("query_anchor_terms")
    except Exception:
        configured = None
    return tuple(str(a).lower() for a in (configured or DEFAULT_ANCHORS))


def _terms(question: str) -> List[str]:
    text = question or ""
    for pattern, short in PHRASES:
        text = re.sub(pattern, short, text, flags=re.IGNORECASE)
    return [w for w in re.findall(r"[A-Za-z0-9]+", text)
            if w.lower() not in STOPWORDS and w.lower() not in FILLER_WORDS and w.lower() not in QUERY_FILLER]


def _anchor_flags(terms: List[str], anchors: Sequence[str]) -> List[bool]:
    """Which terms are anchors; multi-word anchors (e.g. 'code generation') flag every word they cover."""
    lower = [t.lower() for t in terms]
    flags = [t in anchors for t in lower]
    for a in anchors:
        parts = a.split()
        if len(parts) > 1:
            for i in range(len(lower) - len(parts) + 1):
                if lower[i:i + len(parts)] == parts:
                    for j in range(i, i + len(parts)):
                        flags[j] = True
    return flags


def condense(question: str, max_terms: int = MAX_QUERY_TERMS, anchors: Optional[Sequence[str]] = None) -> str:
    """Key terms in their original order; anchor terms are kept first when there are too many."""
    terms = _terms(question)
    flags = _anchor_flags(terms, anchors if anchors is not None else _anchors())
    keep = [i for i, f in enumerate(flags) if f][:max_terms]
    keep += [i for i, f in enumerate(flags) if not f][: max_terms - len(keep)]
    return " ".join(terms[i] for i in sorted(keep))


def anchor_terms(question: str, anchors: Optional[Sequence[str]] = None) -> List[str]:
    terms = _terms(question)
    flags = _anchor_flags(terms, anchors if anchors is not None else _anchors())
    out: List[str] = []
    for t, f in zip(terms, flags):
        if f and t.lower() not in (o.lower() for o in out):
            out.append(t)
    return out


def research_queries(topic: str, approved_package: Optional[Dict[str, Any]] = None) -> List[str]:
    """Condensed main question, then the cleaned full question (the query that worked before S11),
    then each sub-question with the main question's anchors, then the generic topic expansions."""
    pkg = approved_package or {}
    main = pkg.get("refined_question") or topic
    anchors = _anchors()
    main_anchors = anchor_terms(main, anchors)
    topic_queries = build_topic_queries(topic)
    candidates = [condense(main, anchors=anchors)] + topic_queries[:1]
    for sq in pkg.get("sub_questions") or []:
        if not isinstance(sq, str):
            continue
        q = condense(sq, anchors=anchors)
        present = {w.lower() for w in q.split()}
        q = " ".join([q] + [a for a in main_anchors if a.lower() not in present])
        candidates.append(q)
    candidates += topic_queries[1:]
    out: List[str] = []
    seen = set()
    for q in candidates:
        norm = re.sub(r"\s+", " ", q or "").strip()
        if norm and norm.lower() not in seen:
            seen.add(norm.lower())
            out.append(norm)
    return out
