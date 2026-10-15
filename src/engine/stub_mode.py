"""Stub mode detection and enforcement.

Ensures stub mode can only be activated via STUB_LLM=1, is strictly
disabled if HOSTED_DEMO is active, and cannot be activated via query parameters.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional


def is_stub_mode(env: Optional[Mapping[str, str]] = None) -> bool:
    """Return True if stub mode is enabled via environment variable.

    Stub mode is enabled ONLY when STUB_LLM=1 (or 'true').
    STUB_LLM is strictly ignored if HOSTED_DEMO is active (1 or 'true').
    """
    target_env = os.environ if env is None else env

    hosted_demo = target_env.get("HOSTED_DEMO", "").strip().lower()
    if hosted_demo in ("1", "true", "yes", "on"):
        return False

    stub_llm = target_env.get("STUB_LLM", "").strip().lower()
    return stub_llm in ("1", "true", "yes", "on")
