"""Your practitioner experience (S26): captured in Step 2, matched to sub-questions by rule, shown after the run.

DEC-013: practitioner text never goes to a remote model. Everything here is term matching on this machine; the
notes reach the run only as Lane C field notes, which Check A judges by rule and which the report writer never sees.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from src.analysis.relevance import support_terms

_NOTE_PREFIX = re.compile(r"^\s*\[Custom User Observation\]\s*", re.IGNORECASE)


def _terms(text: str) -> set:
    return {t[:-1] if len(t) > 3 and t.endswith("s") else t for t in support_terms(text)}


def match_notes(notes: List[str], sub_questions: List[str]) -> Dict[str, Any]:
    """1-based note numbers per sub-question, plus notes that touch only the common subject ("general") and notes
    that share nothing ("unmatched"). A note goes to the sub-question(s) sharing the most distinguishing terms."""
    q_terms = [_terms(q) for q in sub_questions]
    shared = set.intersection(*q_terms) if q_terms else set()
    out: Dict[str, Any] = {"by_question": [[] for _ in sub_questions], "general": [], "unmatched": []}
    for n, note in enumerate(notes or [], 1):
        nt = _terms(note)
        distinct = [len(nt & (qt - shared)) for qt in q_terms]
        best = max(distinct) if distinct else 0
        if best == 0:
            out["general" if nt & shared else "unmatched"].append(n)
            continue
        totals = [2 * d + len(nt & qt & shared) if d else -1 for d, qt in zip(distinct, q_terms)]
        top = max(totals)
        for i, t in enumerate(totals):
            if t == top:
                out["by_question"][i].append(n)
    return out


def _numbers(ns: List[int]) -> str:
    return ns[0].__str__() if len(ns) == 1 else ", ".join(map(str, ns[:-1])) + f" and {ns[-1]}"


def coverage_lines(notes: List[str], sub_questions: List[str]) -> List[str]:
    if not notes:
        return []
    m = match_notes(notes, sub_questions)
    lines = [f"Q{i}: your note{'s' if len(ns) > 1 else ''} {_numbers(ns)}" if ns else f"Q{i}: nothing from your notes"
             for i, ns in enumerate(m["by_question"], 1)]
    if m["general"]:
        lines.append(f"About the question in general: note{'s' if len(m['general']) > 1 else ''} {_numbers(m['general'])}")
    if m["unmatched"]:
        lines.append(f"Not matched to any sub-question: note{'s' if len(m['unmatched']) > 1 else ''} {_numbers(m['unmatched'])}")
    return lines


def practitioner_inputs(step3_text: str, step3_confirmed: bool, experience: List[str],
                        experience_confirmed: bool) -> Tuple[List[str], bool]:
    """Lane C notes for the run (Step 3 field notes, then Step 2 experience, without duplicates), and whether the
    no-client-names abstraction is confirmed: only when every box that holds notes was confirmed."""
    step3 = [ln.strip() for ln in (step3_text or "").splitlines() if ln.strip()]
    exp = [ln.strip() for ln in experience or [] if str(ln).strip()]
    notes = list(dict.fromkeys(step3 + exp))
    confirmed = bool(notes) and (not step3 or bool(step3_confirmed)) and (not exp or bool(experience_confirmed))
    return notes, confirmed


def observations_by_section(report: Optional[Dict[str, Any]], claims: List[Dict[str, Any]]) -> Dict[int, List[str]]:
    """Field-note claims of this run under the report section they match (by rule), keyed by section index."""
    sections = list((report or {}).get("sections") or [])
    texts = [_NOTE_PREFIX.sub("", str(c.get("assertion") or "")).strip() for c in claims or []
             if str(c.get("lane", "")).upper() == "PRACTITIONER"]
    texts = [t for t in texts if t]
    if not sections or not texts:
        return {}
    m = match_notes(texts, [s.get("sub_question", "") for s in sections])
    out: Dict[int, List[str]] = {}
    for sec, ns in zip(sections, m["by_question"]):
        if ns:
            out[int(sec.get("index") or 0)] = [texts[n - 1] for n in ns]
    return out
