"""Your own copies (S29c): the brief, claims, ledger, post and card always download, whatever the gates say.

A run not cleared for publishing gives copies marked as drafts: the file name ends in _DRAFT and the file opens
with why it is not cleared (failing gates, publish reasons, a low score) and Check D's in-brief support rate, so a
copy kept for later still says what it is. Sentences Check D removed are never in a copy. Publishing stays gated.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List, Optional, Tuple

CLEARED = ("PUBLISH_READY", "PUBLISHED")
HEADER = "DRAFT for personal use — not cleared for publishing"


def is_cleared(results: Dict[str, Any]) -> bool:
    return str(results.get("status") or "").upper() in CLEARED


def draft_reasons(results: Dict[str, Any]) -> List[str]:
    """Why the run is not cleared: each gate that did not pass, the publish reasons, and a score below 70."""
    out: List[str] = []
    gates = ((results.get("gates_audit") or {}).get("gates")
             or ((results.get("publish_res") or {}).get("gate_results") or {}).get("gates") or {})
    for name, g in gates.items():
        if isinstance(g, dict) and not g.get("pass"):
            label = name.split("_", 1)[0] + " " + name.split("_", 1)[1].replace("_", " ") if "_" in name else name
            # The summary only ("2 problems found"); the details are on Checks & share.
            reason = " ".join(str(g.get("reason_plain") or g.get("state") or "did not pass").split()).split(" First:")[0]
            out.append(f"{label}: {reason[:160] + ('…' if len(reason) > 160 else '')}")
    listed = {line.split()[0] for line in out}  # gates already named above ("G1", "G2", ...)
    for r in (results.get("publish_res") or {}).get("reasons") or []:
        r = " ".join(str(r or "").split()).split(" First:")[0]
        if r and r not in out and r.split(":")[0] not in listed:
            out.append(r)
    score = (results.get("quality_scorecard") or {}).get("total_score")
    if isinstance(score, (int, float)) and score < 70:
        out.append(f"Quality score {score:g} (below 70)")
    if results.get("stopped_at"):
        out.append(f"The run stopped at {str(results['stopped_at']).replace('_', ' ')}")
    return out or [f"Status {results.get('status') or 'unknown'}"]


def check_d_line(results: Dict[str, Any]) -> str:
    cd = results.get("check_d") or {}
    if cd.get("in_brief"):
        return (f"Check D: {int(cd.get('supported_in_brief') or 0)} of {int(cd['in_brief'])} sentences in this brief "
                "are supported by their quotes")
    return "Check D: not run for this brief"


def header_lines(results: Dict[str, Any]) -> List[str]:
    from src.ui.engine_switch import engine_line

    return [HEADER, "Why: " + "; ".join(draft_reasons(results)), check_d_line(results)] + \
        ([engine_line(results)] if engine_line(results) else [])


def _removed_texts(results: Dict[str, Any]) -> List[str]:
    return [str(r.get("text")) for r in (results.get("check_d") or {}).get("removed") or [] if r.get("text")]


def _scrub(obj: Any, removed: List[str]) -> Any:
    """Drop every list item (and the check's own removed list) that carries a sentence Check D removed."""
    if not removed:
        return obj
    hit = lambda v: any(t in v for t in removed)
    if isinstance(obj, dict):
        return {k: _scrub(v, removed) for k, v in obj.items() if not (k == "removed" and isinstance(v, list))}
    if isinstance(obj, list):
        keep = []
        for v in obj:
            if isinstance(v, str) and hit(v):
                continue
            if isinstance(v, dict) and any(isinstance(x, str) and hit(x) for x in v.values()):
                continue
            keep.append(_scrub(v, removed))
        return keep
    return obj


def _brief_markdown(results: Dict[str, Any]) -> str:
    from src.ui.brief_view import report_markdown, stopped_run_markdown

    if results.get("report"):
        return report_markdown(results["report"], question=results.get("strategic_question", ""),
                               diagram=results.get("diagram"),
                               papers=(results.get("papers") or []) + (results.get("enterprise_docs") or []))
    if results.get("stopped_at"):
        return stopped_run_markdown(results)
    lines = [f"# {results.get('strategic_question') or 'Research brief'}", "", "## Bottom line",
             str(results.get("verdict") or ""), "", "## Findings"]
    lines += [f"- {f.get('text', '')}" for f in results.get("findings") or []]
    return "\n".join(lines) + "\n"


def _claims_csv(results: Dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["source", "source_title", "lane", "claim", "quote", "grade", "url"])
    for c in results.get("claims") or []:
        w.writerow([c.get("source_key"), c.get("source_title"), c.get("lane"), c.get("assertion"), c.get("excerpt"),
                    c.get("grade"), c.get("source_url")])
    return buf.getvalue()


_KINDS = {"brief_md": ("research_brief", "md", "text/markdown"), "claims_csv": ("claims", "csv", "text/csv"),
          "ledger_json": ("evidence_ledger", "json", "application/json"), "post_txt": ("share_post", "txt", "text/plain"),
          "card_svg": ("share_card", "svg", "image/svg+xml")}


def personal_copy(results: Dict[str, Any], kind: str) -> Optional[Tuple[str, str, str]]:
    """(data, file name, mime) for one copy, or None when the run has nothing of that kind (no summary, no post)."""
    from src.output.share_pack import image_card_svg, post_text
    from src.ui.rerun import export_view

    base, ext, mime = _KINDS[kind]
    cleared = is_cleared(results)
    published = str(results.get("status") or "").upper() == "PUBLISHED"
    removed = _removed_texts(results)
    head = [] if cleared else header_lines(results)
    summary = results.get("summary")
    if kind in ("post_txt", "card_svg") and not summary:
        return None
    if kind == "brief_md":
        data = ("".join(f"> {'**' + h + '**' if i == 0 else h}\n" for i, h in enumerate(head)) + "\n" if head else "") \
            + _brief_markdown(results)
    elif kind == "claims_csv":
        data = ("# " + " · ".join(head) + "\n" if head else "") + _claims_csv(results)
    elif kind == "ledger_json":
        view = _scrub(export_view(results), removed)
        data = json.dumps(({"personal_copy": {"draft": True, "note": head}} if head else {}) | view, indent=2, default=str)
    elif kind == "post_txt":
        post = post_text(summary, (results.get("papers") or []) + (results.get("enterprise_docs") or []), published=published)
        data = ("\n".join(head) + "\n\n" if head else "") + post
    else:
        data = image_card_svg(summary, results.get("diagram"), published=published and cleared)
    for t in removed:
        data = data.replace(t, "")
    return data, f"{base}{'' if cleared else '_DRAFT'}.{ext}", mime
