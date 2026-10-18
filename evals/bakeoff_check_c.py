"""Check C bake-off: does a judge catch drafted sentences that drop a claim's hedge?

Usage:
    .venv/bin/python evals/bakeoff_check_c.py --provider rules
    .venv/bin/python evals/bakeoff_check_c.py --provider ollama [--model qwen2.5:3b-instruct]
    .venv/bin/python evals/bakeoff_check_c.py --provider gemini [--model gemini-2.5-flash]
    options: [--prompt prompts/check_c_hedges_v1.md] [--out evals/results/check_c_<name>.json]

"dropped" (the sentence overstates the claim) is the positive class. A model abstention counts
as "kept": Check C never flags a sentence it could not judge. Per the S5 plan, Check C may hold
sentences for one rewrite only if precision on "dropped" is at least HOLD_PRECISION; otherwise
it ships warn-only, like Check D.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from src.engine.check_c_hedges import PROMPT_FILE_PATH, judge_hedges_with_model, rules_hedge_verdict  # noqa: E402

DATA = Path(__file__).resolve().parent / "data" / "check_c_pairs_v1.json"
HOLD_PRECISION = 0.85


def _scores(pairs: List[tuple]) -> Dict[str, Any]:
    tp = sum(1 for p, g in pairs if p == "dropped" and g == "dropped")
    fp = sum(1 for p, g in pairs if p == "dropped" and g == "kept")
    fn = sum(1 for p, g in pairs if p != "dropped" and g == "dropped")
    tn = sum(1 for p, g in pairs if p != "dropped" and g == "kept")
    return {
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "accuracy": round((tp + tn) / len(pairs), 3) if pairs else None,
        "false_alarms": fp,
        "missed": fn,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="rules", help="rules | ollama | gemini")
    ap.add_argument("--model", default=None)
    ap.add_argument("--prompt", default=PROMPT_FILE_PATH)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    pairs = json.loads(DATA.read_text(encoding="utf-8"))["pairs"]
    t0 = time.time()
    if args.provider == "rules":
        model_name = "rules"
        raw = [rules_hedge_verdict(p["claim_hedges"], p["sentence"]) for p in pairs]
        verdicts = [{"verdict": "dropped" if r == "dropped" else "kept", "reason": r} for r in raw]
        abstained = 0
    else:
        from dotenv import load_dotenv

        from src.llm.factory import build_llm

        load_dotenv()
        cfg = yaml.safe_load(open("config.yaml", encoding="utf-8")) or {}
        if args.model:
            os.environ["OLLAMA_MODEL" if args.provider == "ollama" else "GEMINI_MODEL"] = args.model
        llm = build_llm(args.provider, cfg)
        model_name = getattr(llm, "model", type(llm).__name__)
        verdicts = judge_hedges_with_model(llm, [{"claim": p["claim"], "sentence": p["sentence"]} for p in pairs], args.prompt)
        abstained = sum(1 for v in verdicts if v["verdict"] == "abstain")

    rows = [
        {"id": p["id"], "label": p["label"], "pred": "dropped" if v["verdict"] == "dropped" else "kept",
         "raw": v["verdict"], "reason": v["reason"], "sentence": p["sentence"], "note": p.get("note", "")}
        for p, v in zip(pairs, verdicts)
    ]
    dropped = _scores([(r["pred"], r["label"]) for r in rows])
    report = {
        "provider": args.provider,
        "model": model_name,
        "prompt": None if args.provider == "rules" else args.prompt,
        "seconds": round(time.time() - t0),
        "n": len(rows),
        "abstained": abstained,
        "dropped": dropped,
        "hold_precision": HOLD_PRECISION,
        "decision": "hold" if (dropped["precision"] or 0) >= HOLD_PRECISION else "warn_only",
        "rows": rows,
    }
    out = Path(args.out or f"evals/results/check_c_{str(model_name).replace(':', '_').replace('/', '_')}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("model", "seconds", "n", "abstained", "dropped", "decision")}, indent=1))
    for r in rows:
        if r["pred"] != r["label"]:
            print(f"  wrong {r['id']}: gold={r['label']} pred={r['pred']} ({r['raw']}) | {r['sentence']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
