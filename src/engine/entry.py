"""Single entry point for executing research runs (Slice S1 Task 4).

Guarantees that no run can execute without a verified, un-mutated Gate 1
problem framing approval. Both the primary 'Run Research' action and the
'Re-synthesize' action must route strictly through `start_run`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from src.engine.approvals import get_latest_gate1_approval
from src.engine.ids import compute_question_sha256

logger = logging.getLogger(__name__)


class GateApprovalError(Exception):
    """Raised when execution is refused due to a missing or invalidated Gate 1 approval."""
    pass


def start_run(
    question_id: str,
    question_text: str,
    *,
    runner: Optional[Callable[..., Any]] = None,
    approvals_dir: Optional[str | Path] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Single entry function to validate Gate 1 approval and trigger execution.

    Refuses execution with a plain-English GateApprovalError (no hashes in message) if:
      1. No Gate 1 approval record exists for question_id.
      2. The full 64-hex question_text sha256 no longer matches the approved framing hash.

    Otherwise, delegates to `runner` (or `multilane_runner.run_workflow` by default)
    passing all pipeline arguments.
    """
    approval = get_latest_gate1_approval(question_id, approvals_dir=approvals_dir)
    if approval is None:
        raise GateApprovalError(
            f"Run refused: Problem framing is not approved for question '{question_id}'. "
            "Please review and approve a framing before initiating research."
        )

    current_sha256 = compute_question_sha256(question_text)
    if current_sha256 != approval.question_sha256:
        logger.warning(
            "Gate 1 hash mismatch for '%s': approved=%s, current=%s",
            question_id,
            approval.question_sha256,
            current_sha256,
        )
        raise GateApprovalError(
            "Run refused: You changed the question after approving a framing. Approve a framing again to continue."
        )

    if runner is None:
        from src.analysis import multilane_runner
        runner = multilane_runner.run_workflow

    run_args = dict(kwargs)
    if "topic" not in run_args:
        run_args["topic"] = question_text

    logger.info(
        "Gate 1 validated successfully for '%s' (v%d). Delegating to runner.",
        question_id,
        approval.version,
    )
    return runner(**run_args)
