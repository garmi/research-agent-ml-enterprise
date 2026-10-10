from __future__ import annotations

import os
from typing import Any, Dict

from src.llm.gemini_client import GeminiClient
from src.llm.ollama_client import OllamaClient


def build_llm(provider: str, config: Dict[str, Any]):
    """Return an LLM client. provider: 'ollama' or 'gemini'."""
    if provider == "gemini":
        cfg = config.get("gemini", {})
        model = os.getenv("GEMINI_MODEL") or cfg.get("model", "gemini-2.5-flash")
        return GeminiClient(model=model)
    cfg = config.get("ollama", {})
    return OllamaClient(
        base_url=os.getenv("OLLAMA_BASE_URL") or cfg.get("base_url"),
        model=os.getenv("OLLAMA_MODEL") or cfg.get("model"),
        num_ctx=int(os.getenv("OLLAMA_NUM_CTX") or cfg.get("num_ctx", 4096)),
        timeout=int(cfg.get("timeout_seconds", 180)),
    )
