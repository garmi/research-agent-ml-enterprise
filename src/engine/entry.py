"""Single entry point for executing research runs (Slice S1 Task 4).

Guarantees that no run can execute without a verified, un-mutated Gate 1
problem framing approval. Both the primary 'Run Research' action and the
'Re-synthesize' action must route strictly through `start_run`.
"""

from __future__ import annotations

import inspect
import logging
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable, Dict, Optional

from src.engine.approvals import get_latest_gate1_approval
from src.engine.framings import get_lens_by_id
from src.engine.ids import compute_question_sha256
from src.engine.stub_mode import is_stub_mode

logger = logging.getLogger(__name__)


def _filter_runner_args(runner_fn: Callable[..., Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """Filter args so legacy runners lacking **kwargs do not receive unknown arguments."""
    try:
        sig = inspect.signature(runner_fn)
        for param in sig.parameters.values():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                return args
        return {k: v for k, v in args.items() if k in sig.parameters}
    except Exception:
        return args


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
            "Run refused: Problem framing is not approved. "
            "Please review and approve a framing before initiating research."
        )

    reasoned_pkg = kwargs.get("reasoned_package")
    if reasoned_pkg:
        from src.engine.approvals import is_package_approved
        if not is_package_approved(question_id, reasoned_pkg, approvals_dir=approvals_dir):
            raise GateApprovalError(
                "Run refused: You changed the proposal after approving. Approve again to continue."
            )
    else:
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

    run_args = dict(kwargs)
    if reasoned_pkg:
        run_args["topic"] = reasoned_pkg.get("refined_question", question_text)
        run_args["reasoned_package"] = reasoned_pkg
    elif "topic" not in run_args:
        run_args["topic"] = question_text
    run_args.setdefault("framing_id", approval.framing_id)
    lens = get_lens_by_id(approval.framing_id)
    if lens:
        run_args.setdefault("framing_lens", lens.to_dict())

    logger.info(
        "Gate 1 validated successfully for '%s' (v%d). Delegating to runner.",
        question_id,
        approval.version,
    )

    if is_stub_mode():
        with tempfile.TemporaryDirectory() as tmp_stub_dir:
            temp_db = os.path.join(tmp_stub_dir, "stub_ledger.db")
            temp_prac_db = os.path.join(tmp_stub_dir, "stub_practitioner.db")
            if os.path.exists("ledger/ledger.db"):
                shutil.copy("ledger/ledger.db", temp_db)
            if os.path.exists("ledger/practitioner.db"):
                shutil.copy("ledger/practitioner.db", temp_prac_db)

            if runner is None:
                from src.analysis.multilane_runner import MultiLaneResearchRunner
                stub_instance = MultiLaneResearchRunner(
                    db_path=temp_db,
                    practitioner_db_path=temp_prac_db,
                )
                actual_runner = stub_instance.run_workflow
            elif hasattr(runner, "__self__") and getattr(runner.__self__, "db_path", None) == "ledger/ledger.db":
                from src.analysis.multilane_runner import MultiLaneResearchRunner
                stub_instance = MultiLaneResearchRunner(
                    db_path=temp_db,
                    practitioner_db_path=temp_prac_db,
                )
                actual_runner = stub_instance.run_workflow
            else:
                actual_runner = runner

            filtered_args = _filter_runner_args(actual_runner, run_args)
            result = actual_runner(**filtered_args)

        if not isinstance(result, dict):
            raise TypeError(
                f"Runner in stub mode must return a dict, got {type(result).__name__}"
            )

        result["is_stub_mode"] = True
        result["can_publish"] = False
        result["publishable"] = False
        result["status"] = "NOT_PUBLISHABLE"
        result["stub_marker"] = "TEST MODE: synthetic data. Results are not real and cannot be published."
        if "quality_scorecard" in result and isinstance(result["quality_scorecard"], dict):
            result["quality_scorecard"]["band"] = "NOT_PUBLISHABLE"
        return result

    if runner is None:
        from src.analysis.multilane_runner import MultiLaneResearchRunner
        default_instance = MultiLaneResearchRunner()
        runner = default_instance.run_workflow

    filtered_args = _filter_runner_args(runner, run_args)
    return runner(**filtered_args)

