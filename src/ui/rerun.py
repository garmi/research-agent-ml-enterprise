"""Helpers for re-running a research run from its results (evidence board, Feedback Loop 1)."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

# Kept in the results for re-runs only; never exported (full harvested records, not <=25-word excerpts).
INTERNAL_KEYS = ("harvested_papers",)


def board_editor_key(results: Dict[str, Any]) -> str:
    """Evidence-board editor key, unique per run: a keyed data_editor keeps its row edits by index,
    so a shared key would apply one run's edits to another run's rows."""
    return f"evidence_board_editor_{results.get('run_id') or 'none'}"


def export_view(results: Dict[str, Any]) -> Dict[str, Any]:
    """The results without internal re-run data, for downloads."""
    return {k: v for k, v in results.items() if k not in INTERNAL_KEYS}


def papers_for_rerun(
    results: Dict[str, Any],
    drop_keys: Optional[Iterable[str]] = None,
    drop_custom: bool = True,
) -> List[Dict[str, Any]]:
    """The harvested records behind the run's papers, in display order, minus the papers whose
    keys (P1, P2, ...) are in `drop_keys`. Custom-URL papers are dropped by default because a
    re-draft fetches them again from the lane URLs."""
    dropped = set(drop_keys or [])
    by_id = {str(p.get("id")): p for p in results.get("harvested_papers") or [] if p.get("id")}
    out: List[Dict[str, Any]] = []
    for p in results.get("papers") or []:
        if p.get("key") in dropped or (drop_custom and p.get("is_custom")):
            continue
        out.append(by_id.get(str(p.get("id")), p))
    return out
