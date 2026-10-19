from __future__ import annotations

import os
from typing import Any, Dict

from src.llm.gemini_client import GeminiClient
from src.llm.ollama_client import OllamaClient


def build_llm(provider: str, config: Dict[str, Any]):
    """Return an LLM client. provider: 'ollama', 'gemini', or 'stub'."""
    p_clean = str(provider).strip().lower()
    if p_clean in ("stub", "fake", "mock"):
        from src.llm.stub_client import StubLLM
        return StubLLM()
    if p_clean == "gemini":
        cfg = config.get("gemini", {})
        raw_model = os.getenv("GEMINI_MODEL") or cfg.get("model", "gemini-2.5-flash")
        model = str(raw_model).strip()
        return GeminiClient(model=model)
    if p_clean in ("ollama", "local"):
        cfg = config.get("ollama", {})
        raw_ollama_model = os.getenv("OLLAMA_MODEL") or cfg.get("model", "qwen2.5:3b-instruct")
        raw_base_url = os.getenv("OLLAMA_BASE_URL") or cfg.get("base_url", "http://localhost:11434")
        return OllamaClient(
            base_url=str(raw_base_url).strip(),
            model=str(raw_ollama_model).strip(),
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX") or cfg.get("num_ctx", 4096)),
            timeout=int(cfg.get("timeout_seconds", 180)),
        )
    raise ValueError(f"Unsupported LLM provider: '{provider}'. Supported providers: 'ollama', 'gemini', 'stub'.")

