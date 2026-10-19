"""Check A: is the harvested evidence about the approved question? (S3, DEC-016)

Per source, a model judges on_topic / off_topic and a rule floor can override it:
a source that shares too few salient terms with the approved question is off_topic
whatever the model says. Run level, a count rule decides whether the run proceeds.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.analysis.relevance import STOPWORDS, normalize_text
from src.engine.checks import ABSTAIN, CheckVerdict

logger = logging.getLogger(__name__)

CHECK_A_ID = "check_a_on_topic"
# v1 stays live until the Check A bake-off picks a model: qwen2.5:3b returns malformed output on v2.
PROMPT_FILE_PATH = "prompts/check_a_on_topic_v1.md"
BATCH_SIZE = 12
TEXT_CHARS = 320

# Pure filler for the floor. Domain words such as "delivery" or "productivity" stay salient:
# the floor only catches sources that share nothing with the question.
FILLER_WORDS = {
    "empirical", "evidence", "study", "studies", "research", "analysis", "evaluation", "impact",
    "effect", "effects", "affect", "gains", "assessment", "implications", "guidance", "perspective",
    "information", "known", "trade", "offs", "tradeoffs", "should", "could", "would", "may",
    "might", "must", "why", "when", "where", "there", "any", "has", "have", "its",
}


@dataclass
class SourceItem:
    source_id: str
    lane: str
    title: str
    text: str
    claim_ids: List[str] = field(default_factory=list)


@dataclass
class CheckAResult:
    passed: bool
    on_topic_ids: Set[str]
    verdicts: List[CheckVerdict]
    reason_plain: str
    on_topic_count: int
    total_count: int


def get_prompt_hash(prompt_path: Optional[str | Path] = None) -> str:
    path = Path(prompt_path or PROMPT_FILE_PATH)
    if not path.exists():
        return hashlib.sha256(path.name.encode("utf-8")).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def salient_terms(question: str) -> Set[str]:
    return {
        t for t in normalize_text(question).split()
        if len(t) >= 2 and t not in STOPWORDS and t not in FILLER_WORDS
    }


def paper_source_id(paper: Dict[str, Any]) -> str:
    return str(paper.get("id") or paper.get("doi") or paper.get("url") or paper.get("title"))


def build_source_items(
    academic_papers: List[Dict[str, Any]],
    enterprise_claims: List[Any],
    practitioner_claims: List[Any],
    sources_lookup: Optional[Dict[str, Any]] = None,
) -> List[SourceItem]:
    """One item per source: papers as-is, enterprise/practitioner claims grouped by source_id."""
    items: List[SourceItem] = []
    for p in academic_papers:
        sid = paper_source_id(p)
        items.append(SourceItem(
            source_id=sid,
            lane="academic",
            title=str(p.get("title") or "Untitled"),
            text=f"{p.get('title') or ''}. {p.get('abstract') or ''}",
        ))
    for lane, claims in (("enterprise", enterprise_claims), ("practitioner", practitioner_claims)):
        grouped: Dict[str, SourceItem] = {}
        for c in claims:
            sid = str(c.source_id)
            if sid not in grouped:
                src = (sources_lookup or {}).get(sid)
                grouped[sid] = SourceItem(source_id=sid, lane=lane, title=str(getattr(src, "title", None) or sid), text="")
            grouped[sid].text += f" {c.text or ''} {c.source_excerpt or ''}"
            grouped[sid].claim_ids.append(c.id)
        items.extend(grouped.values())
    return items


def _word_match(a: str, b: str) -> bool:
    """Stricter than relevance.stems_match: inflections only ('assistant'~'assistants', 'code'~'coding'),
    so 'sourdough' does not match 'sources'."""
    if a == b:
        return True
    if min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)):
        return True
    prefix = 0
    for x, y in zip(a, b):
        if x != y:
            break
        prefix += 1
    return prefix >= 3 and prefix >= min(len(a), len(b)) - 1


def _term_alternates(terms: Set[str], synonyms: Optional[Dict[str, List[str]]]) -> Dict[str, Set[str]]:
    """Each salient term plus its configured synonym phrases (research.head_term_synonyms)."""
    alternates = {t: {t} for t in terms}
    for key, phrases in (synonyms or {}).items():
        key_norm = normalize_text(key)
        for t in terms:
            if _word_match(t, key_norm):
                alternates[t].update(normalize_text(ph) for ph in phrases or [] if normalize_text(ph))
    return alternates


def build_question_context(
    question: str,
    package: Optional[Dict[str, Any]],
    alternates: Dict[str, Set[str]],
) -> str:
    """What the model sees about the question: the approved package and the equivalent terms
    configured for the question's own salient terms (research.head_term_synonyms)."""
    pkg = package or {}
    lines = [f"Approved question:\n{question}"]
    for label, key in (("Sub-questions", "sub_questions"), ("In scope", "in_scope"), ("Out of scope", "out_of_scope")):
        values = [str(v).strip() for v in (pkg.get(key) or []) if str(v).strip()]
        if values:
            lines.append(f"{label}:\n" + "\n".join(f"- {v}" for v in values))
    equivalents = [
        f"- {term}: {', '.join(sorted(alts - {term}))}"
        for term, alts in sorted(alternates.items()) if alts - {term}
    ]
    if equivalents:
        lines.append("Equivalent terms (count as the subject itself):\n" + "\n".join(equivalents))
    return "\n\n".join(lines)


