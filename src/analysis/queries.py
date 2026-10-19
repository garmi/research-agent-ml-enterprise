"""Search queries for the academic lane (S11): built from the approved question and its sub-questions.

Search APIs rank long natural-language questions poorly, so each question is condensed to its key
terms (stopwords and filler such as "evidence" or "impact" dropped, order kept, at most 8 terms). The
approved question comes first, then each sub-question, then the generic topic expansions.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.analysis.relevance import STOPWORDS
from src.app import build_topic_queries
from src.engine.check_a_on_topic import FILLER_WORDS

MAX_QUERY_TERMS = 8


def condense(question: str, max_terms: int = MAX_QUERY_TERMS) -> str:
    terms = [w for w in re.findall(r"[A-Za-z0-9]+", question or "")
             if w.lower() not in STOPWORDS and w.lower() not in FILLER_WORDS]
    return " ".join(terms[:max_terms])


def research_queries(topic: str, approved_package: Optional[Dict[str, Any]] = None) -> List[str]:
    pkg = approved_package or {}
    candidates = [condense(pkg.get("refined_question") or topic)]
    candidates += [condense(sq) for sq in pkg.get("sub_questions") or [] if isinstance(sq, str)]
    candidates += build_topic_queries(topic)
    out: List[str] = []
    seen = set()
    for q in candidates:
        norm = re.sub(r"\s+", " ", q or "").strip()
        if norm and norm.lower() not in seen:
            seen.add(norm.lower())
            out.append(norm)
    return out
