"""Draft view (S5): each finding opens to show the quotes it cites and the hedges in those quotes.

A finding is a native <details> block, so clicking the sentence reveals its evidence without a
rerun. Unbound findings (no ledger claim behind them) carry a visible badge instead of a trace.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional

from src.engine.check_b_wellformed import LOCATION_TAG


def safe_url(url: Any) -> str:
    """Only http(s) links are rendered; anything else (javascript:, data:, empty) becomes '#'."""
    u = str(url or "").strip()
    return u if re.match(r"^https?://", u, re.IGNORECASE) else "#"


# ------------------------------------------------------------------------------
# S29b: readable source names in place of [P#] / [E#] on screen (the ledger and the gates keep the codes)
# ------------------------------------------------------------------------------
_TITLE_STOP = {"a", "an", "the", "of", "on", "in", "for", "to", "and", "or", "with", "by", "from", "at", "as", "is",
               "are", "how", "what", "why", "when", "does", "do", "can", "its", "their", "into", "via", "towards",
               "toward", "using", "study", "studies", "analysis", "evidence"}
KIND_LABELS = {"study": "study", "report": "report / practice", "vendor": "vendor says", "note": "your note"}
TAG_RE = re.compile(r"\[([PE]\d+)(?:\.\d+)?\]")


def _year(value: Any) -> str:
    m = re.match(r"(\d{4})", str(value or "").strip())
    return m.group(1) if m else ""


def _surname(authors: Any) -> str:
    first = authors[0] if isinstance(authors, list) and authors else (str(authors).split(",")[0] if authors else "")
    if isinstance(first, dict):
        first = first.get("name") or first.get("display_name") or ""
    words = [w for w in re.split(r"\s+", str(first or "").strip()) if w]
    return words[-1].strip(".,") if words else ""


def _site(url: Any) -> str:
    host = re.sub(r"^https?://", "", str(url or "")).split("/")[0].split(":")[0].lower()
    host = re.sub(r"^www\.", "", host)
    parts = [p for p in host.split(".") if p]
    name = parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")
    return name[:1].upper() + name[1:]


def _title_words(title: Any, n: int = 3) -> str:
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]+", str(title or "")) if w.lower() not in _TITLE_STOP]
    text = " ".join(words[:n]).lower()
    return text[:1].upper() + text[1:] if text else "Source"


def source_kind(src: Dict[str, Any]) -> str:
    if str(src.get("key") or "").startswith("E") or src.get("lane") == "enterprise":
        return "vendor" if str(src.get("label") or src.get("type") or "") == "Vendor says" else "report"
    return "study"


def source_labels(sources: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """Each source's on-screen name and kind, by rule: a paper is its first author's surname + year (or its first
    content words + year); an enterprise source is its organisation (or site name) + year. Repeats get a/b."""
    out: Dict[str, Dict[str, str]] = {}
    for src in sources or []:
        key = str(src.get("key") or "")
        if not key:
            continue
        kind = source_kind(src)
        if kind == "study":
            base = _surname(src.get("authors")) or _title_words(src.get("title"))
        else:
            base = str(src.get("venue") or src.get("organisation") or "").strip() or _site(src.get("url")) \
                or _title_words(src.get("title"))
        year = _year(src.get("year"))
        out[key] = {"name": f"{base} {year}".strip(), "kind": kind, "title": str(src.get("title") or ""),
                    "year": year, "url": str(src.get("url") or src.get("link") or src.get("doi") or "")}
    counts: Dict[str, int] = {}
    for lab in out.values():
        counts[lab["name"]] = counts.get(lab["name"], 0) + 1
    seen: Dict[str, int] = {}
    for lab in out.values():
        if counts[lab["name"]] > 1:
            n = seen.get(lab["name"], 0)
            seen[lab["name"]] = n + 1
            lab["name"] = lab["name"] + "abcdefghijklmnopqrstuvwxyz"[min(n, 25)]
    return out


def labels_for(paper_map: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    return source_labels([{**(v or {}), "key": k} for k, v in (paper_map or {}).items()])


def source_chip(key: str, labels: Dict[str, Dict[str, str]]) -> str:
    """One named, colour-coded source chip linking to the source; an unknown key stays as plain text."""
    lab = labels.get(key)
    if not lab:
        return html.escape(f"[{key}]")
    url = html.escape(safe_url(lab["url"]), quote=True)
    tip = html.escape(f"{lab['title']} ({lab['year'] or 'n.d.'}) · {KIND_LABELS[lab['kind']]}", quote=True)
    return (f'<a href="{url}" target="_blank" title="{tip}" class="src-chip src-{lab["kind"]}">'
            f'{html.escape(lab["name"])}</a>')


def render_sentence(text: str, paper_map: Optional[Dict[str, Any]] = None,
                    labels: Optional[Dict[str, Dict[str, str]]] = None) -> str:
    """Escape the sentence, then turn its [P#] / [E#] / [P#.n] tags into named source chips (S29b)."""
    escaped = html.escape(str(text or ""))
    labs = labels if labels is not None else labels_for(paper_map)
    out = TAG_RE.sub(lambda m: " " + source_chip(m.group(1), labs), escaped)
    return re.sub(r"\s+(<a [^>]*class=\"src-chip)", r" \1", out).strip()


def _claim_field(c: Any, *names: str) -> str:
    for n in names:
        v = c.get(n) if isinstance(c, dict) else getattr(c, n, None)
        if v:
            return str(v)
    return ""


def quotes_html(claim_ids: List[str], claims_by_id: Optional[Dict[str, Any]], paper_map: Dict[str, Any],
                labels: Dict[str, Dict[str, str]]) -> str:
    """The exact quotes a sentence rests on, each under its source's chip."""
    key_of_id = {str(v.get("id")): k for k, v in (paper_map or {}).items() if isinstance(v, dict) and v.get("id")}
    rows = []
    for cid in claim_ids or []:
        c = (claims_by_id or {}).get(cid)
        if c is None:
            continue
        key = _claim_field(c, "source_key") or key_of_id.get(_claim_field(c, "source_id"), "")
        quote = LOCATION_TAG.sub("", _claim_field(c, "excerpt", "source_excerpt")).strip()
        if quote:
            rows.append(f'<div class="cite-quote">{source_chip(key, labels)} “{html.escape(quote)}”</div>')
    return "".join(rows)


def cited_line_html(text: str, claim_ids: Optional[List[str]], paper_map: Dict[str, Any],
                    claims_by_id: Optional[Dict[str, Any]], css: str = "", tag_html: str = "",
                    labels: Optional[Dict[str, Dict[str, str]]] = None) -> str:
    """A brief line; when it cites claims, clicking it opens the quotes it rests on (S29b)."""
    labs = labels if labels is not None else labels_for(paper_map)
    body = tag_html + render_sentence(text, paper_map, labs)
    quotes = quotes_html(list(claim_ids or []), claims_by_id, paper_map, labs) if claims_by_id else ""
    if not quotes:
        return f'<div class="{css}">{body}</div>'
    return (f'<details class="cite-details {css}"><summary>{body} <span class="cite-hint">quotes ▾</span></summary>'
            f'<div class="cite-quotes">{quotes}</div></details>')


def source_legend_html() -> str:
    return ('<div class="src-legend">Sources: '
            + " ".join(f'<span class="src-chip src-{k}">{html.escape(v)}</span>' for k, v in KIND_LABELS.items() if k != "note")
            + " · click a line to see the quotes it rests on</div>")


def _chip(text: str, bg: str, fg: str) -> str:
    return (
        f'<span style="background:{bg};color:{fg};padding:0.1rem 0.45rem;border-radius:4px;'
        f'font-size:0.7rem;font-weight:700;">{html.escape(text)}</span>'
    )


def _trace_html(tr: Dict[str, Any], labels: Optional[Dict[str, Dict[str, str]]] = None) -> str:
    grade = str(tr.get("grade") or "WEAK").upper()
    grade_bg, grade_fg = {"STRONG": ("#DCFCE7", "#166534"), "MODERATE": ("#DBEAFE", "#1E40AF")}.get(grade, ("#F1F5F9", "#475569"))
    raw_excerpt = str(tr.get("excerpt") or "")
    loc = LOCATION_TAG.search(raw_excerpt)
    quote = LOCATION_TAG.sub("", raw_excerpt)
    hedges: List[str] = list(tr.get("hedge_terms") or [])
    hedge_html = (
        "Hedges in source: " + " ".join(_chip(h, "#FEF3C7", "#92400E") for h in hedges)
        if hedges else '<span style="color:#64748B;">No hedge in source</span>'
    )
    url = html.escape(safe_url(tr.get("url")), quote=True)
    return f"""
    <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px;padding:0.55rem 0.75rem;margin-top:0.45rem;font-size:0.8rem;">
        <div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:0.4rem;margin-bottom:0.3rem;">
            <div>
                {source_chip(str(tr.get('source_key') or 'SRC'), labels or {})}
                <a href="{url}" target="_blank" style="font-weight:700;color:#0F172A;text-decoration:none;margin-left:0.3rem;">{html.escape(str(tr.get('source_title') or 'Source'))} ↗</a>
            </div>
            <div style="display:flex;gap:0.35rem;align-items:center;">
                {_chip(f"GRADE: {grade}", grade_bg, grade_fg)}
                {_chip(f"{tr.get('lane') or 'ACADEMIC'} • {tr.get('study_type') or 'study'}", "#EEF2F6", "#334155")}
            </div>
        </div>
        <div style="color:#334155;font-size:0.8rem;background:#FFFFFF;padding:0.4rem 0.6rem;border-left:3px solid #93C5FD;border-radius:4px;">
            “{html.escape(quote)}”
            <div style="color:#64748B;font-size:0.72rem;margin-top:0.2rem;">
                {html.escape(str(tr.get('venue') or 'n/a'))} • {html.escape(str(tr.get('year') or 'n/a'))}{(' • ' + html.escape(loc.group(1))) if loc else ''} • claim <code>{html.escape(str(tr.get('claim_id') or 'n/a'))}</code>
            </div>
        </div>
        <div style="margin-top:0.35rem;font-size:0.74rem;">{hedge_html}</div>
    </div>"""


def finding_card_html(
    item: Dict[str, Any],
    idx_num: int,
    sentence: str,
    sentence_is_html: bool = False,
    paper_map: Optional[Dict[str, Any]] = None,
) -> str:
    """HTML for one finding. `sentence` is plain text: it is escaped and its [P#] tags become pills
    (via `paper_map`). Pass sentence_is_html=True only for markup built by trusted code."""
    traces = list(item.get("sources_trace") or [])
    unbound = item.get("binding") == "unbound" or not traces
    sentence_html = sentence if sentence_is_html else render_sentence(sentence, paper_map)
    if unbound:
        badge = _chip("Unbound: no citation", "#FEE2E2", "#991B1B")
        body = (
            '<div style="margin-top:0.45rem;font-size:0.8rem;color:#991B1B;">'
            "This sentence cites no ledger claim, so nothing in the evidence backs it. "
            "The gates treat it as ungrounded.</div>"
        )
    else:
        n = len(traces)
        badge = _chip(f"{n} cited quote{'' if n == 1 else 's'}", "#EFF6FF", "#1D4ED8")
        labs = labels_for(paper_map)
        body = "".join(_trace_html(tr, labs) for tr in traces)
    return f"""
    <details class="finding-item" style="padding:0.9rem 1.2rem;margin-bottom:0.9rem;">
        <summary style="cursor:pointer;list-style:none;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.35rem;gap:0.5rem;">
                {_chip(f"FINDING #{idx_num}", "#EFF6FF", "#1D4ED8")}
                <span style="display:flex;gap:0.4rem;align-items:center;">{badge}
                    <span style="font-size:0.72rem;color:#64748B;">Click to {'see why' if unbound else 'show evidence'}</span></span>
            </div>
            <div style="font-size:0.96rem;font-weight:600;color:#0F172A;line-height:1.55;">{sentence_html}</div>
        </summary>
        {body}
    </details>"""


def paper_card_html(p: Dict[str, Any], labels: Optional[Dict[str, Dict[str, str]]] = None) -> str:
    """One Evidence-tab paper card (S11). Built without blank lines (a blank line ends Markdown's HTML
    block and the rest shows as raw code), with escaped text and http(s)-only links."""
    esc = lambda v: html.escape(str(v or ""))
    url = html.escape(safe_url(p.get("url")), quote=True)
    year = str(p.get("year") or "")
    when = f"Published: <strong>{esc(year)}</strong>" if year and year != "Date unknown" else "Date: <em>Date unknown</em>"
    custom = '<span class="paper-tag paper-custom">🏷️ Custom URL</span>' if p.get("is_custom") else ""
    parts = [
        '<div class="paper-card">',
        '<div class="paper-card-head">',
        source_chip(str(p.get("key") or ""), labels or source_labels([p])),
        f'<div>{custom}<span class="paper-tag">{esc(p.get("type"))}</span></div>',
        "</div>",
        f'<div class="paper-card-title"><a href="{url}" target="_blank">{esc(p.get("title"))} ↗</a></div>',
        f'<div class="paper-card-meta">{when} &nbsp;•&nbsp; Venue: <strong>{esc(p.get("venue"))}</strong>'
        + (f' &nbsp;•&nbsp; DOI/URL: <code>{esc(p.get("doi"))}</code>' if p.get("doi") else "")
        + "</div>",
        "</div>",
    ]
    return "".join(parts)



def evidence_map(report: Optional[Dict[str, Any]], papers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Which sub-question sections use which sources (S19b), derived by rule from the report.

    One row per source (in the run's order) with, per section, whether it is cited (in the section's table or its
    sentences' tags) and how many of the section's sentences cite it (S29b), plus its method and a "not cited" note.
    `thin` lists sections backed by fewer than two sources; `unbacked` those no source backs."""
    sections = list((report or {}).get("sections") or [])
    tags = [[{m.group(1) for m in TAG_RE.finditer(str(x.get("text") or ""))} for x in sec.get("sentences") or []]
            for sec in sections]
    cited_by = [{row.get("paper") for row in sec.get("table") or []}.union(*t) for sec, t in zip(sections, tags)]
    method_of: Dict[str, str] = {}
    for sec in sections:
        for row in sec.get("table") or []:
            method_of.setdefault(row.get("paper"), row.get("method") or "not stated")
    labels = source_labels(papers or [])
    rows = []
    for p in papers or []:
        key = p.get("key")
        cited = [key in keys for keys in cited_by]
        counts = [sum(1 for ks in t if key in ks) for t in tags]
        rows.append({"paper": key, "name": (labels.get(key) or {}).get("name", key), "kind": source_kind(p),
                     "title": p.get("title", ""), "method": method_of.get(key, ""), "cited": cited, "counts": counts,
                     "note": "" if any(cited) else "not cited"})
    thin = [sec.get("index", i + 1) for i, (sec, keys) in enumerate(zip(sections, cited_by)) if len(keys) < 2]
    unbacked = [sec.get("index", i + 1) for i, (sec, keys) in enumerate(zip(sections, cited_by)) if not keys]
    return {"sections": [{"index": s.get("index", i + 1), "sub_question": s.get("sub_question", "")}
                         for i, s in enumerate(sections)], "rows": rows, "thin": thin, "unbacked": unbacked,
            "labels": labels}


def evidence_map_html(report: Optional[Dict[str, Any]], papers: List[Dict[str, Any]]) -> str:
    """The evidence map as one HTML table (no blank lines, escaped text): sources down the side by name,
    sub-questions across; empty when the run has no sections."""
    m = evidence_map(report, papers)
    if not m["sections"]:
        return ""
    esc = lambda v: html.escape(str(v or ""))
    cell = "padding:0.35rem 0.5rem;border-bottom:1px solid #E2E8F0;font-size:0.84rem;"
    head = "".join(
        f'<th style="{cell}text-align:center;" title="{esc(s["sub_question"])}">Q{esc(s["index"])}'
        + (' <span style="color:#B45309;">(thin)</span>' if s["index"] in m["thin"] else "") + "</th>"
        for s in m["sections"])
    body = []
    for r in m["rows"]:
        marks = "".join(
            f'<td style="{cell}text-align:center;color:#047857;font-weight:700;white-space:nowrap;">'
            + (f"used · {n}" if n else ("in table" if c else "")) + "</td>"
            for c, n in zip(r["cited"], r["counts"]))
        note = f' <span style="color:#94A3B8;font-style:italic;">({esc(r["note"])})</span>' if r["note"] else ""
        body.append(f'<tr><td style="{cell}">{source_chip(r["paper"], m["labels"])}</td>'
                    f'<td style="{cell}color:#334155;">{esc(r["title"])}{note}</td>'
                    f'<td style="{cell}color:#475569;">{esc(r["method"])}</td>{marks}</tr>')
    if m["unbacked"]:
        gaps = "".join(f'<td style="{cell}text-align:center;color:#B45309;font-weight:700;">'
                       + ("no source" if s["index"] in m["unbacked"] else "") + "</td>" for s in m["sections"])
        body.append(f'<tr><td style="{cell}color:#94A3B8;" colspan="3">Not backed</td>{gaps}</tr>')
    legend = "".join(
        f'<li><b>Q{esc(s["index"])}</b>: {esc(s["sub_question"])}'
        + (' <span style="color:#B45309;">· thin: fewer than two sources</span>' if s["index"] in m["thin"] else "")
        + "</li>" for s in m["sections"])
    return (
        '<div class="evidence-map" style="margin:0.4rem 0 1.2rem 0;overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;background:#FFFFFF;">'
        f'<thead><tr><th style="{cell}text-align:left;">Source</th><th style="{cell}text-align:left;">Title</th>'
        f'<th style="{cell}text-align:left;">Method</th>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
        f'<ul style="margin:0.5rem 0 0 1rem;font-size:0.84rem;color:#475569;">{legend}</ul></div>'
    )


def enterprise_card_html(es: Dict[str, Any], doc: Optional[Dict[str, Any]] = None,
                         labels: Optional[Dict[str, Dict[str, str]]] = None) -> str:
    """One Evidence-tab enterprise source (S22): escaped text (titles come from web pages), http(s)-only links,
    its E# key and reader label when the brief can cite it, and an 'older than 24 months' mark."""
    esc = lambda v: html.escape(str(v or ""))
    doc = doc or {}
    date = es.get("pub_date")
    date_str = date if (date and str(date).lower() not in ("none", "null")) else "Date unknown"
    key = (source_chip(str(doc["key"]), labels or source_labels([doc])) + " ") if doc.get("key") else ""
    label = doc.get("label") or str(es.get("source_type") or "enterprise").replace("_", " ")
    older = ' <span style="color:#B45309;font-weight:700;">· older than 24 months</span>' if doc.get("older") else ""
    return (
        '<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;padding:0.9rem 1.15rem;margin-bottom:0.65rem;">'
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">'
        f'<span>{key}<span style="font-size:0.78rem;font-weight:700;color:#6D28D9;background:#F5F3FF;padding:0.15rem 0.5rem;border-radius:4px;">{esc(label)}</span></span>'
        f'<span style="font-size:0.74rem;color:#64748B;">Commercial stake: <strong>{esc(es.get("commercial_stake") or "unknown")}</strong></span></div>'
        f'<div style="font-weight:700;font-size:0.94rem;margin-bottom:0.25rem;"><a href="{html.escape(safe_url(es.get("url")), quote=True)}" '
        f'target="_blank" style="color:#0F172A;text-decoration:none;">{esc(es.get("title"))} ↗</a></div>'
        f'<div style="font-size:0.8rem;color:#64748B;">Organisation: <strong>{esc(es.get("venue"))}</strong> · Date: <strong>{esc(date_str)}</strong>{older}</div>'
        "</div>"
    )
