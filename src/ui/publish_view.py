"""Publish step (S6): whether a run's draft can be published by a human, and why not."""

from __future__ import annotations

import os
from typing import Any, Dict, Tuple

from src.publish.publisher import UNPUBLISHABLE_RUN_STATUS


def publish_eligibility(results: Dict[str, Any]) -> Tuple[bool, bool, str]:
    """(eligible, needs_reason, why_not). PUBLISH_READY can be published by a named reviewer;
    REVISE only with a logged reason; every other status cannot be published."""
    if results.get("is_stub_mode"):
        return False, False, "Test mode: synthetic data cannot be published."
    if os.getenv("HOSTED_DEMO") == "1":
        return False, False, "Publishing is disabled in hosted demo mode: stateless execution only."
    if not results.get("doc_id"):
        return False, False, "Nothing was drafted, so there is nothing to publish."
    status = str(results.get("status") or "").upper()
    if status == "PUBLISH_READY":
        return True, False, ""
    if status == "REVISE":
        return True, True, "The score is in the REVISE band: publishing needs your reason, which is logged."
    return False, False, UNPUBLISHABLE_RUN_STATUS.get(status, f"Status '{status or 'unknown'}' cannot be published.")


GATE_PLAIN = {
    "G1": ("Grounding", "Every finding, signal and risk cites ledger evidence. Roadmap steps are recommendations and are not checked here."),
    "G2": ("Numbers and support", "Numbers appear in the cited claims, and each sentence overlaps the quote it cites."),
    "G3": ("Topic and entity fit", "Cited sources are about the approved question, and named products match the evidence."),
    "G4": ("Honest wording", "No verb is stronger than the weakest cited claim's grade allows."),
    "G5": ("Confidentiality", "No denylisted name appears, and practitioner notes are confirmed as abstracted."),
    "G6": ("Copyright", "Quotes are short and nothing is copied verbatim at length."),
}
STATE_LABEL = {"PASS": "PASS", "FAIL": "FAIL", "NO_DATA": "NO DATA (counts as fail)"}


def gate_rows(gates_audit: Dict[str, Any]) -> list:
    """Plain-English rows for the six gates, verdict first. A gate missing from the audit shows as NO DATA."""
    hard = (gates_audit or {}).get("hard_gates") or {}
    rows = []
    for gid, (name, checks) in GATE_PLAIN.items():
        g = hard.get(gid) or {}
        state = g.get("state") or ("PASS" if g.get("pass") is True else "NO_DATA" if not g else "FAIL")
        rows.append({
            "Gate": f"{gid} {name}",
            "Result": STATE_LABEL.get(state, state),
            "Why": g.get("reason_plain") or (
                "Not audited for this run." if not g
                else "Audited before gate reasons were recorded: re-draft to see why." if state == "FAIL"
                else "Checked and passed."
            ),
            "What it checks": checks,
        })
    return rows


def gates_summary(gates_audit: Dict[str, Any]) -> str:
    rows = gate_rows(gates_audit)
    n_pass = sum(1 for r in rows if r["Result"] == "PASS")
    return f"{n_pass}/{len(rows)} GATES PASS"