def _rule_floor(alternates: Dict[str, Set[str]], text: str, min_terms: int) -> Dict[str, Any]:
    norm = normalize_text(text)
    tokens = set(norm.split())

    def hit(phrase: str) -> bool:
        return all(any(_word_match(word, tok) for tok in tokens) for word in phrase.split())

    matched = sorted(t for t, alts in alternates.items() if any(hit(a) for a in alts))
    needed = min(min_terms, len(alternates))
    off = bool(alternates) and len(matched) < needed
    return {"off_topic": off, "matched_terms": matched}


def _extract_json(raw: str) -> Dict[str, Any]:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(raw[start:end + 1])


def _judge_with_model(llm: Any, question: str, context: str, items: List[SourceItem], template: str) -> Dict[str, Dict[str, str]]:
    """Return {source_id: {"verdict", "reason"}}. Any failure leaves sources unjudged (abstain)."""
    judged: Dict[str, Dict[str, str]] = {}
    if llm is None:
        return judged
    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        keys = {f"S{i}": item for i, item in enumerate(batch, start=1)}
        lines = []
        for k, it in keys.items():
            title = it.title.replace("|", "/")
            snippet = re.sub(r"\s+", " ", it.text)[:TEXT_CHARS]
            lines.append(f"[{k}] lane: {it.lane} | title: {title} | text: {snippet}")
        # v1 prompts take {question}; v2 prompts take {context} (question + package + equivalent terms).
        prompt = template.replace("{context}", context).replace("{question}", question).replace("{items}", "\n".join(lines))
        try:
            data = _extract_json(llm.generate(prompt, temperature=0.0, json_mode=True))
        except Exception as exc:  # unavailable or unparseable model abstains
            logger.info("Check A model abstained on batch %d: %s", start // BATCH_SIZE, exc)
            continue
        entries = data.get("verdicts", []) if isinstance(data, dict) else []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue  # malformed entry: that source stays unjudged (abstain)
            item = keys.get(str(entry.get("id", "")).strip())
            verdict = str(entry.get("verdict", "")).strip().lower()
            if item and verdict in ("on_topic", "off_topic"):
                judged[item.source_id] = {"verdict": verdict, "reason": str(entry.get("reason", ""))[:200]}
    return judged


def run_check_a(
    question: str,
    items: List[SourceItem],
    llm: Any,
    *,
    run_id: str,
    attempt: int,
    min_on_topic_sources: int = 1,
    floor_min_terms: int = 1,
    synonyms: Optional[Dict[str, List[str]]] = None,
    approval_ref: Optional[Dict[str, Any]] = None,
    package: Optional[Dict[str, Any]] = None,
    prompt_path: Optional[str | Path] = None,
) -> CheckAResult:
    prompt_path = Path(prompt_path or PROMPT_FILE_PATH)
    template = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else "{context}\n{items}"
    prompt_hash = get_prompt_hash(prompt_path)
    model_id = str(getattr(llm, "model", None) or type(llm).__name__) if llm is not None else None
    terms = salient_terms(question)
    alternates = _term_alternates(terms, synonyms)

    # Practitioner notes never go to the check model (DEC-013: they never reach a remote model,
    # and the check model may be remote). They are never removed by Check A; the rule floor decides.
    model_items = [it for it in items if it.lane != "practitioner"]
    judged = _judge_with_model(llm, question, build_question_context(question, package, alternates), model_items, template)
    verdicts: List[CheckVerdict] = []
    on_topic: Set[str] = set()
    for item in items:
        floor = _rule_floor(alternates, item.text, floor_min_terms)
        model = judged.get(item.source_id)
        model_verdict = model["verdict"] if model else ABSTAIN
        if floor["off_topic"]:
            reason = "Shares no key term with the approved question."
        elif model:
            reason = model["reason"] or f"Model judged {model_verdict.replace('_', '-')}."
        else:
            reason = "Model gave no verdict; passed the key-term floor."
        v = CheckVerdict(
            check_id=CHECK_A_ID, run_id=run_id, object_type="source", object_id=item.source_id,
            model_verdict=model_verdict,
            rule_verdict="off_topic" if floor["off_topic"] else "on_topic",
            rule_decisive=floor["off_topic"],
            reason_plain=reason, attempt=attempt, model_id=model_id, prompt_hash=prompt_hash,
            details_json={"lane": item.lane, "title": item.title, **floor},
        )
        verdicts.append(v)
        if v.final == "on_topic":
            on_topic.add(item.source_id)

    n_on, n_all = len(on_topic), len(items)
    passed = n_on >= min_on_topic_sources
    need = f"at least {min_on_topic_sources} on-topic source{'' if min_on_topic_sources == 1 else 's'} {'is' if min_on_topic_sources == 1 else 'are'} needed"
    if passed:
        reason = f"{n_on} of {n_all} sources are on-topic for the approved question ({need})."
    elif n_all == 0:
        reason = f"The search found no sources that match the approved question; {need}."
    else:
        reason = f"Only {n_on} of {n_all} sources are on-topic for the approved question; {need}."
    verdicts.append(CheckVerdict(
        check_id=CHECK_A_ID, run_id=run_id, object_type="run", object_id=run_id,
        model_verdict=None, rule_verdict="pass" if passed else "fail", rule_decisive=True,
        reason_plain=reason, attempt=attempt, model_id=model_id, prompt_hash=prompt_hash,
        details_json={
            "question": question, "salient_terms": sorted(terms),
            "on_topic_sources": n_on, "total_sources": n_all, "min_on_topic_sources": min_on_topic_sources,
            "approval_ref": approval_ref or {},
        },
    ))
    return CheckAResult(passed, on_topic, verdicts, reason, n_on, n_all)
