"""Brief (S8): the run's draft read as an executive brief. Every piece of model or source text is escaped."""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional


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


# ------------------------------------------------------------------------------
# S19: the question-shaped report
# ------------------------------------------------------------------------------
def _confidence_badge(conf: Dict[str, Any]) -> str:
    if not conf:
        return ""
    level = str(conf.get("level") or "low")
    return (f'<span class="conf-badge conf-{plain_html(level)}">Confidence: {plain_html(level)} · '
            f'{int(conf.get("papers") or 0)} papers · {int(conf.get("empirical") or 0)} empirical</span>')


def _evidence_table_html(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    head = "<tr><th>Paper</th><th>Method</th><th>What it found</th><th>Grade</th></tr>"
    body = "".join(
        f"<tr><td>{plain_html(r.get('paper'))}</td><td>{plain_html(r.get('method'))}</td>"
        f"<td>{plain_html(r.get('finding') or r.get('title'))}</td><td>{plain_html(r.get('grade'))}</td></tr>"
        for r in rows
    )
    return f'<table class="ev-table">{head}{body}</table>'


def report_blocks(report: Dict[str, Any], paper_map: Dict[str, Any], findings_by_text: Dict[str, Dict[str, Any]],
                  meta: str = "", negatives: Optional[List[str]] = None) -> List[str]:
    """The Brief tab for a question-shaped report, as separate HTML blocks (one st.markdown each: finding cards
    contain blank lines, which end a Markdown HTML block, so they cannot share one call). Model text is escaped by
    render_sentence; evidence sentences keep their click-to-see-the-quotes cards."""
    from src.ui.evidence_view import finding_card_html, render_sentence

    answer = report.get("answer") or {}
    blocks = [
        '<div class="report-answer"><div class="report-answer-head"><h3>Answer in brief</h3>'
        f'{_confidence_badge(answer.get("confidence") or {})}</div>'
        f'<p>{render_sentence(answer.get("text", ""), paper_map)}</p></div>'
    ]
    if meta:
        blocks.append(f'<div class="brief-meta">{plain_html(meta)}</div>')
    card_no = 0
    for sec in report.get("sections") or []:
        blocks.append(f'<div class="report-section-head"><h3>{int(sec.get("index") or 0)}. '
                      f'{plain_html(sec.get("sub_question"))}</h3>{_confidence_badge(sec.get("confidence") or {})}</div>')
        if not sec.get("sentences"):
            blocks.append('<p class="report-empty">The papers found say nothing on this sub-question.</p>')
        for s in sec.get("sentences") or []:
            item = findings_by_text.get(str(s.get("text", "")).strip())
            if s.get("type") == "assertive" and item:
                card_no += 1
                blocks.append(finding_card_html(item, card_no, item.get("text", ""), paper_map=paper_map))
            else:
                label = "Synthesis" if s.get("type") == "synthesis" else "Evidence"
                blocks.append(f'<div class="{"sy-line" if label == "Synthesis" else "ev-line"}"><span class="line-tag">{label}</span>'
                              f'{render_sentence(s.get("text", ""), paper_map)}</div>')
        if sec.get("table"):
            blocks.append(_evidence_table_html(sec["table"]))
    if report.get("tensions"):
        blocks.append('<h3 class="report-h">Where studies disagree</h3>' + "".join(
            f'<div class="sy-line">{render_sentence(t.get("text", ""), paper_map)}</div>' for t in report["tensions"]))
    gaps = list(report.get("gaps") or []) + [{"text": n} for n in negatives or []]
    if gaps:
        blocks.append('<h3 class="report-h">What we don\'t know</h3><ul class="report-list">' + "".join(
            f'<li>{render_sentence(g.get("text", ""), paper_map)}</li>' for g in gaps) + "</ul>")
    if report.get("implications"):
        blocks.append('<h3 class="report-h">Implications</h3><ol class="report-list">' + "".join(
            f'<li>{render_sentence(i.get("text", ""), paper_map)}'
            + (f' <span class="line-tag">From section {int(i["section"])}</span>' if i.get("section") else "")
            + "</li>" for i in report["implications"]) + "</ol>")
    return blocks


def report_html(*args: Any, **kwargs: Any) -> str:
    """All report blocks as one string (for exports and tests; the Brief tab renders the blocks one by one)."""
    return "\n".join(report_blocks(*args, **kwargs))


def report_markdown(report: Dict[str, Any], question: str = "") -> str:
    """The brief download for a question-shaped report, in the same order as the Brief tab."""
    lines = [f"# {question}" if question else "# Research brief", ""]
    answer = report.get("answer") or {}
    conf = answer.get("confidence") or {}
    lines += ["## Answer in brief", answer.get("text", "")]
    if conf:
        lines.append(f"_Confidence: {conf.get('level')} · {conf.get('papers', 0)} papers · {conf.get('empirical', 0)} empirical_")
    lines.append("")
    for sec in report.get("sections") or []:
        lines += [f"## {sec.get('index')}. {sec.get('sub_question')}", ""]
        for s in sec.get("sentences") or []:
            prefix = "**Synthesis.** " if s.get("type") == "synthesis" else ""
            lines.append(f"- {prefix}{s.get('text', '')}")
        rows = sec.get("table") or []
        if rows:
            lines += ["", "| Paper | Title | Method | What it found | Grade |", "|---|---|---|---|---|"]
            lines += [f"| {_md_cell(r.get('paper'))} | {_md_cell(r.get('title'))} | {_md_cell(r.get('method'))} | "
                      f"{_md_cell(r.get('finding'))} | {_md_cell(r.get('grade'))} |" for r in rows]
        lines.append("")
    if report.get("tensions"):
        lines += ["## Where studies disagree"] + [f"- {t.get('text', '')}" for t in report["tensions"]] + [""]
    if report.get("gaps"):
        lines += ["## What we don't know"] + [f"- {g.get('text', '')}" for g in report["gaps"]] + [""]
    if report.get("implications"):
        lines += ["## Implications"] + [
            f"{n}. {i.get('text', '')}" + (f" _(from section {i['section']})_" if i.get("section") else "")
            for n, i in enumerate(report["implications"], 1)] + [""]
    return "\n".join(lines)
