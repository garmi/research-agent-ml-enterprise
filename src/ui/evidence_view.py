"""Draft view (S5): each finding opens to show the quotes it cites and the hedges in those quotes.

A finding is a native <details> block, so clicking the sentence reveals its evidence without a
rerun. Unbound findings (no ledger claim behind them) carry a visible badge instead of a trace.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, List

_LOCATION_TAG = re.compile(r"\s*\(Location:\s*([^)]*)\)\s*$")


def _chip(text: str, bg: str, fg: str) -> str:
    return (
        f'<span style="background:{bg};color:{fg};padding:0.1rem 0.45rem;border-radius:4px;'
        f'font-size:0.7rem;font-weight:700;">{html.escape(text)}</span>'
    )


def _trace_html(tr: Dict[str, Any]) -> str:
    grade = str(tr.get("grade") or "WEAK").upper()
    grade_bg, grade_fg = {"STRONG": ("#DCFCE7", "#166534"), "MODERATE": ("#DBEAFE", "#1E40AF")}.get(grade, ("#F1F5F9", "#475569"))
    raw_excerpt = str(tr.get("excerpt") or "")
    loc = _LOCATION_TAG.search(raw_excerpt)
    quote = _LOCATION_TAG.sub("", raw_excerpt)
    hedges: List[str] = list(tr.get("hedge_terms") or [])
    hedge_html = (
        "Hedges in source: " + " ".join(_chip(h, "#FEF3C7", "#92400E") for h in hedges)
        if hedges else '<span style="color:#64748B;">No hedge in source</span>'
    )
    url = html.escape(str(tr.get("url") or "#"), quote=True)
    return f"""
    <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px;padding:0.55rem 0.75rem;margin-top:0.45rem;font-size:0.8rem;">
        <div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:0.4rem;margin-bottom:0.3rem;">
            <div>
                <a href="{url}" target="_blank" class="cite-pill">[{html.escape(str(tr.get('source_key') or 'SRC'))}]</a>
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


def finding_card_html(item: Dict[str, Any], idx_num: int, sentence: str, sentence_is_html: bool = True) -> str:
    """HTML for one finding. `sentence` is the display text (citation pills already applied when
    `sentence_is_html` is True; escaped otherwise)."""
    traces = list(item.get("sources_trace") or [])
    unbound = item.get("binding") == "unbound" or not traces
    sentence_html = sentence if sentence_is_html else html.escape(sentence)
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
        body = "".join(_trace_html(tr) for tr in traces)
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
