"""Check A bake-off: score a model + prompt against hand-labelled real harvests.

Usage:
    .venv/bin/python evals/bakeoff_check_a.py --provider ollama --model qwen2.5:3b-instruct \
        [--prompt prompts/check_a_on_topic_v2.md] [--out evals/results/check_a_<name>.json]

Reports, for the model's own verdicts and for Check A's final verdicts (after the rule floor):
precision / recall / accuracy with on_topic as the positive class, on all items and on the
non-borderline items, plus whether each question's run would pass Check A as expected
(the sourdough canary must stop; the others must pass).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

import src.engine.check_a_on_topic as check_a  # noqa: E402
from src.engine.check_a_on_topic import SourceItem, run_check_a  # noqa: E402

DATA = Path(__file__).resolve().parent / "data" / "check_a_labelled_v1.json"
EXPECTED_RUN_PASS = {"kiro": True, "hospital": True, "assistants": True, "sourdough": False}


def _scores(pairs: List[tuple]) -> Dict[str, Any]:
    tp = sum(1 for pred, gold in pairs if pred == "on_topic" and gold == "on_topic")
    fp = sum(1 for pred, gold in pairs if pred == "on_topic" and gold == "off_topic")
    fn = sum(1 for pred, gold in pairs if pred != "on_topic" and gold == "on_topic")
    tn = sum(1 for pred, gold in pairs if pred != "on_topic" and gold == "off_topic")
    n = len(pairs)
    return {
        "n": n,
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "accuracy": round((tp + tn) / n, 3) if n else None,
        "false_on_topic": fp,
        "false_off_topic": fn,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="ollama")
    ap.add_argument("--model", default=None, help="Ollama/Gemini model name (overrides config)")
    ap.add_argument("--prompt", default=check_a.PROMPT_FILE_PATH)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from dotenv import load_dotenv

    from src.llm.factory import build_llm

    load_dotenv()  # same as web_app: picks up GEMINI_API_KEY from the nearest .env

    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8")) or {}
    if args.model:
        os.environ["OLLAMA_MODEL" if args.provider == "ollama" else "GEMINI_MODEL"] = args.model
    llm = build_llm(args.provider, cfg)
    check_a.PROMPT_FILE_PATH = args.prompt
    synonyms = (cfg.get("research") or {}).get("head_term_synonyms")

    data = json.loads(DATA.read_text(encoding="utf-8"))
    by_q: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for it in data["items"]:
        by_q[it["question_key"]].append(it)

    rows, runs = [], {}
    t0 = time.time()
    for key, items in by_q.items():
        src_items = [SourceItem(source_id=f"{key}-{i}", lane=it["lane"], title=it["title"], text=it["text"]) for i, it in enumerate(items)]
        res = run_check_a(items[0]["question"], src_items, llm, run_id=f"bakeoff-{key}", attempt=0, synonyms=synonyms)
        by_id = {v.object_id: v for v in res.verdicts if v.object_type == "source"}
        for i, it in enumerate(items):
            v = by_id[f"{key}-{i}"]
            rows.append({
                "question": key, "title": it["title"], "gold": it["label"], "borderline": it.get("borderline", False),
                "model": v.model_verdict, "final": v.final, "rule_decisive": v.rule_decisive, "reason": v.reason_plain,
            })
        runs[key] = {"passed": res.passed, "expected": EXPECTED_RUN_PASS[key], "on_topic": res.on_topic_count, "total": res.total_count}

    def pick(field: str, only_clear: bool) -> List[tuple]:
        return [(r[field], r["gold"]) for r in rows if not (only_clear and r["borderline"])]

    report = {
        "provider": args.provider,
        "model": getattr(llm, "model", type(llm).__name__),
        "prompt": args.prompt,
        "seconds": round(time.time() - t0),
        "abstained": sum(1 for r in rows if r["model"] == "abstain"),
        "model_all": _scores(pick("model", False)),
        "model_clear": _scores(pick("model", True)),
        "final_all": _scores(pick("final", False)),
        "final_clear": _scores(pick("final", True)),
        "runs": runs,
        "runs_as_expected": sum(1 for r in runs.values() if r["passed"] == r["expected"]),
        "rows": rows,
    }
    out = Path(args.out or f"evals/results/check_a_{report['model'].replace(':', '_').replace('/', '_')}_{Path(args.prompt).stem}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    summary = {k: report[k] for k in ("model", "prompt", "seconds", "abstained", "model_clear", "final_clear", "runs_as_expected")}
    print(json.dumps(summary, indent=1))
    for k, r in runs.items():
        print(f"  {k:<11} passed={r['passed']!s:<5} expected={r['expected']!s:<5} on_topic={r['on_topic']}/{r['total']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
