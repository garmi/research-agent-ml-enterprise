"""Per-paper evidence limits for the writer (S27): the verbs and figures each paper's claims allow.

G4 caps a sentence's verb at the rank its weakest cited claim allows, and G2 fails a figure the cited claims do
not hold. Telling the writer those limits up front, per paper, keeps the gates strict while the draft passes them.
"""

from __future__ import annotations

from typing import Any, Dict, List

import re

_FIGURE = re.compile(r"(?<![\w.])\$?\d+(?:\.\d+)?(?:%|x|×|k|m|b)?(?![\w.])", re.IGNORECASE)

_GRADE_ORDER = ("anecdote", "vendor_claim", "weak", "moderate", "strong")
_PREFERRED = ["shows", "finds", "suggests", "indicates", "observes", "reports", "describes", "proposes", "argues",
              "states", "according to", "claims", "notes", "in one case"]


def paper_evidence_limits(papers: List[Dict[str, Any]], claims: List[Any], checker: Any) -> Dict[str, Dict[str, List[str]]]:
    """{"P#": {"allowed_verbs": [...], "figures": [...]}} for each paper (in [P#] order) that has claims."""
    by_source: Dict[str, List[Any]] = {}
    for c in claims or []:
        if getattr(c, "status", "") != "rejected":
            by_source.setdefault(c.source_id, []).append(c)
    out: Dict[str, Dict[str, List[str]]] = {}
    for i, p in enumerate(papers or [], 1):
        cs = by_source.get(p.get("id"))
        if not cs:
            continue
        weakest = min((c.grade for c in cs), key=lambda g: _GRADE_ORDER.index(g) if g in _GRADE_ORDER else 0)
        cap = checker.get_max_allowed_rank(weakest)
        verbs: List[str] = []
        rank_of: Dict[str, int] = {}
        for info in sorted(checker.verbs_cfg.values(), key=lambda v: -v.get("rank", 0)):
            if info.get("rank", 0) <= cap:
                for v in info.get("verbs", []):
                    if v not in verbs:
                        verbs.append(v)
                        rank_of[v] = info.get("rank", 0)
        figures: List[str] = []
        for c in cs:
            for n in _FIGURE.findall(f"{c.text} {c.source_excerpt or ''}"):
                n = n.lower()
                if not re.fullmatch(r"(19|20)\d{2}", n) and n not in figures:
                    figures.append(n)
        # S22c: at most six verbs, the most useful first (strongest allowed rank, then plain reporting verbs).
        verbs.sort(key=lambda v: (-rank_of[v], _PREFERRED.index(v) if v in _PREFERRED else len(_PREFERRED)))
        out[p.get("key") or f"P{i}"] = {"allowed_verbs": verbs[:6], "figures": figures[:12]}
    return out


def limits_lines(limits: Dict[str, Dict[str, List[str]]]) -> List[str]:
    """The limits as short prompt lines, one per paper."""
    return [f"{k}: Allowed verbs: {', '.join(v['allowed_verbs'][:8])}. Figures: {', '.join(v['figures']) or 'none'}."
            for k, v in limits.items()]
