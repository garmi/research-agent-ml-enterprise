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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Gate1Approval:
        return cls(
            schema_version=int(data["schema_version"]),
            gate=str(data["gate"]),
            question_id=str(data["question_id"]),
            question_text=str(data["question_text"]),
            question_sha256=str(data["question_sha256"]),
            framing_id=str(data["framing_id"]),
            framing_title=str(data["framing_title"]),
            framing_question=str(data["framing_question"]),
            approved_by=str(data["approved_by"]),
            approved_at=str(data["approved_at"]),
            version=int(data["version"]),
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


def save_gate1_approval(
    question_id: str,
    question_text: str,
    framing_id: str,
    framing_title: str,
    framing_question: str,
    approved_by: Optional[str] = None,
    approvals_dir: Optional[str | Path] = None,
) -> Gate1Approval:
    """Save an immutable Gate 1 problem framing approval record.

    Writes to `<approvals_dir>/<question_id>/gate1-v<N>.json`.
    If an approval already exists, increments version to N+1, keeping earlier files intact.
    """
    target_dir = _get_question_approvals_dir(question_id, approvals_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    existing_files = list_gate1_approval_files(question_id, approvals_dir)
    next_version = 1
    if existing_files:
        m = re.search(r"gate1-v(\d+)\.json$", existing_files[-1].name)
        if m:
            next_version = int(m.group(1)) + 1

    sha256_hash = compute_question_sha256(question_text)
    approved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    actual_approver = approved_by or get_default_research_user()

    approval = Gate1Approval(
        schema_version=1,
        gate="problem",
        question_id=question_id,
        question_text=question_text,
        question_sha256=sha256_hash,
        framing_id=framing_id,
        framing_title=framing_title,
        framing_question=framing_question,
        approved_by=actual_approver,
        approved_at=approved_at,
        version=next_version,
    )

    out_file = target_dir / f"gate1-v{next_version}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(approval.to_dict(), f, indent=2)

    return approval
