"""Claims & gaps in plain words (S24).

The ledger keeps every claim with its grade, rules and excerpt; that stays available as the full claim ledger.
This view is what a reader needs first: how much evidence each lane has and what that means, what the evidence
does not cover, and the claims grouped under the sub-question they answer, each with a plain grade label.
Everything is derived by rule from the run's payload; nothing here is written by the model.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Tuple

from src.extract.claim_extractor import strip_claim_prefix

_GRADES: Dict[str, Tuple[str, str, str, str]] = {
    # grade: (label, meaning, chip background, chip text)
    "strong": ("Strong", "A rigorous study with measured results, or several studies agreeing.", "#DCFCE7", "#166534"),
    "moderate": ("Moderate", "A sound study with some limits (size, setting or method).", "#DBEAFE", "#1E40AF"),
    "weak": ("Weak", "Early, small, self-reported or abstract-only evidence.", "#FEF3C7", "#92400E"),
    "vendor_claim": ("Vendor says", "A company describing its own product or customers; not independent.", "#F3E8FF", "#6B21A8"),
    "anecdote": ("Anecdote", "One person's or one team's account.", "#F1F5F9", "#334155"),
}
_MIX_NAMES = {"strong": "strong", "moderate": "moderate", "weak": "weak", "vendor_claim": "vendor claim", "anecdote": "anecdote"}

_LANE_MEANING = {
    "academic": {"supported": "Enough research to answer the question.",
                 "partial": "Some research, but thin or mostly weak.",
                 "contradicted": "Studies disagree with each other.",
                 "none found": "No relevant research papers were found."},
    "enterprise": {"supported": "Companies describe doing this in practice.",
                   "partial": "One or two practice reports, mostly weak.",
                   "contradicted": "Practice reports disagree with each other.",
                   "none found": "Searched, but no on-topic practice reports were found.",
                   "not searched": "Enterprise practice sources were not searched."},
    "practitioner": {"supported": "Your field notes back this.",
                     "partial": "One field note touches on this.",
                     "contradicted": "Your field notes disagree with each other.",
                     "none found": "No field notes from your own practice were added."},
}
_MISSING = {
    ("academic", "none found"): "No relevant research papers were found.",
    ("enterprise", "none found"): "No on-topic enterprise practice reports were found.",
    ("enterprise", "not searched"): "Enterprise practice sources were not searched.",
    ("practitioner", "none found"): "No field notes from your own practice were added.",
}
_OUTCOMES = {
    "1": ("Research and practice agree", "Studies and company reports point the same way."),
    "2": ("Practice ahead of research", "Companies are doing this, but independent studies are missing or only vendors report it."),
    "3": ("Research ahead of practice", "Studies show what is possible, but no company reports measuring it in practice."),
    "4": ("Thin evidence everywhere", "Neither research nor practice offers solid evidence yet."),
    "na": ("Practice not checked", "Research was reviewed, but enterprise practice sources were not searched."),
}
_RULE_GAP = re.compile(r"^Section \d+ (has no evidence|rests on one paper)")
_TAGS = re.compile(r"\s*\[(?:P\d+(?:[,;\s]+P\d+)*)\]")


def grade_label(grade: Any) -> Tuple[str, str]:
    """(label, one-line meaning) for an evidence grade."""
    g = _GRADES.get(str(grade or "").strip().lower())
    return (g[0], g[1]) if g else ("Not graded", "This claim has no grade.")


def outcome_plain(outcome: Any) -> Tuple[str, str]:
    key = str(outcome or "").strip().lower()
    return _OUTCOMES.get(key) or (_OUTCOMES["na"] if "practice" in key else _OUTCOMES["4"])


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def lane_summary(results: Dict[str, Any]) -> List[Dict[str, str]]:
    gm = results.get("gap_matrix") or {}
    lb = results.get("lane_breakdown") or {}
    rows = [
        ("Research papers", "academic", lb.get("academic_claims_count", 0), lb.get("academic_sources_count", 0), "paper"),
        ("Enterprise practice", "enterprise", lb.get("enterprise_claims_count", 0), lb.get("enterprise_sources_count", 0), "source"),
        ("Your field notes", "practitioner", lb.get("practitioner_claims_count", 0), lb.get("practitioner_observations_count", 0), "note"),
    ]
    state_key = {"academic": "academic_state", "enterprise": "enterprise_state", "practitioner": "field_state"}
    out = []
    for name, lane, n_claims, n_sources, unit in rows:
        state = str(gm.get(state_key[lane]) or "none found").strip().lower()
        meaning = _LANE_MEANING[lane].get(state) or "Not assessed for this run."
        count = f"{_plural(int(n_claims or 0), 'claim')} from {_plural(int(n_sources or 0), unit)}" if n_claims else "No claims"
        out.append({"name": name, "lane": lane, "count": count, "meaning": meaning})
    return out


def _plain_claim(c: Dict[str, Any]) -> Dict[str, Any]:
    text = strip_claim_prefix(str(c.get("assertion") or "")).strip()
    text = text[:1].upper() + text[1:]
    label, meaning = grade_label(c.get("grade"))
    source = " · ".join(str(x) for x in (c.get("source_title"), c.get("venue"), c.get("year")) if x and str(x) != "Date unknown")
    key = str(c.get("source_key") or "")
    return {"id": c.get("id"), "text": text, "grade": label, "meaning": meaning,
            "grade_key": str(c.get("grade") or "").lower(), "source": source,
            "key": key if re.fullmatch(r"P\d+", key) else "", "excerpt": c.get("excerpt") or "", "url": c.get("source_url") or ""}


def _mix(claims: List[Dict[str, Any]]) -> str:
    counts = {g: sum(1 for c in claims if c["grade_key"] == g) for g in _MIX_NAMES}
    return " · ".join(f"{n} {_MIX_NAMES[g]}" for g, n in counts.items() if n)


def claims_by_question(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Claims under the sub-question whose section cites them (first section wins), then the claims no section uses."""
    by_id = {c.get("id"): c for c in results.get("claims") or []}
    used: set = set()
    groups = []
    for sec in (results.get("report") or {}).get("sections") or []:
        ids = [cid for s in sec.get("sentences") or [] for cid in s.get("claim_ids") or []]
        ids = [cid for cid in dict.fromkeys(ids) if cid in by_id and cid not in used]
        if not ids:
            continue
        used.update(ids)
        claims = [_plain_claim(by_id[cid]) for cid in ids]
        groups.append({"title": f"{sec.get('index')}. {sec.get('sub_question')}", "claims": claims, "mix": _mix(claims)})
    rest = [_plain_claim(c) for cid, c in by_id.items() if cid not in used]
    if rest:
        title = "Found but not used in the brief" if groups else "All claims"
        groups.append({"title": title, "claims": rest, "mix": _mix(rest)})
    return groups


