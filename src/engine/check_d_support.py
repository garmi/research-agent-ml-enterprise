"""Check D: does each sentence say only what the quotes it cites say? (S28)

The gates check structure (a citation exists, figures appear, verbs fit the grade); Check D checks meaning. Each
grounded sentence goes to the model with only the quotes it cites, and comes back supported, partial or
unsupported with a reason. Without a model, a rule verdict is used: every figure is present and the sentence shares
two or more terms with a quote, else "unchecked". Practitioner quotes never leave this machine (DEC-013).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.analysis.relevance import support_terms
from src.extract.claim_extractor import strip_claim_prefix
from src.score.checker import GROUNDED_TYPES, claim_has_numeral, extract_numerals

logger = logging.getLogger(__name__)

BATCH_SIZE = 8
MAX_QUOTES = 6
VERDICTS = ("supported", "partial", "unsupported")

PROMPT = """You are Check D, a strict fact-checker. For each sentence below, read only the quotes listed under it
(taken from the sources the sentence cites) and decide whether they support the sentence.
- "supported": everything the sentence claims, including any figure, is stated in or directly implied by the quotes.
- "partial": the quotes support part of the sentence, but it adds, generalises or overstates something.
- "unsupported": the quotes do not support the sentence's main claim, or a figure in it is not in the quotes.
Judge only against the quotes; do not use your own knowledge. Wording such as "one study reports" or
"according to one vendor" is attribution, not a claim.

Return valid JSON only: {{"verdicts": [{{"id": "S1", "verdict": "supported|partial|unsupported", "reason": "one short sentence"}}]}}

{items}
"""


def _quote(claim: Any) -> str:
    return re.sub(r"\s+", " ", strip_claim_prefix(str(claim.text or "")) or str(claim.source_excerpt or "")).strip()


def _rule_verdict(text: str, quotes: List[Any]) -> str:
    nums = extract_numerals(text)
    if nums and not all(any(claim_has_numeral(c, n) for c in quotes) for n in nums):
        return "unchecked"
    s_terms = support_terms(text)
    return "supported" if any(len(s_terms & support_terms(_quote(c))) >= 2 for c in quotes) else "unchecked"


def _parse(raw: str) -> List[Dict[str, Any]]:
    start, end = (raw or "").find("{"), (raw or "").rfind("}")
    if start == -1 or end <= start:
        return []
    try:
        return list(json.loads(raw[start:end + 1]).get("verdicts") or [])
    except (ValueError, AttributeError):
        return []


def run_check_d(sentences: List[Any], claims_by_id: Dict[str, Any], lanes: Dict[str, str], llm: Optional[Any]) -> Dict[str, Any]:
    """Judge every grounded sentence against its cited quotes; returns the summary and one item per sentence."""
    items: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    for s in sentences:
        cited = [claims_by_id[c] for c in (s.claim_ids_json or []) if c in claims_by_id]
        if s.type not in GROUNDED_TYPES or not cited:
            continue
        remote = [c for c in cited if lanes.get(c.source_id, "academic") != "practitioner"]
        item = {"sentence_id": s.id, "ordinal": s.ordinal, "text": s.text, "type": s.type,
                "quotes": [_quote(c) for c in remote][:MAX_QUOTES], "verdict": "", "reason": "", "method": ""}
        if not remote:
            item.update(verdict="local, not checked", reason="Rests on your field notes, which stay on this machine.")
        else:
            item["_claims"] = remote
            pending.append(item)
        items.append(item)

    method = "model" if llm is not None else "rules"
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start:start + BATCH_SIZE]
        verdicts: Dict[str, Dict[str, Any]] = {}
        if llm is not None:
            blocks = []
            for k, it in enumerate(batch, 1):
                quotes = "\n".join(f"   - {q}" for q in it["quotes"])
                sentence = re.sub(r"\s+", " ", it["text"])
                blocks.append(f"[S{k}] {sentence}\n   Quotes:\n{quotes}")
            try:
                raw = llm.generate(PROMPT.format(items="\n\n".join(blocks)), system_prompt="Output valid JSON only.",
                                   temperature=0.0, json_mode=True)
                verdicts = {str(v.get("id", "")).upper(): v for v in _parse(raw) if isinstance(v, dict)}
            except Exception as e:  # a failed batch falls back to the rule verdict
                logger.warning("Check D batch failed (%s)", type(e).__name__)
        for k, it in enumerate(batch, 1):
            v = verdicts.get(f"S{k}") or {}
            verdict = str(v.get("verdict", "")).strip().lower()
            if verdict in VERDICTS:
                it.update(verdict=verdict, reason=str(v.get("reason", ""))[:300], method="model")
            else:
                it.update(verdict=_rule_verdict(it["text"], it["_claims"]), method="rules",
                          reason="Judged by rule: figures and key terms checked against the quotes.")
    for it in items:
        it.pop("_claims", None)

    judged = [i for i in items if i["verdict"] != "local, not checked"]
    count = lambda v: sum(1 for i in judged if i["verdict"] == v)
    checked = len(judged)
    return {"checked": checked, "supported": count("supported"), "partial": count("partial"),
            "unsupported": count("unsupported"), "unchecked": count("unchecked"),
            "rate": round(count("supported") / checked, 3) if checked else 0.0,
            "method": method if any(i["method"] == "model" for i in judged) or llm is None else "rules",
            "items": sorted(items, key=lambda i: (["unsupported", "partial", "unchecked", "supported"].index(i["verdict"])
                                                   if i["verdict"] in ("unsupported", "partial", "unchecked", "supported") else 4,
                                                   i["ordinal"]))}


def apply_check_d(result: Dict[str, Any], check_d: Dict[str, Any]) -> None:
    """Record Check D on the run; any unsupported sentence blocks publishing."""
    result["check_d"] = check_d
    n = int(check_d.get("unsupported") or 0)
    if n:
        pr = result.setdefault("publish_res", {})
        reason = (f"Check D: {n} sentence{'s are' if n != 1 else ' is'} not supported by the quotes cited; "
                  "fix the wording or exclude the evidence, then re-draft.")
        pr.update(status="BLOCKED", allowed=False, reasons=[reason] + list(pr.get("reasons") or []))
        pr["reason"] = " ".join(pr["reasons"])
        result["status"] = "BLOCKED"
