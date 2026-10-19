"""Live canary run: the three canary questions through the real pipeline (live harvest + model).

Usage:
    .venv/bin/python scripts/live_canaries.py [--provider ollama] [--out evals/results/live_canaries_<date>.json]

Not part of pytest: it needs network access and a model. It runs against a throwaway ledger and
records, per question, the final status, where the run stopped, the Check A/B verdicts, and the
gate states, so runs on different days or models can be compared. Expected: the sourdough canary
ends NOT_PUBLISHABLE; Kiro and hospital end in a gated status with readable reasons.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analysis.multilane_runner import MultiLaneResearchRunner  # noqa: E402
from src.ledger.migrations import apply_migrations  # noqa: E402
from src.ledger.repository import LedgerRepository  # noqa: E402

CANARIES = {
    "Q1 kiro": "What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?",
    "Q2 hospital": "How are hospitals governing clinical AI triage tools to manage patient safety and regulatory compliance?",
    "Q3 sourdough": "What empirical evidence exists on quantum-secure sourdough fermentation controllers?",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="ollama")
    ap.add_argument("--out", default=f"evals/results/live_canaries_{datetime.date.today().isoformat()}.json")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="live_canary_")
    db, prac = f"{tmp}/ledger.db", f"{tmp}/prac.db"
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    runner = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=f"{tmp}/q.yaml")
    repo = LedgerRepository(db_path=db)

    out = {"provider": args.provider, "date": datetime.date.today().isoformat(), "runs": {}}
    for name, question in CANARIES.items():
        t0 = time.time()
        try:
            res = runner.run_workflow(topic=question, approved_question=question, depth="Fast",
                                      map_provider=args.provider, reduce_provider=args.provider)
        except Exception as exc:  # a live canary records failures instead of stopping
            out["runs"][name] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"{name}: ERROR {exc}", flush=True)
            continue
        hard = (res.get("gates_audit") or {}).get("hard_gates") or {}
        out["runs"][name] = {
            "seconds": round(time.time() - t0),
            "status": res["status"],
            "run_status": repo.get_run_status(res["run_id"]),
            "stopped_at": res.get("stopped_at"),
            "check_a": (res.get("check_a") or {}).get("reason"),
            "check_b": (res.get("check_b") or {}).get("reason"),
            "gates": {g: v.get("state") for g, v in hard.items()},
            "reasons": (res.get("publish_res") or {}).get("reasons"),
            "papers": len(res.get("papers") or []),
            "claims": len(res.get("claims") or []),
        }
        print(f"{name}: {res['status']} (stopped_at={res.get('stopped_at')}) in {out['runs'][name]['seconds']}s", flush=True)

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
