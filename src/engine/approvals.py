"""Gate 1 Problem Framing Approval Recorder (Slice S1 Task 3).

Persists immutable, versioned JSON records of problem framing approvals to
`<approvals_dir>/<question_id>/gate1-v<N>.json`.
Re-approval never overwrites earlier approvals, incrementing to v<N+1>.
Environment variables:
- RESEARCH_APPROVALS_DIR: approvals directory (default ledger/approvals).
- RESEARCH_USER: identity of approver (default local-user).
"""

from __future__ import annotations

import datetime
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.engine.ids import compute_question_sha256

DEFAULT_APPROVALS_DIR = "ledger/approvals"
DEFAULT_RESEARCH_USER = "local-user"


def get_approvals_dir() -> Path:
    return Path(os.getenv("RESEARCH_APPROVALS_DIR", DEFAULT_APPROVALS_DIR))


def get_default_research_user() -> str:
    return os.getenv("RESEARCH_USER", DEFAULT_RESEARCH_USER)


@dataclass
class Gate1Approval:
    schema_version: int
    gate: str
    question_id: str
    question_text: str
    question_sha256: str
    framing_id: str
    framing_title: str
    framing_question: str
    approved_by: str
    approved_at: str
    version: int
    raw_user_text: str = ""
    proposals: List[Dict[str, Any]] = None
    final_package: Dict[str, Any] = None
    package_sha256: str = ""
    provider: str = ""
    model_name: str = ""
    prompt_file_hash: str = ""

    def __post_init__(self):
        if self.proposals is None:
            self.proposals = []
        if self.final_package is None:
            self.final_package = {}

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Gate1Approval:
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            gate=str(data.get("gate", "problem")),
            question_id=str(data.get("question_id", "")),
            question_text=str(data.get("question_text", "")),
            question_sha256=str(data.get("question_sha256", "")),
            framing_id=str(data.get("framing_id", "lens_empirical_effect")),
            framing_title=str(data.get("framing_title", "Empirical effect")),
            framing_question=str(data.get("framing_question", data.get("question_text", ""))),
            approved_by=str(data.get("approved_by", DEFAULT_RESEARCH_USER)),
            approved_at=str(data.get("approved_at", "")),
            version=int(data.get("version", 1)),
            raw_user_text=str(data.get("raw_user_text", "")),
            proposals=data.get("proposals") or [],
            final_package=data.get("final_package") or {},
            package_sha256=str(data.get("package_sha256", "")),
            provider=str(data.get("provider", "")),
            model_name=str(data.get("model_name", "")),
            prompt_file_hash=str(data.get("prompt_file_hash", "")),
        )


def _get_question_approvals_dir(question_id: str, approvals_dir: Optional[str | Path] = None) -> Path:
    base = Path(approvals_dir or get_approvals_dir())
    return base / question_id


def list_gate1_approval_files(question_id: str, approvals_dir: Optional[str | Path] = None) -> List[Path]:
    target_dir = _get_question_approvals_dir(question_id, approvals_dir)
    if not target_dir.is_dir():
        return []
    files = list(target_dir.glob("gate1-v*.json"))

    def _extract_v(p: Path) -> int:
        m = re.search(r"gate1-v(\d+)\.json$", p.name)
        return int(m.group(1)) if m else 0

    return sorted(files, key=_extract_v)


def get_latest_gate1_approval(question_id: str, approvals_dir: Optional[str | Path] = None) -> Optional[Gate1Approval]:
    """Retrieve the highest-version Gate 1 approval record for a question, or None."""
    files = list_gate1_approval_files(question_id, approvals_dir)
    if not files:
        return None
    latest_file = files[-1]
    with open(latest_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Gate1Approval.from_dict(data)


def is_package_approved(question_id: str, package: Dict[str, Any], approvals_dir: Optional[str | Path] = None) -> bool:
    """Return True if the exact package matches the latest approved package_sha256."""
    from src.engine.reasoner import compute_package_sha256
    latest = get_latest_gate1_approval(question_id, approvals_dir=approvals_dir)
    if not latest:
        return False
    current_hash = compute_package_sha256(package)
    if latest.package_sha256:
        return latest.package_sha256 == current_hash
    # Backward-compatible check on question text
    return latest.question_sha256 == compute_question_sha256(package.get("refined_question", ""))


def save_gate1_approval(
    question_id: str,
    question_text: Optional[str] = None,
    framing_id: str = "lens_empirical_effect",
    framing_title: str = "Empirical effect",
    framing_question: Optional[str] = None,
    approved_by: Optional[str] = None,
    approvals_dir: Optional[str | Path] = None,
    raw_user_text: Optional[str] = None,
    proposals: Optional[List[Dict[str, Any]]] = None,
    final_package: Optional[Dict[str, Any]] = None,
    provider: str = "",
    model_name: str = "",
    prompt_file_hash: str = "",
) -> Gate1Approval:
    """Save an immutable Gate 1 problem framing approval record (S1 + S2 extended).

    Writes to `<approvals_dir>/<question_id>/gate1-v<N>.json`.
    If an approval already exists, increments version to N+1, keeping earlier files intact.
    """
    from src.engine.reasoner import compute_package_sha256

    target_dir = _get_question_approvals_dir(question_id, approvals_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    existing_files = list_gate1_approval_files(question_id, approvals_dir)
    next_version = 1
    if existing_files:
        m = re.search(r"gate1-v(\d+)\.json$", existing_files[-1].name)
        if m:
            next_version = int(m.group(1)) + 1

    # Resolve package and text
    pkg = final_package or {}
    effective_question_text = (
        question_text
        or pkg.get("refined_question")
        or framing_question
        or ""
    )
    effective_raw_user = raw_user_text or effective_question_text
    package_hash = compute_package_sha256(pkg) if pkg else ""
    question_hash = compute_question_sha256(effective_question_text)

    approved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    actual_approver = approved_by or get_default_research_user()

    approval = Gate1Approval(
        schema_version=2 if pkg else 1,
        gate="problem",
        question_id=question_id,
        question_text=effective_question_text,
        question_sha256=question_hash,
        framing_id=framing_id,
        framing_title=framing_title,
        framing_question=effective_question_text,
        approved_by=actual_approver,
        approved_at=approved_at,
        version=next_version,
        raw_user_text=effective_raw_user,
        proposals=proposals or ([pkg] if pkg else []),
        final_package=pkg,
        package_sha256=package_hash,
        provider=provider,
        model_name=model_name,
        prompt_file_hash=prompt_file_hash,
    )

    out_file = target_dir / f"gate1-v{next_version}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(approval.to_dict(), f, indent=2)

    return approval
