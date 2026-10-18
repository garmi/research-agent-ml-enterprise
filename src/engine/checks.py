"""Shared contract for the handoff checks A-D (DEC-016, docs/solution_design.md).

Every check produces CheckVerdict rows. Two invariants are enforced here, once:
  1. Rules override models, never the reverse (`resolve_final`).
  2. Nothing loops more than once (`record_verdict` refuses attempt > MAX_ATTEMPT).
"""

from __future__ import annotations

import datetime
import os
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

MAX_ATTEMPT = 1
ABSTAIN = "abstain"


class CheckLoopError(RuntimeError):
    """Raised when a check tries to retry or rewrite more than once."""


def resolve_final(model_verdict: Optional[str], rule_verdict: str, rule_decisive: bool) -> str:
    """A decisive rule wins; otherwise the model decides; an abstaining model defers to the rule."""
    if rule_decisive:
        return rule_verdict
    if model_verdict and model_verdict != ABSTAIN:
        return model_verdict
    return rule_verdict


@dataclass
class CheckVerdict:
    check_id: str
    run_id: str
    object_type: str
    object_id: str
    model_verdict: Optional[str]
    rule_verdict: str
    rule_decisive: bool
    reason_plain: str
    attempt: int = 0
    model_id: Optional[str] = None
    prompt_hash: Optional[str] = None
    details_json: Optional[Dict[str, Any]] = None
    final: str = ""
    id: str = field(default_factory=lambda: f"cv_{uuid.uuid4().hex[:12]}")
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if not self.final:
            self.final = resolve_final(self.model_verdict, self.rule_verdict, self.rule_decisive)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def record_verdict(repo: Any, verdict: CheckVerdict) -> CheckVerdict:
    """Validate and persist a verdict. In hosted demo mode the verdict is returned unpersisted."""
    if verdict.attempt > MAX_ATTEMPT:
        raise CheckLoopError(
            f"Check {verdict.check_id} attempted pass {verdict.attempt}; at most {MAX_ATTEMPT} retry is allowed."
        )
    if repo is not None and os.getenv("HOSTED_DEMO") != "1":
        repo.insert_check_verdict(verdict.to_dict())
    return verdict
