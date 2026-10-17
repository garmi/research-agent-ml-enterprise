"""Scope definition and Gate 2 Scope Validation (Step 2 Scope).

Defines the configuration for research scope:
- Selected source lanes (academic, enterprise, practitioner)
- Time window (months)
- Depth / breadth configuration
- Target report format (brief, whitepaper, field_note)
- Practitioner field notes and URLs with mandatory abstraction confirmation

Enforces strict binding with Gate 1 Problem Framing Approval:
If the user modifies the question text or switches the approved framing lens in Step 1,
the scope configuration is invalidated and must be reviewed before execution.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.engine.approvals import Gate1Approval
from src.engine.ids import compute_question_sha256


class ScopeValidationError(Exception):
    """Raised when scope configuration fails validation against Gate 1 approval."""
    pass


@dataclass
class ScopeConfig:
    question_id: str
    question_text: str
    framing_id: str
    source_types: List[str] = field(default_factory=lambda: ["academic", "enterprise"])
    time_window_months: int = 36
    depth: str = "Standard"
    report_format: str = "brief"
    practitioner_notes: Optional[str] = None
    practitioner_urls: List[str] = field(default_factory=list)
    practitioner_abstraction_confirmed: bool = False
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def validate_scope_against_framing(scope: ScopeConfig, approval: Gate1Approval) -> bool:
    """Validate that scope configuration matches the approved Gate 1 framing.

    Raises ScopeValidationError if:
      - Question ID does not match.
      - Question text hash does not match approval hash (question was edited).
      - Framing lens ID does not match approved framing ID (lens was switched).

    Returns True if valid.
    """
    if scope.question_id != approval.question_id:
        raise ScopeValidationError(
            f"Question ID mismatch: scope is for '{scope.question_id}', but approval is for '{approval.question_id}'."
        )

    current_hash = compute_question_sha256(scope.question_text)
    if current_hash != approval.question_sha256:
        raise ScopeValidationError(
            "Question text has changed since problem framing approval. Scope is invalidated. "
            "Please review framing and confirm scope again."
        )

    if scope.framing_id != approval.framing_id:
        raise ScopeValidationError(
            f"Framing lens mismatch: scope was configured for '{scope.framing_id}', "
            f"but active approved framing is '{approval.framing_id}'. Scope is invalidated."
        )

    return True
