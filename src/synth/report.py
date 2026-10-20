"""The question-shaped report (S19), built by rule from the checked ledger sentences.

The model writes the answer, synthesis and evidence sentences; everything here is derived by rule from
those sentences, their cited claims and the papers: the per-section evidence table, the confidence
badge, and gap lines such as "rests on one paper".
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from src.analysis.relevance import support_terms

_EMPIRICAL = re.compile(
    r"\b(survey|experiment|controlled|trial|randomi[sz]ed|case stud|interview|measured|measurement|evaluation|"
    r"evaluated|benchmark|dataset|mixed[- ]method|quantitative|qualitative|empirical|field stud|observational|"
    r"regression|sample of|respondents|participants)\w*", re.IGNORECASE)
_CONCEPTUAL = re.compile(r"\b(framework|propos|position|vision|conceptual|design|literature review|review of|"
                         r"perspective|essay|theoretical|architecture)\w*", re.IGNORECASE)
_SECTION_TYPES = ("synthesis", "assertive")
_GRADE_ORDER = ("anecdote", "vendor_claim", "weak", "moderate", "strong")


def classify_method(text: Any) -> str:
    """Empirical, conceptual or not stated, from a paper's research-method summary (empirical wins)."""
    t = str(text or "").strip()
    if not t or t.lower() == "not stated":
        return "not stated"
    if _EMPIRICAL.search(t):
        return "empirical"
    if _CONCEPTUAL.search(t):
        return "conceptual"
    return "not stated"


def group_by_sub_question(sentences: List[str], sub_questions: List[str]) -> List[Dict[str, Any]]:
    """Evidence-only sections (no model): each sentence goes to the sub-question it shares most terms with."""
    sections = [{"sub_question": q, "synthesis": [], "evidence": []} for q in sub_questions]
    if not sections:
        return []
    q_terms = [support_terms(q) for q in sub_questions]
    for s in sentences:
        terms = support_terms(s)
        best = max(range(len(sections)), key=lambda i: (len(terms & q_terms[i]), -i))
        sections[best]["evidence"].append(s)
    return sections


def _confidence(paper_ids: List[str], methods: Dict[str, str], tiers: Dict[str, str]) -> Dict[str, Any]:
    n = len(paper_ids)
    empirical = sum(1 for p in paper_ids if methods.get(p) == "empirical")
    conceptual = sum(1 for p in paper_ids if methods.get(p) == "conceptual")
    verified = sum(1 for p in paper_ids if tiers.get(p) == "verified")
    if n >= 3 and empirical >= 2 and verified >= 1:
        level = "high"
    elif n >= 2 and empirical >= 1:
        level = "moderate"
    else:
        level = "low"
    return {"level": level, "papers": n, "empirical": empirical, "conceptual": conceptual, "verified": verified}


def build_report(
    sentences: List[Any],
    papers: List[Dict[str, Any]],
    claims_by_id: Dict[str, Any],
    summaries: List[Dict[str, Any]],
    tier_of: Callable[[Dict[str, Any]], str],
) -> Optional[Dict[str, Any]]:
    """The report dict for the Brief tab and exports, or None when the run has no sections."""
    heads = [s for s in sentences if s.type == "heading" and (s.checks_json or {}).get("section")]
    if not heads:
        return None
    by_source = {p.get("id"): p for p in papers}
    key_of = {p.get("id"): p.get("key") for p in papers}
    method_of_key = {s.get("paper_id"): classify_method(s.get("research_method")) for s in summaries or []}
    methods = {pid: method_of_key.get(key, "not stated") for pid, key in key_of.items()}
    tiers = {pid: tier_of(p) for pid, p in by_source.items()}

    def sources_of(s: Any) -> List[str]:
        out: List[str] = []
        for cid in s.claim_ids_json or []:
            c = claims_by_id.get(cid)
            if c is not None and c.source_id in by_source and c.source_id not in out:
                out.append(c.source_id)
        return out

    def sentence_dict(s: Any) -> Dict[str, Any]:
        return {"type": s.type, "text": s.text, "claim_ids": list(s.claim_ids_json or []),
                "papers": [key_of[sid] for sid in sources_of(s)]}

    sections = []
    for h in heads:
        idx = h.checks_json["section"]
        members = [s for s in sentences if s.type in _SECTION_TYPES and (s.checks_json or {}).get("section") == idx]
        members.sort(key=lambda s: (0 if s.type == "synthesis" else 1, s.ordinal))
        cited = []
        for s in members:
            cited += [sid for sid in sources_of(s) if sid not in cited]
        table = []
        for sid in cited:
            finding = next((s.text for s in members if s.type == "assertive" and sid in sources_of(s)), "")
            grades = [claims_by_id[cid].grade for s in members for cid in (s.claim_ids_json or [])
                      if cid in claims_by_id and claims_by_id[cid].source_id == sid]
            weakest = min(grades, key=lambda g: _GRADE_ORDER.index(g) if g in _GRADE_ORDER else 0) if grades else ""
            table.append({"paper": key_of[sid], "title": by_source[sid].get("title", ""), "method": methods.get(sid, "not stated"),
                          "finding": re.sub(r"\s*\[[^\]]+\]", "", finding).strip(), "grade": weakest,
                          "venue": by_source[sid].get("venue", ""), "type": by_source[sid].get("type", "")})
        sections.append({"index": idx, "sub_question": h.text, "sentences": [sentence_dict(s) for s in members],
                         "table": table, "confidence": _confidence(cited, methods, tiers)})

    summary = next((s for s in sentences if s.type == "summary"), None)
    all_cited = []
    for sec in sections:
        all_cited += [r["paper"] for r in sec["table"] if r["paper"] not in all_cited]
    answer_ids = [pid for pid, key in key_of.items() if key in all_cited]
    gaps = [sentence_dict(s) for s in sentences if s.type == "gap"]
    for sec in sections:
        n = sec["confidence"]["papers"]
        if n == 0:
            gaps.append({"type": "gap", "text": f"Section {sec['index']} has no evidence from the papers found.", "claim_ids": [], "papers": []})
        elif n == 1:
            gaps.append({"type": "gap", "text": f"Section {sec['index']} rests on one paper.", "claim_ids": [], "papers": []})
    return {
        "answer": {"text": summary.text if summary else "", "papers": [key_of[sid] for sid in sources_of(summary)] if summary else [],
                   "confidence": _confidence(answer_ids, methods, tiers)},
        "sections": sections,
        "tensions": [sentence_dict(s) for s in sentences if s.type == "tension"],
        "gaps": gaps,
        "implications": [{**sentence_dict(s), "section": (s.checks_json or {}).get("section")}
                         for s in sentences if s.type == "implication"],
    }
