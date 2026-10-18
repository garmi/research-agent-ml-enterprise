"""Live check script for Slice S2 with real local Ollama model.

Evaluates Text A, Text B, and Text C against question reasoning and approval logic.
Writes approvals ONLY to a temporary directory, never to ledger/.
Opt-in script, NOT collected by pytest.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.engine.reasoner import (
    reason_question,
    validate_reasoned_package,
    find_unlisted_terms,
    _call_model_for_reasoning,
    _parse_model_json,
)
from src.engine.approvals import save_gate1_approval, list_gate1_approval_files
from src.engine.ids import generate_question_id


TEXT_A = (
    "We keep hearing that AI coding tools like Kiro make teams much faster, "
    "but at a large enterprise I work with the licence costs are all over the place "
    "and nobody can say whether the credits are worth it. "
    "I think governance is the missing piece. "
    "I need something for a leadership conversation about whether to standardise "
    "on one tool and what controls to put around usage."
)

TEXT_B = (
    "Does quantum-secure sourdough fermentation improve enterprise API latency?"
)

TEXT_C = (
    "Our hospital group is piloting an AI tool that sorts emergency patients by urgency. "
    "The vendor says it cuts waiting times and is safer than nurses doing it. "
    "The board wants to know who is accountable if it gets a case wrong "
    "and what oversight we need before rolling it out to all sites."
)


def format_ui_proposal(proposal: dict) -> str:
    lines = []
    lines.append(f"Refined Question: {proposal.get('refined_question', '')}")
    lines.append("Sub-questions:")
    for sq in proposal.get("sub_questions", []):
        lines.append(f"  - {sq}")
    lines.append("Premises to Test:")
    for pt in proposal.get("premises_to_test", []):
        lines.append(f"  - {pt}")
    lines.append("In Scope:")
    for is_item in proposal.get("in_scope", []):
        lines.append(f"  - {is_item}")
    lines.append("Out of Scope:")
    for oos in proposal.get("out_of_scope", []):
        lines.append(f"  - {oos}")
    lines.append("Evidence Needed:")
    for en in proposal.get("evidence_needed", []):
        lines.append(f"  - {en}")
    lines.append("Ambiguities:")
    for amb in proposal.get("ambiguities", []):
        lines.append(f"  - {amb}")
    lines.append("Changes and Reasons:")
    for cr in proposal.get("changes_and_reasons", []):
        lines.append(f"  - {cr.get('change')}: {cr.get('reason')}")
    lines.append("Coverage Map:")
    for sent, usage in proposal.get("coverage_map", {}).items():
        lines.append(f"  - \"{sent}\" => {usage}")
    lines.append(f"Added Terms: {proposal.get('added_terms', [])}")
    return "\n".join(lines)


def run_check():
    print("=" * 80)
    print("SLICED S2 LIVE CHECK WITH REAL LOCAL MODEL (qwen2.5:3b-instruct)")
    print("=" * 80)

    # Force stub off and hosted demo off
    os.environ["STUB_LLM"] = "0"
    os.environ["HOSTED_DEMO"] = "0"

    cases = [
        ("Text A (Enterprise Kiro Governance)", TEXT_A),
        ("Text B (Adversarial Sourdough)", TEXT_B),
        ("Text C (Hospital Emergency Triage)", TEXT_C),
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        for name, text in cases:
            print("\n" + "=" * 80)
            print(f"CASE: {name}")
            print(f"INPUT TEXT:\n  \"{text}\"")
            print("=" * 80)

            # 1. Capture Raw Model Response
            raw_response = _call_model_for_reasoning(
                user_text=text,
                angle_hint="Enterprise impact",
                provider="ollama",
                model="qwen2.5:3b-instruct",
                feedback=None,
                previous_package=None,
            )
            print("\n[1] RAW MODEL JSON:")
            print(raw_response.strip())

            # Parse and validate
            proposal = _parse_model_json(raw_response)
            val_ok, val_errors = validate_reasoned_package(proposal, text)
            unlisted = find_unlisted_terms(proposal, text)

            print("\n[2] VALIDATION RESULT:")
            print(f"  Is Valid: {val_ok}")
            print(f"  Errors: {val_errors}")
            print(f"  Unlisted Terms (UI Checkbox trigger): {unlisted}")

            # UI representation
            print("\n[3] PROPOSAL AS SHOWN IN UI:")
            print(format_ui_proposal(proposal))

            # Approval package in temp directory
            qid = generate_question_id(proposal.get("refined_question", text))
            approval = save_gate1_approval(
                question_id=qid,
                question_text=proposal.get("refined_question"),
                raw_user_text=text,
                final_package=proposal,
                approvals_dir=tmp_dir,
                approved_by="live_check_reviewer",
                provider="ollama",
                model_name="qwen2.5:3b-instruct",
            )
            approval_files = list_gate1_approval_files(qid, approvals_dir=tmp_dir)
            with open(approval_files[-1], "r", encoding="utf-8") as f:
                approval_json_content = f.read()

            print("\n[4] APPROVAL JSON (Written strictly to TEMP directory):")
            print(approval_json_content)

            # Evaluate Pass Criteria
            print("\n[5] CRITERIA EVALUATION:")
            if name.startswith("Text A"):
                premises_str = " ".join(proposal.get("premises_to_test", [])).lower()
                has_speed_premise = any(w in premises_str for w in ["faster", "speed", "productivity", "throughput", "velocity", "worth"])
                ref_q = proposal.get("refined_question", "").lower()
                has_std = any(w in ref_q for w in ["standardis", "standardiz", "adopt", "tool", "select", "one tool", "platform", "licen"])
                has_gov = any(w in ref_q for w in ["control", "govern", "usage", "policy", "oversight", "cost"])
                cov = proposal.get("coverage_map", {})
                print(f"  - 'tools make teams much faster' in premises_to_test: {has_speed_premise}")
                print(f"  - Refined question reflects standardisation: {has_std}")
                print(f"  - Refined question reflects controls/governance: {has_gov}")
                print(f"  - Coverage count: {len(cov)} sentences")
            elif name.startswith("Text B"):
                premises_and_amb = " ".join(proposal.get("premises_to_test", []) + proposal.get("ambiguities", [])).lower()
                flags_connection = any(w in premises_and_amb for w in ["sourdough", "fermentation", "quantum", "implausible", "unrelated", "causal", "premise", "ungrounded", "link", "nexus", "biological"])
                sub_qs = proposal.get("sub_questions", [])
                print(f"  - Ungrounded connection flagged in premises/ambiguities: {flags_connection}")
                print(f"  - Sub-questions count: {len(sub_qs)} (no invented supporting sub-questions)")
            elif name.startswith("Text C"):
                premises_str = " ".join(proposal.get("premises_to_test", [])).lower()
                has_time_premise = any(w in premises_str for w in ["waiting", "wait time", "time", "speed", "cut"])
                has_nurse_premise = any(w in premises_str for w in ["nurse", "safer", "safety", "accuracy"])
                ref_q = proposal.get("refined_question", "").lower()
                has_accountability = any(w in ref_q for w in ["accountab", "liab", "responsib", "blame", "legal", "err"])
                has_oversight = any(w in ref_q for w in ["oversight", "govern", "control", "monitor", "safeguard", "rollout", "audit", "policy"])
                cov = proposal.get("coverage_map", {})
                added = proposal.get("added_terms", [])
                print(f"  - 'cuts waiting times' in premises_to_test: {has_time_premise}")
                print(f"  - 'safer than nurses' in premises_to_test: {has_nurse_premise}")
                print(f"  - Refined question covers accountability: {has_accountability}")
                print(f"  - Refined question covers oversight: {has_oversight}")
                print(f"  - Coverage count: {len(cov)} sentences")
                print(f"  - Added terms (laws/standards): {added}")


if __name__ == "__main__":
    run_check()
