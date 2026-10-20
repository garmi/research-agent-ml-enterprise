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
    """What a step rests on: the findings it builds on and figures not in its evidence (S10)."""
    builds_on = step.get("builds_on") or []
    parts = [
        f'<div class="roadmap-basis">Builds on finding{"s" if len(builds_on) > 1 else ""} '
        f'{plain_html(", ".join(str(n) for n in builds_on))}</div>'
        if builds_on else '<div class="roadmap-flag">⚠ Not tied to a finding</div>'
    ]
    parts += [
        f'<div class="roadmap-flag">⚠ {plain_html(n)} is not a figure from the cited evidence</div>'
        for n in step.get("unsupported_numbers") or []
    ]
    return "".join(parts)


def roadmap_html(roadmap: List[Dict[str, Any]]) -> str:
    """Roadmap steps, labelled as recommendations: they are not checked against evidence (G1-G4), so
    each one shows what it rests on instead. Steps are grouped by phase, and each phase's KPI is shown
    once at its head (S17; it is a phase target, not a per-step one)."""
    groups: List[Dict[str, Any]] = []
    for s in roadmap or []:
        if not groups or groups[-1]["phase"] != s.get("phase"):
            groups.append({"phase": s.get("phase"), "measure": s.get("measure") or "", "steps": []})
        groups[-1]["steps"].append(s)
    html_parts = ['<div class="roadmap-note">Recommendations, not evidence: these steps are not checked against sources.</div>']
    for g in groups:
        measure = f'<span class="roadmap-impact">Measure: {plain_html(g["measure"])}</span>' if g["measure"] else ""
        html_parts.append(
            f'<div class="roadmap-phase-head"><span class="roadmap-phase">{plain_html(g["phase"])}</span>{measure}</div>'
        )
        html_parts += [
            f'<div class="roadmap-item"><div><div class="roadmap-action">{plain_html(s.get("action"))}</div>'
            f'{_roadmap_basis(s)}</div></div>'
            for s in g["steps"]
        ]
    return "".join(html_parts)


_STOP_TITLE = {
    "check_a": ("Run stopped: not enough on-topic evidence",
                "Rephrase or widen the question in Step 1 (name the subject plainly, e.g. AI code generation), then run again."),
    "check_b": ("Run stopped: too few usable claims",
                "Add sources, or re-include claims on the Evidence tab, then re-draft."),
}


def _md_cell(value: Any) -> str:
    return " ".join(str(value or "").split()).replace("|", "\\|")


def stopped_run_markdown(results: Dict[str, Any]) -> str:
    """The download for a run a handoff check stopped (S13): why it stopped and what was judged,
    instead of an empty brief template. Nothing was drafted, so there are no findings to show."""
    title, next_step = _STOP_TITLE.get(results.get("stopped_at") or "",
                                       ("Run stopped before drafting", "Run it again."))
    lines = [
        f"# {title}",
        "",
        f"**Question:** {results.get('strategic_question') or ''}",
        "",
        f"**Status:** {results.get('status') or ''}",
        "",
        "## Why it stopped",
    ]
    reasons = list((results.get("publish_res") or {}).get("reasons") or [])
    stop_reason = results.get("stop_reason")
    if stop_reason and not any(stop_reason in r for r in reasons):
        reasons.append(stop_reason)
    lines += [f"- {r}" for r in reasons or ["No reason was recorded."]]
    sources = (results.get("check_a") or {}).get("sources") or []
    if sources:
        lines += ["", "## Sources judged by Check A", "", "| Source | Lane | Verdict | Why |", "|---|---|---|---|"]
        lines += [
            f"| {_md_cell(s.get('title'))} | {_md_cell(str(s.get('lane', '')).capitalize())} | "
            f"{'On-topic' if s.get('verdict') == 'on_topic' else 'Off-topic'} | {_md_cell(s.get('reason'))} |"
            for s in sources
        ]
    lines += ["", "## What to do next", f"- {next_step}", ""]
    return "\n".join(lines)
