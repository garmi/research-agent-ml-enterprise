"""Feedback on a reasoned proposal (S15): quick adjustments, and a rule-checked review of what changed.

Feedback becomes numbered points. After re-reasoning, each point is checked by rule against the
proposal before and after: the model's own account of what it did is never taken as proof.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.analysis.relevance import support_terms

# label -> (kind, instruction sent to the model)
QUICK_ADJUSTMENTS: Dict[str, tuple] = {
    "Narrow the scope": ("narrow", "Narrow the scope: make the question more specific and list what is out of scope."),
    "Broaden the scope": ("broaden", "Broaden the scope: widen the question and remove unnecessary limits."),
    "Focus on enterprise practice": ("enterprise", "Focus on how enterprises adopt and run this in practice."),
    "Focus on measured outcomes": ("measured", "Focus on measured outcomes (metrics, benchmarks, controlled studies)."),
    "Make the question more neutral": ("neutral", "Make the question neutral: remove assumptions about the answer."),
    "Fewer sub-questions": ("fewer_sub_questions", "Use fewer sub-questions, keeping the most important ones."),
    "More sub-questions": ("more_sub_questions", "Add sub-questions that cover parts the question leaves out."),
}

_FIELDS = ("refined_question", "sub_questions", "in_scope", "out_of_scope", "premises_to_test")


def compose_feedback(adjustments: List[str], add_sub_question: str = "", drop_terms: str = "",
                     free_text: str = "") -> List[Dict[str, str]]:
    """Numbered feedback points: quick adjustments, an added sub-question, dropped terms, then free text."""
    points: List[Dict[str, str]] = []
    for label in adjustments or []:
        if label in QUICK_ADJUSTMENTS:
            kind, text = QUICK_ADJUSTMENTS[label]
            points.append({"kind": kind, "text": text, "detail": ""})
    topic = (add_sub_question or "").strip()
    if topic:
        points.append({"kind": "add_sub_question", "text": f"Add a sub-question about {topic}.", "detail": topic})
    for term in [t.strip() for t in re.split(r"[,;\n]", drop_terms or "") if t.strip()]:
        points.append({"kind": "drop_term", "text": f"Remove the term '{term}' from the question and sub-questions.", "detail": term})
    for line in [ln.strip() for ln in re.split(r"[\n]+", free_text or "") if ln.strip()]:
        points.append({"kind": "free", "text": line, "detail": ""})
    return points


def feedback_prompt(points: List[Dict[str, str]]) -> str:
    """The text sent to the model: one numbered instruction per point."""
    return "\n".join(f"{i}. {p['text']}" for i, p in enumerate(points, 1))


def _items(pkg: Optional[Dict[str, Any]], field: str) -> List[str]:
    value = (pkg or {}).get(field)
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()] if value else []


def proposal_diff(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "question_before": (before or {}).get("refined_question", ""),
        "question_after": (after or {}).get("refined_question", ""),
    }
    out["question_changed"] = out["question_before"].strip() != out["question_after"].strip()
    for field in ("sub_questions", "in_scope", "out_of_scope"):
        b, a = _items(before, field), _items(after, field)
        out[f"{field}_added"] = [x for x in a if x not in b]
        out[f"{field}_removed"] = [x for x in b if x not in a]
    return out


def _text(pkg: Optional[Dict[str, Any]], fields=("refined_question", "sub_questions", "in_scope")) -> str:
    return " ".join(" ".join(_items(pkg, f)) for f in fields).lower()


def _has_term(text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term.lower())}\b", text) is not None


def review_feedback(points: List[Dict[str, str]], before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]],
                    blocked_reason: Optional[str] = None) -> List[Dict[str, str]]:
    """One row per point: result is Applied, Not applied or Blocked by a rule, with what changed."""
    if after is None or blocked_reason:
        why = f"Re-reasoning was refused: {blocked_reason or 'the new proposal failed its checks'}"
        return [{"point": p["text"], "result": "Blocked by a rule", "what_changed": why} for p in points]

    d = proposal_diff(before, after)
    changed_fields = [f for f in _FIELDS if _items(before, f) != _items(after, f)]
    changed_text = " ".join(
        ([d["question_after"]] if d["question_changed"] else [])
        + d["sub_questions_added"] + d["in_scope_added"] + d["out_of_scope_added"]
    )
    n_before, n_after = len(_items(before, "sub_questions")), len(_items(after, "sub_questions"))

    def row(p: Dict[str, str], applied: bool, what: str) -> Dict[str, str]:
        return {"point": p["text"], "result": "Applied" if applied else "Not applied", "what_changed": what}

    rows = []
    for p in points:
        kind = p["kind"]
        if not changed_fields:
            rows.append(row(p, False, "Nothing in the question, sub-questions or scope changed."))
        elif kind == "drop_term":
            term = p["detail"]
            if _has_term(_text(after), term):
                rows.append(row(p, False, f"'{term}' is still in the question or sub-questions."))
            elif _has_term(_text(before), term):
                rows.append(row(p, True, f"'{term}' was removed."))
            else:
                rows.append(row(p, False, f"'{term}' was not in the proposal to begin with."))
        elif kind == "add_sub_question":
            topic_terms = support_terms(p["detail"])
            hit = next((q for q in d["sub_questions_added"] if topic_terms & support_terms(q)), None)
            rows.append(row(p, bool(hit), f"Added: \"{hit}\"" if hit else "No new sub-question is about that topic."))
        elif kind == "fewer_sub_questions":
            rows.append(row(p, n_after < n_before, f"Sub-questions: {n_before} → {n_after}."))
        elif kind == "more_sub_questions":
            rows.append(row(p, n_after > n_before, f"Sub-questions: {n_before} → {n_after}."))
        elif kind == "narrow":
            narrowed = bool(d["out_of_scope_added"] or d["in_scope_removed"] or d["question_changed"])
            what = (f"Added to out of scope: {', '.join(d['out_of_scope_added'])}." if d["out_of_scope_added"]
                    else "The question was reworded." if d["question_changed"] else "Scope did not narrow.")
            rows.append(row(p, narrowed, what))
        elif kind == "broaden":
            broadened = bool(d["in_scope_added"] or d["out_of_scope_removed"] or d["question_changed"])
            what = (f"Added to in scope: {', '.join(d['in_scope_added'])}." if d["in_scope_added"]
                    else "The question was reworded." if d["question_changed"] else "Scope did not widen.")
            rows.append(row(p, broadened, what))
        else:
            # Free text and focus/neutral adjustments: applied when the changed text picks up the point's terms.
            terms = support_terms(p["detail"] or p["text"]) - {"focus", "question", "make", "scope"}
            overlap = sorted(terms & support_terms(changed_text))
            if overlap:
                rows.append(row(p, True, f"Changed text now mentions: {', '.join(overlap)}."))
            else:
                rows.append(row(p, False, f"Changed: {', '.join(f.replace('_', ' ') for f in changed_fields)}, "
                                          "but nothing that matches this point. Check the before and after."))
    return rows
