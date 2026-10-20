"""The "Summary & share" tab (S21): the thought-leadership summary as read in the app, and the PNG step.

Model text is escaped (render_sentence / html.escape); takeaways keep their [P#] pills in the app and show
"N papers · method" beneath, while the post built for sharing has no tags (src/output/share_pack.py).
"""

from __future__ import annotations

import base64
import html
from typing import Any, Dict


def summary_missing_reason(results: Dict[str, Any]) -> str:
    if results.get("stopped_at"):
        return "This run stopped before writing a brief, so there is no summary to share."
    if results.get("is_fallback"):
        return ("The summary is written by the model from the checked report. This run used the extractive fallback "
                "(no model), so there is no summary. Run again with the model available.")
    if not results.get("report"):
        return "This run was saved before summaries existed. Run the question again to get one."
    return "No takeaway passed the checks (each must cite this run's evidence and add no figure it lacks), so no summary is shown."


def summary_html(summary: Dict[str, Any], paper_map: Dict[str, Any]) -> str:
    from src.ui.evidence_view import render_sentence

    esc = lambda v: html.escape(str(v or ""))
    items = "".join(
        f'<li><div>{render_sentence(t["text"], paper_map)}</div><div class="line-tag">{esc(t.get("basis"))}</div></li>'
        for t in summary.get("takeaways") or [])
    extra = "".join(
        f'<p><b>{label}</b> {esc(summary.get(key))}</p>'
        for label, key in (("What this means for leaders:", "for_leaders"), ("The nuance:", "nuance"),
                           ("What to watch:", "watch_next")) if summary.get(key))
    tags = " ".join(esc(h) for h in summary.get("hashtags") or [])
    return (
        '<div class="tl-summary">'
        f'<div class="tl-hook">{esc(summary.get("hook"))}</div>'
        f'<p>{esc(summary.get("opening"))}</p>'
        f'<ol class="tl-takeaways">{items}</ol>{extra}'
        f'<p class="tl-question">{esc(summary.get("question"))}</p>'
        f'<p class="line-tag">{tags}</p></div>'
    )


def png_download_html(svg: str, file_name: str = "share_card.png") -> str:
    """A small page for st.components: draws the card SVG on a 1200x1200 canvas in the browser and offers the PNG."""
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    name = html.escape(file_name, quote=True)
    return f"""<div style="font-family:Inter,Arial,sans-serif;">
<a id="png" href="#" download="{name}" style="display:inline-block;padding:0.45rem 0.9rem;border:1px solid #CBD5E1;
border-radius:8px;color:#0F172A;text-decoration:none;font-size:14px;">Preparing PNG…</a></div>
<script>
const img = new Image();
img.onload = () => {{
  const c = document.createElement("canvas"); c.width = 1200; c.height = 1200;
  c.getContext("2d").drawImage(img, 0, 0, 1200, 1200);
  const a = document.getElementById("png"); a.href = c.toDataURL("image/png"); a.textContent = "🖼️ Image card (.png)";
}};
img.onerror = () => {{ document.getElementById("png").textContent = "PNG not available in this browser; use the SVG"; }};
img.src = "data:image/svg+xml;base64,{data}";
</script>"""


def card_preview_html(svg: str) -> str:
    return f'<div class="share-card">{svg}</div>'

