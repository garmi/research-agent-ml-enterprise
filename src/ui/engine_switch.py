"""S29d: when Gemini's limit is reached, switch to Ollama on this machine and keep going.

The hosted app cannot reach Ollama on your Mac, so the fallback is the same app run locally (scripts/run_local.sh).
Local runs are labelled honestly: the local model judges Check D less reliably than Gemini.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Mapping, Optional

LOCAL_COMMAND = "./scripts/run_local.sh"


def ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct").strip() or "qwen2.5:3b-instruct"


def ollama_label() -> str:
    return f"Local Ollama ({ollama_model()}) (on this machine) [Active]"


def quota_hit(results: Optional[Dict[str, Any]], state: Mapping[str, Any]) -> bool:
    """The run's model step, or the reasoning step in this session, hit Gemini's limit."""
    return bool(state.get("gemini_quota_hit")) or \
        ((results or {}).get("error_details") or {}).get("error_class") == "GeminiQuotaExceeded"


def switch_offer(ollama_ok: bool) -> Dict[str, str]:
    if ollama_ok:
        return {"action": "switch", "text": "Gemini's limit is reached. Ollama is running on this machine: switch to it "
                                             "and keep going (slower, and its checks are less reliable)."}
    return {"action": "local",
            "text": "Gemini's limit is reached, and Ollama can't be reached from here (the hosted app can't see your "
                    f"Mac). To keep going, start the app on your Mac with `{LOCAL_COMMAND}` (it starts Ollama's model "
                    "and opens the app at http://localhost:8501), or try Gemini again later."}


def engine_line(results: Dict[str, Any]) -> str:
    eng = results.get("engine") or {}
    provider, model = str(eng.get("provider") or "").lower(), str(eng.get("model") or "")
    if provider == "ollama":
        return f"Engine: Ollama ({model}), local"
    if provider == "gemini":
        return f"Engine: Gemini ({model})"
    return f"Engine: {provider}" if provider else ""


def check_d_engine_note(results: Dict[str, Any]) -> str:
    eng = results.get("engine") or {}
    if str(eng.get("provider") or "").lower() != "ollama":
        return ""
    return f"Checked by the local model ({eng.get('model') or ollama_model()}): less reliable than Gemini."
