"""Deterministic fixed lenses (Slice S1 Task 2).

Defines 4 fixed problem lenses:
- Empirical effect
- Adoption and practice
- Risks and controls
- Costs and trade-offs

All fields (id, title, focus, counts_as_evidence, out_of_scope) are fixed template text
containing ZERO user words. The user's question is shown once, verbatim (original casing,
never rewritten, never embedded in lens text).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class FramingLens:
    id: str
    title: str
    focus: str
    counts_as_evidence: str
    out_of_scope: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "focus": self.focus,
            "counts_as_evidence": self.counts_as_evidence,
            "out_of_scope": self.out_of_scope,
        }


FIXED_LENSES: List[FramingLens] = [
    FramingLens(
        id="empirical-effect",
        title="Empirical effect",
        focus="what measured outcomes and effects have been reported",
        counts_as_evidence="studies and reports with data such as trials, case studies, benchmarks",
        out_of_scope="opinions, vendor claims without data, forecasts",
    ),
    FramingLens(
        id="adoption-and-practice",
        title="Adoption and practice",
        focus="how organizations actually use this",
        counts_as_evidence="documented use at named organizations, practitioner accounts labelled as such",
        out_of_scope="controlled effect sizes",
    ),
    FramingLens(
        id="risks-and-controls",
        title="Risks and controls",
        focus="what can go wrong and what controls or governance are used",
        counts_as_evidence="incident reports, audits, standards, governance documents",
        out_of_scope="productivity or cost outcomes",
    ),
    FramingLens(
        id="costs-and-trade-offs",
        title="Costs and trade-offs",
        focus="what it costs and what is given up",
        counts_as_evidence="cost and effort data, comparisons with alternatives",
        out_of_scope="technical benchmarks unrelated to cost",
    ),
]

LENS_TEMPLATES = FIXED_LENSES
Framing = FramingLens


def generate_framings(question_text: str = "") -> List[FramingLens]:
    """Return the fixed problem lenses.

    Fields are fixed template text containing zero user words.
    The user question is handled separately and displayed verbatim.
    """
    return list(FIXED_LENSES)


def get_lens_by_id(lens_id: str) -> Optional[FramingLens]:
    """Return the FramingLens matching the given lens_id, or None if not found."""
    for lens in FIXED_LENSES:
        if lens.id == lens_id:
            return lens
    return None