def missing_plain(results: Dict[str, Any]) -> List[str]:
    """What the evidence does not cover, in plain words."""
    report = results.get("report") or {}
    lines: List[str] = []
    for g in report.get("gaps") or []:
        text = _TAGS.sub("", str(g.get("text") or "")).strip()
        text = re.sub(r"\s+([.,;:])", r"\1", text)
        if text and not _RULE_GAP.match(text):
            lines.append(text)
    for sec in report.get("sections") or []:
        n = len({row.get("paper") for row in sec.get("table") or []})
        if n == 0:
            lines.append(f"“{sec.get('sub_question')}” has no evidence from the papers found.")
        elif n == 1:
            lines.append(f"“{sec.get('sub_question')}” rests on a single paper.")
    gm = results.get("gap_matrix") or {}
    for lane, key in (("academic", "academic_state"), ("enterprise", "enterprise_state"), ("practitioner", "field_state")):
        line = _MISSING.get((lane, str(gm.get(key) or "").strip().lower()))
        if line:
            lines.append(line)
    return list(dict.fromkeys(lines))


def claims_overview_html(results: Dict[str, Any]) -> str:
    esc = lambda v: html.escape(str(v or ""))
    lanes = "".join(
        f'<div class="cg-lane"><div class="cg-lane-name">{esc(l["name"])}</div>'
        f'<div class="cg-lane-count">{esc(l["count"])}</div><div class="cg-lane-meaning">{esc(l["meaning"])}</div></div>'
        for l in lane_summary(results))
    title, meaning = outcome_plain((results.get("gap_matrix") or {}).get("outcome"))
    missing = "".join(f"<li>{esc(m)}</li>" for m in missing_plain(results)) or "<li>Nothing flagged.</li>"
    groups = []
    for g in claims_by_question(results):
        items = []
        for c in g["claims"]:
            _, meaning_c, bg, fg = _GRADES.get(c["grade_key"], ("", "", "#F1F5F9", "#334155"))
            chip = (f'<span class="cg-chip" title="{esc(c["meaning"])}" style="background:{bg};color:{fg};">'
                    f'{esc(c["grade"])}</span>')
            key = f'<b>{esc(c["key"])}</b> · ' if c["key"] else ""
            quote = f'<div class="cg-quote">“{esc(c["excerpt"])}”</div>' if c["excerpt"] else ""
            items.append(f'<div class="cg-claim">{chip} {esc(c["text"])}<div class="cg-src">{key}{esc(c["source"])}</div>{quote}</div>')
        n = len(g["claims"])
        groups.append(f'<details class="cg-group"{" open" if not groups else ""}><summary><b>{esc(g["title"])}</b> '
                      f'<span class="cg-mix">{_plural(n, "claim")} · {esc(g["mix"])}</span></summary>{"".join(items)}</details>')
    legend = " ".join(f'<span class="cg-chip" style="background:{bg};color:{fg};">{esc(label)}</span> {esc(m)}'
                      for label, m, bg, fg in _GRADES.values())
    return (
        '<div class="cg-overview">'
        f'<h4>At a glance</h4><div class="cg-lanes">{lanes}</div>'
        f'<div class="cg-outcome"><b>{esc(title)}.</b> {esc(meaning)}</div>'
        f"<h4>What's missing</h4><ul class=\"cg-missing\">{missing}</ul>"
        f'<h4>Claims by question</h4>{"".join(groups) or "<p>No claims recorded for this run.</p>"}'
        f'<div class="cg-legend">{legend}</div></div>'
    )
