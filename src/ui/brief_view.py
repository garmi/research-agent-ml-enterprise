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
            f'{int(conf.get("papers") or 0)} papers · {int(conf.get("empirical") or 0)} empirical'
            + (f' · {int(conf["practice"])} practice' if conf.get("practice") else "") + "</span>")


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
                  meta: str = "", negatives: Optional[List[str]] = None, diagram: Optional[Dict[str, Any]] = None,
                  observations: Optional[Dict[int, List[str]]] = None,
                  claims_by_id: Optional[Dict[str, Any]] = None) -> List[str]:
    """The Brief tab for a question-shaped report, as separate HTML blocks (one st.markdown each: finding cards
    contain blank lines, which end a Markdown HTML block, so they cannot share one call). Model text is escaped by
    render_sentence; evidence sentences keep their click-to-see-the-quotes cards. S29b: sources show as named chips,
    and every line with `claims_by_id` opens to the quotes it rests on."""
    from src.ui.evidence_view import cited_line_html, finding_card_html, labels_for, source_legend_html

    labels = labels_for(paper_map)
    line = lambda item, css="", tag="": cited_line_html(item.get("text", ""), item.get("claim_ids"), paper_map,
                                                        claims_by_id, css=css, tag_html=tag, labels=labels)
    answer = report.get("answer") or {}
    blocks = [
        '<div class="report-answer"><div class="report-answer-head"><h3>Answer in brief</h3>'
        f'{_confidence_badge(answer.get("confidence") or {})}</div>'
        f'{line(answer, "answer-line")}'
        + ('<p class="line-tag" style="color:#B45309;">Check D: this answer is only partly supported by the quotes it cites.</p>'
           if answer.get("support") == "partial" else "")
        + ('<p class="line-tag" style="color:#991B1B;">Check D: this answer is not supported by the quotes it cites.</p>'
           if answer.get("support") == "unsupported" else "")
        + '</div>',
        source_legend_html(),
    ]
    if meta:
        blocks.append(f'<div class="brief-meta">{plain_html(meta)}</div>')
    if diagram:
        # S20: the validated diagram sits right after the answer; each box names the papers it rests on.
        from src.ui.diagrams import diagram_svg

        blocks.insert(1, f'<div class="report-diagram"><h3>{plain_html(diagram.get("title"))}</h3>{diagram_svg(diagram, labels={k: v["name"] for k, v in labels.items()})}'
                         '<div class="line-tag" style="font-size:0.78rem;">Each box names the sources it rests on.</div></div>')
    card_no = 0
    for sec in report.get("sections") or []:
        blocks.append(f'<div class="report-section-head"><h3>{int(sec.get("index") or 0)}. '
                      f'{plain_html(sec.get("sub_question"))}</h3>{_confidence_badge(sec.get("confidence") or {})}</div>')
        if not sec.get("sentences"):
            blocks.append('<p class="report-empty">The papers found say nothing on this sub-question.</p>')
        for s in sec.get("sentences") or []:
            item = findings_by_text.get(str(s.get("text", "")).strip())
            if s.get("type") == "assertive" and item and s.get("support") != "partial":
                card_no += 1
                blocks.append(finding_card_html(item, card_no, item.get("text", ""), paper_map=paper_map))
            else:
                label = "Synthesis" if s.get("type") == "synthesis" else "Evidence"
                partial = ('<span class="line-tag" style="color:#B45309;">Partly supported</span>'
                           if s.get("support") == "partial" else "")
                blocks.append(line(s, "sy-line" if label == "Synthesis" else "ev-line",
                                   f'<span class="line-tag">{label}</span>{partial}'))
        if sec.get("table"):
            blocks.append(_evidence_table_html(sec["table"]))
        # S26: your field notes that match this section, by rule; shown in the app only, never in exports.
        for obs in (observations or {}).get(int(sec.get("index") or 0), []):
            blocks.append(f'<div class="obs-line"><span class="line-tag">Your observation · not peer-reviewed</span> '
                          f'{plain_html(obs)}</div>')
    if report.get("tensions"):
        blocks.append('<h3 class="report-h">Where studies disagree</h3>' + "".join(
            line(t, "sy-line") for t in report["tensions"]))
    gaps = list(report.get("gaps") or []) + [{"text": n} for n in negatives or []]
    if gaps:
        blocks.append('<h3 class="report-h">What we don\'t know</h3><ul class="report-list">' + "".join(
            f'<li>{line(g)}</li>' for g in gaps) + "</ul>")
    if report.get("implications"):
        items = []
        for i in report["implications"]:
            tag = f'<span class="line-tag">From section {int(i["section"])}</span> ' if i.get("section") else ""
            items.append(f"<li>{line(i, tag=tag)}</li>")
        blocks.append('<h3 class="report-h">Implications</h3><ol class="report-list">' + "".join(items) + "</ol>")
    return blocks


