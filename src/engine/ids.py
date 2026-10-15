"""Question ID generation, normalization, and register-based resolution (Slice S1).

Rules:
- Question ID = slug of first 6 words + "-" + first 8 hex chars of sha256 of normalized text.
- Normalized text: lowercase, collapsed whitespace, trailing "?" removed.
- Deterministic: same text gives the same ID.
- Dynamic ID resolution queries questions/register.yaml (injectable path); no hardcoded canary tables.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

DEFAULT_REGISTER_PATH = "questions/register.yaml"


def normalize_question_text(text: str) -> str:
    """Normalize question text: lowercase, collapsed whitespace, trailing '?' removed."""
    cleaned = (text or "").strip()
    while cleaned.endswith("?"):
        cleaned = cleaned[:-1].strip()
    return " ".join(cleaned.lower().split())


def compute_question_sha256(text: str) -> str:
    """Return the full 64 hex characters of the SHA-256 digest of normalized text."""
    normalized = normalize_question_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_question_hash_suffix(text: str) -> str:
    """Return the first 8 hex characters of the SHA-256 digest of normalized text."""
    return compute_question_sha256(text)[:8]


compute_question_hash = compute_question_hash_suffix


def generate_question_id(text: str) -> str:
    """Generate deterministic question ID: slug of first 6 words + '-' + first 8 hex of sha256."""
    normalized = normalize_question_text(text)
    if not normalized:
        normalized = "unspecified question"

    tokens = [re.sub(r"[^a-z0-9]+", "", t) for t in normalized.split()]
    words = [t for t in tokens if t][:6]
    slug = "-".join(words) if words else "question"
    hash_suffix = compute_question_hash_suffix(text)
    return f"{slug}-{hash_suffix}"


def load_question_register(register_path: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    """Load question definitions from YAML register."""
    p = Path(register_path or os.getenv("RESEARCH_REGISTER_PATH", DEFAULT_REGISTER_PATH))
    if not p.is_file():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data.get("questions", [])
    except Exception:
        return []


def resolve_question_id(text_or_id: str, register_path: Optional[str | Path] = None) -> str:
    """Resolve a question text or identifier to its canonical question ID.

    Queries questions/register.yaml dynamically:
    1. If input matches an existing registered question ID, returns it.
    2. If input's normalized text matches a registered question's normalized text, returns its ID.
    3. Otherwise generates the standard slug + 8-hex ID.
    """
    stripped = (text_or_id or "").strip()
    if not stripped:
        return generate_question_id(stripped)

    registered_questions = load_question_register(register_path)
    # Check if directly passing registered question ID
    for q in registered_questions:
        if q.get("id") == stripped:
            return q["id"]

    # Check normalized text matching against registered questions
    normalized_input = normalize_question_text(stripped)
    for q in registered_questions:
        if normalize_question_text(q.get("text", "")) == normalized_input:
            return q["id"]

    return generate_question_id(stripped)
