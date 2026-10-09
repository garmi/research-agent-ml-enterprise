from __future__ import annotations

import os
from typing import Optional

import requests


class OllamaClient:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

    def generate(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.3) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system_prompt:
            payload["system"] = system_prompt

        response = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=180)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "")