def report_html(*args: Any, **kwargs: Any) -> str:
    """All report blocks as one string (for exports and tests; the Brief tab renders the blocks one by one)."""
    return "\n".join(report_blocks(*args, **kwargs))


def report_markdown(report: Dict[str, Any], question: str = "", diagram: Optional[Dict[str, Any]] = None,
                    papers: Optional[List[Dict[str, Any]]] = None) -> str:
    """The brief download for a question-shaped report, in the same order as the Brief tab. With `papers` (S29b),
    tags read as source names ("(Chen 2024)") and the brief ends with a numbered source list."""
    import re

    from src.ui.evidence_view import source_labels

    labels = source_labels(papers or [])

    def T(text: Any) -> str:
        if not labels:
            return str(text or "")

        def names(m: "re.Match[str]") -> str:
            keys = re.findall(r"\[([PE]\d+)(?:\.\d+)?\]", m.group(0))
            known = [labels[k]["name"] for k in dict.fromkeys(keys) if k in labels]
            return f" ({'; '.join(known)})" if known else m.group(0)

        return re.sub(r"\s*(?:\[[PE]\d+(?:\.\d+)?\])+", names, str(text or ""))

    name = lambda key: labels.get(str(key), {}).get("name", key)
    lines = [f"# {question}" if question else "# Research brief", ""]
    answer = report.get("answer") or {}
    conf = answer.get("confidence") or {}
    lines += ["## Answer in brief", T(answer.get("text", ""))]
    if conf:
        lines.append(f"_Confidence: {conf.get('level')} · {conf.get('papers', 0)} papers · {conf.get('empirical', 0)} empirical_")
    lines.append("")
    if diagram:
        from src.synth.diagram import diagram_outline

        lines += [f"## {diagram.get('title')}", ""] + [f"- {ln}" for ln in diagram_outline(diagram)] + [""]
    for sec in report.get("sections") or []:
        lines += [f"## {sec.get('index')}. {sec.get('sub_question')}", ""]
        for s in sec.get("sentences") or []:
            prefix = "**Synthesis.** " if s.get("type") == "synthesis" else ""
            lines.append(f"- {prefix}{T(s.get('text', ''))}")
        rows = sec.get("table") or []
        if rows:
            lines += ["", "| Source | Title | Method | What it found | Grade |" if labels else
                      "| Paper | Title | Method | What it found | Grade |", "|---|---|---|---|---|"]
            lines += [f"| {_md_cell(name(r.get('paper')))} | {_md_cell(r.get('title'))} | {_md_cell(r.get('method'))} | "
                      f"{_md_cell(r.get('finding'))} | {_md_cell(r.get('grade'))} |" for r in rows]
        lines.append("")
    if report.get("tensions"):
        lines += ["## Where studies disagree"] + [f"- {T(t.get('text', ''))}" for t in report["tensions"]] + [""]
    if report.get("gaps"):
        lines += ["## What we don't know"] + [f"- {T(g.get('text', ''))}" for g in report["gaps"]] + [""]
    if report.get("implications"):
        lines += ["## Implications"] + [
            f"{n}. {T(i.get('text', ''))}" + (f" _(from section {i['section']})_" if i.get("section") else "")
            for n, i in enumerate(report["implications"], 1)] + [""]
    if papers:
        from src.ui.evidence_view import evidence_map

        m = evidence_map(report, papers)
        if m["sections"]:
            qs = [f"Q{sec['index']}" for sec in m["sections"]]
            lines += ["## Evidence map", "", "| Source | Title | Method | " + " | ".join(qs) + " |",
                      "|---|---|---|" + "---|" * len(qs)]
            lines += [f"| {_md_cell(r['name'])} | {_md_cell(r['title'])} | {_md_cell(r['method'] or r['note'])} | "
                      + " | ".join("●" if c else "" for c in r["cited"]) + " |" for r in m["rows"]]
            lines += [""] + [f"- Q{sec['index']}: {sec['sub_question']}" + (" (thin: fewer than two papers)" if sec["index"] in m["thin"] else "")
                             for sec in m["sections"]] + [""]
    if labels:
        lines += ["## Sources", ""]
        for n, p in enumerate(papers or [], 1):
            lab = labels.get(str(p.get("key")))
            if not lab:
                continue
            bits = [str(b) for b in (p.get("venue") or p.get("label"), lab["year"]) if b]
            lines.append(f"{n}. {lab['name']} — {p.get('title', '')}" + (f". {', '.join(bits)}" if bits else "")
                         + (f". {lab['url']}" if lab["url"].startswith("http") else ""))
        lines.append("")
    return "\n".join(lines)
