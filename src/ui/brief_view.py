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


def _roadmap_basis(step: Dict[str, Any]) -> str:
    """What a step rests on: the findings it builds on, its KPI, and figures not in its evidence (S10)."""
    builds_on = step.get("builds_on") or []
    parts = [
        f'<div class="roadmap-basis">Builds on finding{"s" if len(builds_on) > 1 else ""} '
        f'{plain_html(", ".join(str(n) for n in builds_on))}</div>'
        if builds_on else '<div class="roadmap-flag">⚠ Not tied to a finding</div>'
    ]
    if step.get("measure"):
        parts.append(f'<div class="roadmap-impact">Measure: {plain_html(step["measure"])}</div>')
    parts += [
        f'<div class="roadmap-flag">⚠ {plain_html(n)} is not a figure from the cited evidence</div>'
        for n in step.get("unsupported_numbers") or []
    ]
    return "".join(parts)


def roadmap_html(roadmap: List[Dict[str, Any]]) -> str:
    """Roadmap steps, labelled as recommendations: they are not checked against evidence (G1-G4),
    so each one shows what it rests on instead."""
    items = "".join(
        f'<div class="roadmap-item"><span class="roadmap-phase">{plain_html(s.get("phase"))}</span>'
        f'<div><div class="roadmap-action">{plain_html(s.get("action"))}</div>{_roadmap_basis(s)}</div></div>'
        for s in roadmap or []
    )
    return f'<div class="roadmap-note">Recommendations, not evidence: these steps are not checked against sources.</div>{items}'
