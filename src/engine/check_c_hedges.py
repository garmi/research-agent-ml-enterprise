"""Check C: did the draft keep the claim's hedges? (S5, DEC-016) - scaffolding.

Two judges, compared by evals/bakeoff_check_c.py before Check C is wired into runs:
  - rules_hedge_verdict: word-list diff from synth/hedge_terms.yaml (cheap, deterministic)
  - judge_hedges_with_model: a model reads claim + sentence pairs
The bake-off decides whether Check C holds sentences for one rewrite or only warns.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.extract.hedges import find_hedge_terms

logger = logging.getLogger(__name__)

CHECK_C_ID = "check_c_hedges"
PROMPT_FILE_PATH = "prompts/check_c_hedges_v1.md"
BATCH_SIZE = 8


def get_prompt_hash(prompt_path: Optional[str] = None) -> str:
    path = Path(prompt_path or PROMPT_FILE_PATH)
    return hashlib.sha256(path.read_bytes() if path.exists() else path.name.encode("utf-8")).hexdigest()


def rules_hedge_verdict(claim_hedges: Optional[List[str]], sentence: str) -> str:
    """"no_hedge" if the claim has none; "kept" if the sentence has any hedge; otherwise "dropped"."""
    if not claim_hedges:
        return "no_hedge"
    return "kept" if find_hedge_terms(sentence) else "dropped"


def _extract_json(raw: str) -> Any:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(raw[start:end + 1])


def judge_hedges_with_model(llm: Any, pairs: List[Dict[str, str]], prompt_path: Optional[str] = None) -> List[Dict[str, str]]:
    """One {"verdict", "reason"} per pair, in order. Unavailable or malformed output abstains."""
    out = [{"verdict": "abstain", "reason": "Model gave no verdict."} for _ in pairs]
    if llm is None:
        return out
    path = Path(prompt_path or PROMPT_FILE_PATH)
    template = path.read_text(encoding="utf-8") if path.exists() else "{pairs}"
    for start in range(0, len(pairs), BATCH_SIZE):
        batch = list(enumerate(pairs[start:start + BATCH_SIZE], start=start))
        lines = []
        for k, (_, p) in enumerate(batch, start=1):
            claim = re.sub(r"\s+", " ", str(p.get("claim", "")))
            sentence = re.sub(r"\s+", " ", str(p.get("sentence", "")))
            lines.append(f"[H{k}] claim: {claim}\n     sentence: {sentence}")
        prompt = template.replace("{pairs}", "\n".join(lines))
        try:
            data = _extract_json(llm.generate(prompt, temperature=0.0, json_mode=True))
        except Exception as exc:
            logger.info("Check C model abstained on batch %d: %s", start // BATCH_SIZE, exc)
            continue
        entries = data.get("verdicts", []) if isinstance(data, dict) else []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            m = re.fullmatch(r"H(\d+)", str(entry.get("id", "")).strip())
            verdict = str(entry.get("verdict", "")).strip().lower()
            if m and verdict in ("kept", "dropped") and 1 <= int(m.group(1)) <= len(batch):
                idx = batch[int(m.group(1)) - 1][0]
                out[idx] = {"verdict": verdict, "reason": str(entry.get("reason", ""))[:200]}
    return out
