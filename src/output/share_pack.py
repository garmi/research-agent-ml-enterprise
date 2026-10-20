"""The share pack (S21): the thought-leadership summary as a post to paste and a one-image card.

Replaces the LinkedIn pack. The post body carries no [P#] tags: sources are listed, numbered, at the end (for the
first comment). Until the run is published, the post opens with a draft line and the card carries a watermark.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional

from src.synth.thought_leadership import strip_tags
from src.ui.diagrams import diagram_svg

DRAFT_LINE = "DRAFT: not yet published. Check and publish the brief before sharing."


def _cited_papers(summary: Dict[str, Any], papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key = {p.get("key"): p for p in papers or []}
    keys = list(dict.fromkeys(k for t in summary.get("takeaways") or [] for k in t.get("papers") or []))
    return [by_key[k] for k in keys if k in by_key]


def post_text(summary: Dict[str, Any], papers: List[Dict[str, Any]], published: bool = False) -> str:
    """The post: hook, opening, numbered takeaways, the leaders turn, nuance, what to watch, one question,
    hashtags; then the numbered sources."""
    paras: List[str] = [] if published else [DRAFT_LINE]
    paras += [summary.get("hook", ""), summary.get("opening", "")]
    paras.append("\n".join(f"{i}. {strip_tags(t['text'])}" for i, t in enumerate(summary.get("takeaways") or [], 1)))
    if summary.get("for_leaders"):
        paras.append(f"What this means for leaders: {summary['for_leaders']}")
    if summary.get("nuance"):
        paras.append(f"The nuance: {summary['nuance']}")
    if summary.get("watch_next"):
        paras.append(f"What to watch: {summary['watch_next']}")
    paras += [summary.get("question", ""), " ".join(summary.get("hashtags") or [])]
    sources = [f"{i}. {p.get('title', '')} ({p.get('year', 'n.d.')}) {p.get('url') or ''}".strip()
               for i, p in enumerate(_cited_papers(summary, papers), 1)]
    body = "\n\n".join(p for p in paras if p)
    return body + ("\n\nSources (first comment):\n" + "\n".join(sources) if sources else "") + "\n"


def _wrap(text: str, width: int, max_lines: int) -> List[str]:
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = re.sub(r"\W*\s*\S*$", "", lines[-1]) + "…"
    return lines


def image_card_svg(summary: Dict[str, Any], diagram: Optional[Dict[str, Any]], published: bool = False) -> str:
    """A 1200x1200 card: the hook, the diagram when there is one, and up to three takeaways."""
    esc = lambda v: html.escape(str(v or ""), quote=True)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 1200" width="1200" height="1200" '
             'font-family="Inter, Arial, sans-serif">',
             '<rect width="1200" height="1200" fill="#FFFFFF"/><rect width="1200" height="14" fill="#2563EB"/>']
    y = 120
    for line in _wrap(summary.get("hook", ""), 36, 3):
        parts.append(f'<text x="60" y="{y}" font-size="52" font-weight="800" fill="#0F172A">{esc(line)}</text>')
        y += 64
    y += 20
    if diagram:
        parts.append(diagram_svg(diagram, marker_id="card-arrow", frame=(60, y, 1080, 430)))
        y += 470
    for i, t in enumerate((summary.get("takeaways") or [])[:3], 1):
        lines = _wrap(strip_tags(t["text"]), 58, 2)
        parts.append(f'<circle cx="82" cy="{y - 10}" r="22" fill="#2563EB"/>'
                     f'<text x="82" y="{y - 1}" font-size="24" font-weight="700" fill="#FFFFFF" text-anchor="middle">{i}</text>')
        for j, line in enumerate(lines):
            parts.append(f'<text x="124" y="{y + j * 38}" font-size="30" fill="#1E293B">{esc(line)}</text>')
        y += 38 * len(lines) + 34
    n = summary.get("n_reviewed")
    parts.append(f'<text x="60" y="1150" font-size="24" fill="#64748B">'
                 f'{esc(f"{n} studies reviewed · sources in the first comment" if n else "Sources in the first comment")}</text>')
    parts.append('<text x="1140" y="1150" font-size="24" font-weight="700" fill="#2563EB" text-anchor="end">AI Guruji</text>')
    if not published:
        parts.append('<text x="600" y="640" font-size="200" font-weight="800" fill="#DC2626" fill-opacity="0.12" '
                     'text-anchor="middle" transform="rotate(-30 600 600)">DRAFT</text>')
    parts.append("</svg>")
    return "".join(parts)
