"""Term normalization and integrity checking for atomic claim extraction.

Protects against hallucinations and corrupted terms of art (e.g. the 'vibrate coding' failure).
Ensures that key technical terms in extracted claims actually exist in the source text.
"""

from __future__ import annotations

import re
from typing import List, Tuple


KNOWN_CORRUPTIONS = {
    "vibrate coding": "vibe coding",
}


def normalize_term(term: str) -> str:
    """Normalize whitespace and lowercasing for term matching."""
    return re.sub(r"\s+", " ", term.strip().lower())


def check_term_integrity(
    claim_text: str,
    source_text: str,
    key_terms: List[str],
) -> Tuple[bool, List[str]]:
    """Verify that key technical terms in a claim appear in the source text.

    Args:
        claim_text: The paraphrased claim text.
        source_text: The original source text (abstract or excerpt).
        key_terms: List of specific domain terms extracted in the claim.

    Returns:
        (is_valid, list of warning messages)
    """
    warnings: List[str] = []
    norm_source = normalize_term(source_text)
    norm_claim = normalize_term(claim_text)

    # Check for known corruptions
    for corrupted, correct in KNOWN_CORRUPTIONS.items():
        if corrupted in norm_claim:
            warnings.append(
                f"Corrupted term of art detected: '{corrupted}'. Expected: '{correct}'."
            )

    # Check that key technical terms exist in source
    for term in key_terms:
        norm_term = normalize_term(term)
        if norm_term not in norm_source:
            # Check if source contains a near match that was corrupted
            for corrupted, correct in KNOWN_CORRUPTIONS.items():
                if norm_term == corrupted and correct in norm_source:
                    warnings.append(
                        f"Term '{term}' is a corrupted variation of source term '{correct}'."
                    )
                    break
            else:
                warnings.append(
                    f"Key term '{term}' does not appear in source text."
                )

    is_valid = len(warnings) == 0
    return is_valid, warnings
