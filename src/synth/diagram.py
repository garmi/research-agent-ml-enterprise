"""The report diagram (S20): a small spec the model proposes, kept or dropped by rule.

The model returns one spec from the checked report sentences. Nothing here asks it again: a spec out of bounds
is dropped whole, a node whose cites do not resolve to a claim in this run is dropped with its edges, and what
is left must still be a diagram (two or more nodes; an architecture drawing on two or more papers).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

DIAGRAM_TYPES = ("pathway", "architecture", "comparison", "cause_effect")
MAX_NODES = 6
MAX_LABEL = 40
MAX_EDGE_LABEL = 30
MAX_TITLE = 80


def _cites(raw: Any) -> List[str]:
    """[P#] keys named by a node, in order, from a list or a string ("P1", "[P2][P3]", "P1, P4")."""
    text = " ".join(str(x) for x in raw) if isinstance(raw, (list, tuple)) else str(raw or "")
    out: List[str] = []
    for kind, n in re.findall(r"([PE])(\d+)", text):
        key = f"{kind}{int(n)}"
        if key not in out:
            out.append(key)
    return out


def validate_diagram(raw: Any, papers: List[Dict[str, Any]], claims_by_id: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The diagram to draw, or None. `papers` are the run's papers in [P#] order (each with its source `id`)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    if not isinstance(raw, dict):
        return None
    dtype = re.sub(r"[\s-]+", "_", str(raw.get("type") or "").strip().lower())
    if dtype not in DIAGRAM_TYPES:
        return None
    nodes_raw = [n for n in raw.get("nodes") or [] if isinstance(n, dict)]
    if not nodes_raw or len(nodes_raw) > MAX_NODES:
        return None
    if any(len(str(n.get("label") or "").strip()) > MAX_LABEL for n in nodes_raw):
        return None

    # A cite counts only when its paper has a claim in this run.
    with_claims = {c.source_id for c in claims_by_id.values()}
    key_ok = {p.get("key") or f"P{i}" for i, p in enumerate(papers or [], 1) if p.get("id") in with_claims}
    nodes: List[Dict[str, Any]] = []
    for i, n in enumerate(nodes_raw):
        label = str(n.get("label") or "").strip()
        cites = [k for k in _cites(n.get("cites")) if k in key_ok]
        nid = str(n.get("id") or f"n{i + 1}").strip()
        if label and cites and nid not in {m["id"] for m in nodes}:
            nodes.append({"id": nid, "label": label, "cites": cites})
    if len(nodes) < 2:
        return None
    if dtype == "architecture" and len({k for n in nodes for k in n["cites"]}) < 2:
        return None

    kept = {n["id"] for n in nodes}
    edges: List[Dict[str, str]] = []
    for e in raw.get("edges") or []:
        if not isinstance(e, dict):
            continue
        a, b = str(e.get("from") or "").strip(), str(e.get("to") or "").strip()
        if a in kept and b in kept and a != b:
            label = str(e.get("label") or "").strip()
            edges.append({"from": a, "to": b, "label": label if len(label) <= MAX_EDGE_LABEL else ""})
    title = str(raw.get("title") or "").strip()[:MAX_TITLE] or "How the evidence fits together"
    return {"type": dtype, "title": title, "nodes": nodes, "edges": edges}


def diagram_outline(spec: Optional[Dict[str, Any]]) -> List[str]:
    """The diagram as text lines (for exports): each edge as 'a [P#] → b [P#]', then any node left unjoined."""
    if not spec:
        return []
    by_id = {n["id"]: n for n in spec["nodes"]}
    tag = lambda n: f"{n['label']} " + "".join(f"[{k}]" for k in n["cites"])
    lines = [f"{tag(by_id[e['from']])} → {tag(by_id[e['to']])}" + (f" ({e['label']})" if e.get("label") else "")
             for e in spec["edges"]]
    joined = {x for e in spec["edges"] for x in (e["from"], e["to"])}
    lines += [tag(n) for n in spec["nodes"] if n["id"] not in joined]
    return lines
