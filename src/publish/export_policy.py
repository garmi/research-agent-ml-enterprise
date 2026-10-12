"""Export Policy & Gate Control (Section A2-4).

Enforces strict export restrictions based on publication and governance gates:
1. BLOCKED outputs: Zero exports allowed, no overrides.
2. NOT_PUBLISHABLE / REVISE outputs: Only draft exports (.md and .json) watermarked
   with 'DRAFT, NOT FOR PUBLICATION' and listing failing gates.
   LinkedIn pack, presentation deck, and paper index are strictly disabled.
3. PUBLISH_READY outputs: Full exports enabled across all 5 deliverable formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExportPermissions:
    status: str
    is_blocked: bool
    can_download_draft: bool
    can_download_full: bool
    can_download_deck: bool
    can_download_linkedin: bool
    can_download_csv: bool
    failing_gates: List[str] = field(default_factory=list)


def evaluate_export_permissions(
    status: str,
    allowed: bool = False,
    gate_violations: Optional[Dict[str, List[str]]] = None,
    reasons: Optional[List[str]] = None,
    quality_score: Optional[float] = None,
) -> ExportPermissions:
    """Evaluate download permissions for the 5 export formats."""
    status_upper = (status or "NOT_PUBLISHABLE").upper()
    is_blocked = (status_upper == "BLOCKED")
    is_publish_ready = (status_upper == "PUBLISH_READY") and (allowed is True) and (not is_blocked)

    failing_gates: List[str] = []
    if gate_violations:
        for gate_key, errs in gate_violations.items():
            for err in errs:
                failing_gates.append(f"{gate_key}: {err}")
    if reasons and not failing_gates:
        failing_gates = list(reasons)
    if not is_publish_ready and not failing_gates:
        if quality_score is not None:
            failing_gates.append(f"Composite score {quality_score}/100 ({status_upper}) below PUBLISH_READY threshold (≥ 85)")
        else:
            failing_gates.append(f"Quality status '{status_upper}' below PUBLISH_READY threshold (≥ 85)")

    if is_blocked:
        return ExportPermissions(
            status="BLOCKED",
            is_blocked=True,
            can_download_draft=False,
            can_download_full=False,
            can_download_deck=False,
            can_download_linkedin=False,
            can_download_csv=False,
            failing_gates=failing_gates,
        )

    if is_publish_ready:
        return ExportPermissions(
            status="PUBLISH_READY",
            is_blocked=False,
            can_download_draft=False,
            can_download_full=True,
            can_download_deck=True,
            can_download_linkedin=True,
            can_download_csv=True,
            failing_gates=[],
        )

    # Any non-publishable draft status (NOT_PUBLISHABLE, REVISE, etc.)
    return ExportPermissions(
        status=status_upper,
        is_blocked=False,
        can_download_draft=True,
        can_download_full=False,
        can_download_deck=False,
        can_download_linkedin=False,
        can_download_csv=False,
        failing_gates=failing_gates,
    )
