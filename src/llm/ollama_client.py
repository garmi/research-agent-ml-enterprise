from __future__ import annotations

import os
import time
from typing import Optional

import requests


class OllamaClient:
    """Local Ollama client. Sized for 8 GB Apple Silicon (small model, bounded context)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        num_ctx: Optional[int] = None,
        timeout: int = 180,
        retries: int = 2,
    ):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
        self.num_ctx = num_ctx or int(os.getenv("OLLAMA_NUM_CTX", "4096"))
        self.timeout = timeout
        self.retries = retries

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        json_mode: bool = False,
    ) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": self.num_ctx},
        }
        if system_prompt:
            payload["system"] = system_prompt
        if json_mode:
            payload["format"] = "json"

        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                response = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=self.timeout)
                if not response.ok:
                    error_msg = response.text
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("error", response.text)
                    except Exception:
                        pass
                    raise RuntimeError(f"Ollama error {response.status_code}: {error_msg}")
                return response.json().get("response", "")
            except Exception as exc:
                last_exc = exc
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Ollama request failed after retries: {last_exc}")
