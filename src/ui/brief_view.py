"""Brief (S8): the run's draft read as an executive brief. Every piece of model or source text is escaped."""

from __future__ import annotations

import html
from typing import Any, Dict, List


def plain_html(text: Any) -> str:
    return html.escape(str(text or ""))


def brief_meta_line(results: Dict[str, Any]) -> str:
    """One line in place of the four metric tiles: what the brief rests on."""
    metrics = results.get("metrics") or {}
    parts = [
        f"{len(results.get('papers') or [])} papers",
        f"{len(results.get('enterprise_sources') or [])} enterprise sources",
        f"{len(results.get('practitioner_observations') or [])} field notes",
        f"{len(results.get('claims') or [])} claims",
    ]
    if metrics.get("horizon"):
        parts.append(str(metrics["horizon"]))
    if metrics.get("quality"):
        # The score only: the run's status is the banner's job, so the two can never disagree.
        parts.append("Score " + str(metrics["quality"]).split(" (")[0])
    return " · ".join(parts)


def distinct_signals(signals: List[Dict[str, Any]], findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Signals that say something the findings do not (signals copied from findings are dropped)."""
    finding_texts = {" ".join(str(f.get("text", "")).split()) for f in findings or []}
    return [s for s in signals or [] if " ".join(str(s.get("text", "")).split()) not in finding_texts]


def roadmap_html(roadmap: List[Dict[str, Any]]) -> str:
    """Roadmap steps, labelled as recommendations: they are not checked against evidence (G1-G4)."""
    items = "".join(
        f'<div class="roadmap-item"><span class="roadmap-phase">{plain_html(s.get("phase"))}</span>'
        f'<div><div class="roadmap-action">{plain_html(s.get("action"))}</div>'
        f'<div class="roadmap-impact">Expected outcome: {plain_html(s.get("impact"))}</div></div></div>'
        for s in roadmap or []
    )
    return f'<div class="roadmap-note">Recommendations, not evidence: these steps are not checked against sources.</div>{items}'
