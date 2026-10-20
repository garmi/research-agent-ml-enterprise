"""The thought-leadership summary (S21): an executive, first-person post drafted by the model, kept by rule.

The model writes from the checked report; these rules decide what survives:
- each takeaway passes the same gates as a synthesis sentence (cite; two or more sources or single-source
  wording; no figure its claims lack), is at most two sentences, and invents no experience;
- "I reviewed N studies" is written by rule with the real N, so the model never states a count;
- a long or invented hook is replaced, other invented lines are dropped;
- exactly one closing question and 3-5 hashtags;
- when most cited papers are not empirical, the nuance says so.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from src.ledger.models import OutputSentence
from src.synth.generator import resolve_citations

MAX_TAKEAWAYS = 7
MAX_HOOK_WORDS = 20
MAX_TAKEAWAY_SENTENCES = 2
MAX_QUESTION_WORDS = 15

# First-person claims of experience the system cannot have had: the post may say "I reviewed", never "we built".
_INVENTED = re.compile(
    r"\b(in my (team|company|organi[sz]ation|experience|role|work)|at my (company|firm|organi[sz]ation|work)|"
    r"my (team|company|organi[sz]ation|engineers|clients)|our (team|company|organi[sz]ation|engineers|clients|rollout|pilot)|"
    r"we (found|built|saw|see|implemented|deployed|rolled|tried|learned|learnt|ran|tested|measured|shipped|launched|adopted|did)|"
    r"i (built|implemented|deployed|led|ran|managed|saw|tested|launched|shipped|rolled|worked|advised|coached|consulted)|"
    r"i (talk|talked|speak|spoke|meet|met|work|advise|coach) (to|with|for)|i've (seen|built|led|worked|watched))\b",
    re.IGNORECASE,
)
_COUNT_CLAIM = re.compile(r"\bI\s+(reviewed|read|analy[sz]ed|looked at|went through|studied)\s+(\d+|[a-z]+-?[a-z]*)\s+"
                          r"(studies|papers|articles|reports|sources)\b", re.IGNORECASE)
_NUMBER_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
_STATED_COUNT = re.compile(r"\b(\d+|" + "|".join(_NUMBER_WORDS) + r")\s+(?:[a-z-]+\s+){0,2}(studies|papers|reports|sources)\b",
                           re.IGNORECASE)
_TAG = re.compile(r"\s*\[(?:P\d+(?:[,;\s]+P\d+)*)\]")
_EMPIRICAL_WORDS = re.compile(r"conceptual|framework|propos|self-report|not state|early|limited|few", re.IGNORECASE)
_SENTENCES = re.compile(r"(?<=[.!?])\s+")


def invents_experience(text: Any) -> bool:
    return bool(_INVENTED.search(str(text or "")))


def strip_tags(text: Any) -> str:
    return re.sub(r"\s+([.,;:!?])", r"\1", _TAG.sub("", str(text or ""))).strip()


def _as_list(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(v).strip() for v in value or [] if str(v).strip()]


def evidence_profile(report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Papers the report cites and their methods, from its section tables."""
    method: Dict[str, str] = {}
    for sec in (report or {}).get("sections") or []:
        for row in sec.get("table") or []:
            if row.get("paper"):
                method.setdefault(row["paper"], row.get("method") or "not stated")
    vals = list(method.values())
    return {"papers": len(vals), "empirical": vals.count("empirical"), "conceptual": vals.count("conceptual"),
            "not_stated": len(vals) - vals.count("empirical") - vals.count("conceptual"), "methods": method}


def _basis(keys: List[str], methods: Dict[str, str]) -> str:
    n = len(keys)
    counts = {m: sum(1 for k in keys if methods.get(k, "not stated") == m) for m in ("empirical", "conceptual", "not stated")}
    head = f"{n} paper{'' if n == 1 else 's'}"
    if counts["not stated"] == n:
        return f"{head} · method not stated"
    return f"{head} · " + ", ".join(f"{c} {m}" for m, c in counts.items() if c)


def _check_takeaway(text: str, papers: List[Dict[str, Any]], claims_by_id: Dict[str, Any], checker: Any) -> Optional[str]:
    """None when the takeaway may be kept, else the reason it is dropped."""
    if invents_experience(text):
        return "invents experience"
    if len([s for s in _SENTENCES.split(text.strip()) if s]) > MAX_TAKEAWAY_SENTENCES:
        return "longer than two sentences"
    cids = resolve_citations(text, papers, list(claims_by_id.values()), claims_by_id)
    if not cids:
        return "cites no claim in this run"
    res = checker.check_output([OutputSentence(id="tk", output_id="summary", ordinal=0, text=text, type="synthesis",
                                               claim_ids_json=cids)], claims_by_id, papers=papers)
    if not res.g1_pass:
        return "cites no valid claim"
    if not res.g2_pass:
        return "adds a figure its sources do not hold"
    if not res.g4_pass:
        joined = " ".join(res.violations.get("G4") or [])
        return "cites one source without saying so" if "one source" in joined else "overstates its evidence"
    return None


