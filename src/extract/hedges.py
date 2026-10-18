"""Rule-based hedge detection (S5). Terms live in synth/hedge_terms.yaml."""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import List, Pattern, Tuple

import yaml

HEDGE_TERMS_PATH = Path(__file__).resolve().parents[2] / "synth" / "hedge_terms.yaml"


@functools.lru_cache(maxsize=1)
def _pattern() -> Tuple[Pattern[str], ...]:
    data = yaml.safe_load(HEDGE_TERMS_PATH.read_text(encoding="utf-8")) or {}
    terms = sorted({str(t).strip().lower() for group in data.values() for t in (group or []) if str(t).strip()},
                   key=len, reverse=True)
    # Longest first so "tends to" wins over a shorter overlapping term.
    return (re.compile(r"\b(" + "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in terms) + r")\b", re.IGNORECASE),)


def find_hedge_terms(text: str) -> List[str]:
    """Hedge terms in `text`, lowercased, deduplicated, in order of first appearance."""
    found: List[str] = []
    for m in _pattern()[0].finditer(text or ""):
        term = re.sub(r"\s+", " ", m.group(1).lower())
        if term not in found:
            found.append(term)
    return found
