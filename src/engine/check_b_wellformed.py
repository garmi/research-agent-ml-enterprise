"""Check B: are there enough well-formed claims from enough sources? (S4, DEC-016)

Rules only. No model is built or called, so the verdict is cheap and repeatable:
the same claims always give the same verdict and the same reason.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.engine.checks import CheckVerdict

CHECK_B_ID = "check_b_wellformed"
MAX_EXCERPT_WORDS = 25
VALID_GRADES = {"strong", "moderate", "weak", "vendor_claim", "anecdote"}
LOCATION_TAG = re.compile(r"\s*\(Location:[^)]*\)\s*$")


@dataclass
class CheckBResult:
    passed: bool
    wellformed: List[Any]
    set_aside: Dict[str, str]
    verdicts: List[CheckVerdict]
    reason_plain: str


def claim_content_key(claim: Any) -> str:
    """Stable key for a claim across re-runs (claim ids can be random): source + normalised text."""
    text = re.sub(r"\s+", " ", str(getattr(claim, "text", "") or "")).strip().lower()
    return hashlib.sha256(f"{claim.source_id}|{text}".encode("utf-8")).hexdigest()[:16]


def claim_problem(claim: Any, source: Optional[Any]) -> Optional[str]:
    """The first rule a claim breaks, in plain words, or None if it is well formed."""
    if source is None:
        return "Set aside: its source is not in the ledger."
    if not str(claim.text or "").strip():
        return "Set aside: the claim text is empty."
    # The extractor appends "(Location: Abstract)" after the capped quote; the tag is not quoted text.
    excerpt = LOCATION_TAG.sub("", str(claim.source_excerpt or "")).strip()
    if not excerpt:
        return "Set aside: there is no source excerpt."
    if len(excerpt.split()) > MAX_EXCERPT_WORDS:
        return f"Set aside: the source excerpt is longer than {MAX_EXCERPT_WORDS} words."
    if claim.grade not in VALID_GRADES:
        return "Set aside: the claim has no evidence grade."
    if not getattr(source, "lane", None):
        return "Set aside: its source has no lane."
    return None


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def run_check_b(
    claims: List[Any],
    sources_lookup: Dict[str, Any],
    *,
    run_id: str,
    min_claims: int,
    min_sources: int,
    excluded_count: int = 0,
) -> CheckBResult:
    verdicts: List[CheckVerdict] = []
    wellformed: List[Any] = []
    set_aside: Dict[str, str] = {}
    for c in claims:
        problem = claim_problem(c, sources_lookup.get(c.source_id))
        if problem:
            set_aside[c.id] = problem
            verdicts.append(CheckVerdict(
                check_id=CHECK_B_ID, run_id=run_id, object_type="claim", object_id=c.id,
                model_verdict=None, rule_verdict="set_aside", rule_decisive=True, reason_plain=problem,
                details_json={"source_id": c.source_id},
            ))
        else:
            wellformed.append(c)

    n_claims = len(wellformed)
    n_sources = len({c.source_id for c in wellformed})
    passed = n_claims >= min_claims and n_sources >= min_sources
    found = f"{_plural(n_claims, 'usable claim')} from {_plural(n_sources, 'source')}"
    if passed:
        reason = f"{found} (at least {_plural(min_claims, 'claim')} from {_plural(min_sources, 'source')} needed)."
    else:
        reason = f"Only {found}; at least {_plural(min_claims, 'claim')} from {_plural(min_sources, 'source')} are needed."
    notes = []
    if set_aside:
        notes.append(f"{_plural(len(set_aside), 'claim')} {'was' if len(set_aside) == 1 else 'were'} set aside as malformed.")
    if excluded_count:
        notes.append(f"{_plural(excluded_count, 'claim')} {'was' if excluded_count == 1 else 'were'} excluded on the evidence board.")
    if notes:
        reason = f"{reason} {' '.join(notes)}"

    verdicts.append(CheckVerdict(
        check_id=CHECK_B_ID, run_id=run_id, object_type="run", object_id=run_id,
        model_verdict=None, rule_verdict="pass" if passed else "fail", rule_decisive=True, reason_plain=reason,
        details_json={
            "usable_claims": n_claims, "distinct_sources": n_sources,
            "min_claims": min_claims, "min_sources": min_sources,
            "set_aside": len(set_aside), "excluded": excluded_count,
            "claim_ids": [c.id for c in wellformed],
        },
    ))
    return CheckBResult(passed, wellformed, set_aside, verdicts, reason)