def _hashtags(raw: Any, subject: List[str]) -> List[str]:
    """The model's tags as #CamelCase, at most 5; filled to 3 from the question's subject terms when short."""
    out: List[str] = []

    def add(tag: str) -> None:
        word = "".join(w[:1].upper() + w[1:] for w in re.findall(r"[A-Za-z0-9]+", tag))
        if word and f"#{word}".lower() not in {o.lower() for o in out}:
            out.append(f"#{word}")

    for tag in _as_list(raw):
        add(tag)
    for term in subject or []:
        if len(out) >= 3:
            break
        add(term)
    return out[:5]


def _closing_question(raw: Any) -> str:
    qs = [s.strip() for s in _SENTENCES.split(strip_tags(raw)) if s.strip().endswith("?")]
    q = qs[-1] if qs else ""
    return q if q and not invents_experience(q) else "What are you seeing where you work?"


def build_summary(raw: Any, report: Optional[Dict[str, Any]], papers: List[Dict[str, Any]], claims_by_id: Dict[str, Any],
                  checker: Any, n_reviewed: int, subject: Optional[List[str]] = None,
                  question: str = "") -> Optional[Dict[str, Any]]:
    """The kept summary, or None when the reply is unusable or no takeaway passes."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    if not isinstance(raw, dict):
        return None
    profile = evidence_profile(report)
    key_of = {f"P{i}": p for i, p in enumerate(papers or [], 1)}
    dropped: List[str] = []
    takeaways: List[Dict[str, Any]] = []
    for text in _as_list(raw.get("takeaways")):
        why = _check_takeaway(text, papers, claims_by_id, checker)
        if why:
            dropped.append(f"Takeaway dropped ({why}): {strip_tags(text)}")
            continue
        keys = [k for k in dict.fromkeys(re.findall(r"P\d+", " ".join(re.findall(r"\[[^\]]+\]", text)))) if k in key_of]
        takeaways.append({"text": text, "papers": keys, "basis": _basis(keys, profile["methods"])})
        if len(takeaways) == MAX_TAKEAWAYS:
            break
    if not takeaways:
        return None

    true_counts = {n_reviewed, profile["papers"], profile["empirical"], profile["conceptual"], profile["not_stated"]}

    def counts_ok(sentence: str) -> bool:
        for m in _STATED_COUNT.finditer(sentence):
            n = m.group(1).lower()
            if (int(n) if n.isdigit() else _NUMBER_WORDS[n]) not in true_counts:
                return False
        return True

    def line(field: str) -> str:
        text = strip_tags(raw.get(field))
        if invents_experience(text):
            dropped.append(f"{field} dropped (invents experience)")
            return ""
        kept = [s for s in _SENTENCES.split(text) if s.strip()]
        ok = [s for s in kept if counts_ok(s)]
        if len(ok) < len(kept):
            dropped.append(f"{field}: a sentence stating a study count the evidence does not match was dropped")
        return " ".join(ok)

    hook = strip_tags(raw.get("hook"))
    if not hook or len(hook.split()) > MAX_HOOK_WORDS or invents_experience(hook):
        dropped.append("hook replaced (over 20 words or invents experience)" if hook else "hook missing")
        hook = "I went through the research on one question. Here is what holds up."
    rest = [s for s in _SENTENCES.split(strip_tags(raw.get("opening"))) if s.strip()
            and not _COUNT_CLAIM.search(s) and not invents_experience(s) and counts_ok(s)]
    short_q = question.strip() if question and len(question.split()) <= MAX_QUESTION_WORDS else ""
    lead = f"I reviewed {n_reviewed} studies to answer one question" + (f": {short_q}" if short_q else ".")
    opening = " ".join([lead] + rest)
    nuance = line("nuance")
    if profile["papers"] and profile["empirical"] * 2 < profile["papers"] and not _EMPIRICAL_WORDS.search(nuance):
        nuance = (nuance + " " if nuance else "") + (
            f"Only {profile['empirical']} of the {profile['papers']} papers cited measured an outcome; the rest are "
            "conceptual or do not state a method, so read this as direction rather than proof.")
    return {
        "hook": hook,
        "opening": opening,
        "takeaways": takeaways,
        "for_leaders": line("for_leaders"),
        "nuance": nuance,
        "watch_next": line("watch_next"),
        "question": _closing_question(raw.get("question")),
        "hashtags": _hashtags(raw.get("hashtags"), subject or []),
        "n_reviewed": n_reviewed,
        "profile": {k: v for k, v in profile.items() if k != "methods"},
        "dropped": dropped,
    }
