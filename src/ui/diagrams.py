"""SVG for a validated report diagram (S20), drawn without any new dependency.

Layered layout: with edges, each node sits in the column of its longest path from a starting node, so a chain
runs left to right; without edges, nodes sit in a grid of three. The SVG has no blank lines, so it fits one
Markdown HTML block, and every label is escaped.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional, Tuple

NODE_W, NODE_H, GAP_X, GAP_Y, MARGIN = 200, 82, 64, 24, 16
_FILL, _STROKE, _TEXT, _MUTED, _EDGE = "#EFF6FF", "#2563EB", "#0F172A", "#475569", "#64748B"


def _wrap(label: str, width: int = 22) -> List[str]:
    """At most two lines of about `width` characters (labels are at most 40)."""
    words, lines, cur = label.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    return lines[:2] if len(lines) <= 2 else [lines[0], " ".join(lines[1:])]


def _layers(spec: Dict[str, Any]) -> Dict[str, List[int]]:
    """Column and row for each node id."""
    ids = [n["id"] for n in spec["nodes"]]
    if not spec["edges"]:
        return {nid: [i % 3, i // 3] for i, nid in enumerate(ids)}
    depth = {nid: 0 for nid in ids}
    for _ in range(len(ids)):  # longest path; bounded, so a cycle cannot loop forever
        for e in spec["edges"]:
            depth[e["to"]] = max(depth[e["to"]], min(depth[e["from"]] + 1, len(ids) - 1))
    rows: Dict[int, int] = {}
    pos = {}
    for nid in ids:
        col = depth[nid]
        pos[nid] = [col, rows.get(col, 0)]
        rows[col] = rows.get(col, 0) + 1
    return pos


def diagram_svg(spec: Optional[Dict[str, Any]], marker_id: str = "dg-arrow",
                frame: Optional[Tuple[int, int, int, int]] = None, labels: Optional[Dict[str, str]] = None) -> str:
    """The diagram as an SVG; `frame` (x, y, width, height) places it inside another SVG, such as the share card.
    `labels` (S29b) maps a P#/E# key to the source name shown under each box."""
    if not spec or not spec.get("nodes"):
        return ""
    esc = lambda v: html.escape(str(v or ""), quote=True)
    pos = _layers(spec)
    cols = max(c for c, _ in pos.values()) + 1
    rows = max(r for _, r in pos.values()) + 1
    width = MARGIN * 2 + cols * NODE_W + (cols - 1) * GAP_X
    height = MARGIN * 2 + rows * NODE_H + (rows - 1) * GAP_Y
    xy = {nid: (MARGIN + c * (NODE_W + GAP_X), MARGIN + r * (NODE_H + GAP_Y)) for nid, (c, r) in pos.items()}

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        + (f'x="{frame[0]}" y="{frame[1]}" width="{frame[2]}" height="{frame[3]}" ' if frame else
           f'width="100%" style="max-width:{width}px;display:block;margin:0.4rem 0;" ')
        + f'role="img" aria-label="{esc(spec.get("title"))}">',
        f'<defs><marker id="{esc(marker_id)}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{_EDGE}"/></marker></defs>',
    ]
    for e in spec["edges"]:
        (ax, ay), (bx, by) = xy[e["from"]], xy[e["to"]]
        x1, y1 = ax + NODE_W, ay + NODE_H / 2
        x2, y2 = bx, by + NODE_H / 2
        if bx <= ax:  # same or earlier column: leave from the bottom, enter from the top
            x1, y1, x2, y2 = ax + NODE_W / 2, ay + NODE_H, bx + NODE_W / 2, by
        mx = (x1 + x2) / 2
        parts.append(f'<path d="M{x1:.0f},{y1:.0f} C{mx:.0f},{y1:.0f} {mx:.0f},{y2:.0f} {x2 - 2:.0f},{y2:.0f}" '
                     f'fill="none" stroke="{_EDGE}" stroke-width="1.6" marker-end="url(#{esc(marker_id)})"/>')
        if e.get("label"):
            parts.append(f'<text x="{mx:.0f}" y="{(y1 + y2) / 2 - 6:.0f}" text-anchor="middle" font-size="11" '
                         f'fill="{_MUTED}">{esc(e["label"])}</text>')
    for n in spec["nodes"]:
        x, y = xy[n["id"]]
        parts.append(f'<rect class="dg-node" x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" rx="10" '
                     f'fill="{_FILL}" stroke="{_STROKE}" stroke-width="1.4"/>')
        lines = _wrap(n["label"])
        top = y + (30 if len(lines) == 2 else 38)
        for i, line in enumerate(lines):
            parts.append(f'<text x="{x + NODE_W / 2:.0f}" y="{top + i * 17}" text-anchor="middle" font-size="14" '
                         f'font-weight="600" fill="{_TEXT}">{esc(line)}</text>')
        parts.append(f'<text x="{x + NODE_W / 2:.0f}" y="{y + NODE_H - 10}" text-anchor="middle" font-size="11" '
                     f'fill="{_MUTED}">{esc(" · ".join((labels or {}).get(c, c) for c in n["cites"]))}</text>')
    parts.append("</svg>")
    return "".join(parts)
