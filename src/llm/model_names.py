"""Which Gemini model the app uses: GEMINI_MODEL when set, else config.yaml's gemini.model, else the default."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


def gemini_model_name(config: Optional[Dict[str, Any]] = None) -> str:
    if config is None:
        from src.config import load_config

        try:
            config = load_config() or {}
        except Exception:  # a missing or unreadable config falls back to the default
            config = {}
    raw = os.getenv("GEMINI_MODEL") or (config.get("gemini") or {}).get("model") or DEFAULT_GEMINI_MODEL
    return str(raw).strip()
