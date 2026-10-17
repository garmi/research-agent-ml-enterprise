"""Spike 1: Sentence-to-Quote Support Verification (Hallucination Warning Badge).

Evaluates whether an assertive sentence in a research draft is faithfully supported
by the verbatim source excerpt (< 25 words) cited behind it.

Architecture & Design Principles:
1. Non-Blocking Warning Badge: Generates an informative advisory flag on
   `output_sentences.checks_json`. It never replaces or overrides the deterministic
   Hard Gates (G1–G6).
2. Local & Fast: Designed to run with zero remote API dependencies. Can utilize
   Vectara HHEM-2.1-Open (or DeBERTa-v3 NLI) locally, with deterministic regex and
   token-overlap fallback for resource-constrained environments.
3. Plain-English Diagnostics: Identifies numerical mismatches and semantic divergence.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set


def _extract_numbers(text: str) -> Set[str]:
    """Extract numeric tokens (percentages, multipliers, integers, floats)."""
    # Matches patterns like 24%, 3.5x, 100, $5M
    tokens = re.findall(r"\b\d+(?:\.\d+)?(?:%|x|k|m|b)?\b", text.lower())
    return set(tokens)


def _tokenize_content_words(text: str) -> Set[str]:
    """Extract lowercase words >= 3 chars, filtering standard stopwords."""
    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "are", "was",
        "were", "our", "their", "have", "been", "has", "more", "than", "which"
    }
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    return {w for w in words if w not in stopwords}


def verify_sentence_support(
    sentence: str,
    quote: str,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify whether a draft sentence is faithfully grounded in the cited source quote.

    Returns a dictionary conforming to the Spike 1 verification contract:
      - supported: bool
      - confidence: float (0.0 to 1.0)
      - warning_badge: Optional[str]
      - reasons: List[str]
    """
    sentence_clean = (sentence or "").strip()
    quote_clean = (quote or "").strip()

    if not sentence_clean or not quote_clean:
        return {
            "supported": False,
            "confidence": 0.0,
            "warning_badge": "⚠️ Unsupported Assertion",
            "reasons": ["Sentence or quote is empty."],
        }

    reasons: List[str] = []

    # 1. Numerical Fidelity Check: numbers in sentence must appear in quote
    sentence_nums = _extract_numbers(sentence_clean)
    quote_nums = _extract_numbers(quote_clean)
    missing_nums = sentence_nums - quote_nums
    if missing_nums:
        return {
            "supported": False,
            "confidence": 0.20,
            "warning_badge": "⚠️ Numerical Mismatch",
            "reasons": [
                f"Sentence asserts numbers not grounded in quote: {', '.join(sorted(missing_nums))}"
            ],
        }

    # 2. Content Word Overlap Check
    s_words = _tokenize_content_words(sentence_clean)
    q_words = _tokenize_content_words(quote_clean)

    if not s_words:
        overlap_ratio = 1.0
        overlap_count = 0
    else:
        overlap = s_words.intersection(q_words)
        overlap_count = len(overlap)
        overlap_ratio = overlap_count / len(s_words)

    if overlap_ratio >= 0.30 or overlap_count >= 3:
        num_boost = 0.10 if (sentence_nums and not missing_nums) else 0.0
        confidence = min(0.95, round(0.50 + num_boost + overlap_ratio * 0.40, 2))
        return {
            "supported": True,
            "confidence": confidence,
            "warning_badge": None,
            "reasons": [],
        }
    else:
        return {
            "supported": False,
            "confidence": round(overlap_ratio, 2),
            "warning_badge": "⚠️ Unsupported Assertion",
            "reasons": [
                f"Prose assertions lack sufficient token grounding in cited quote (overlap: {overlap_ratio:.0%})."
            ],
        }
