from __future__ import annotations

import os
import time
from typing import Optional

import requests

from src.llm.model_names import gemini_model_name


class GeminiClient:
    """Minimal Gemini REST client (Google AI Studio key). Same interface as OllamaClient."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None, retries: int = 2, timeout: int = 120):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env (AI Studio key).")
        raw_model = model or gemini_model_name()
        self.model = str(raw_model).strip()
        self.retries = retries
        self.timeout = timeout
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        json_mode: bool = False,
    ) -> str:
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"

        import re

        clean_model = self.model.strip()
        url = f"{self.base_url}/{clean_model}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                response = requests.post(url, json=body, headers=headers, timeout=self.timeout)
                if response.status_code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                if not response.ok:
                    err_text = response.text
                    err_clean = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[REDACTED_KEY]", err_text)
                    raise requests.HTTPError(f"HTTP {response.status_code} ({response.reason}): {err_clean}", response=response)
                data = response.json()
                parts = data["candidates"][0]["content"]["parts"]
                return "".join(part.get("text", "") for part in parts)
            except Exception as exc:
                last_exc = exc
                time.sleep(2 ** attempt)
        if last_exc:
            raise last_exc
        raise RuntimeError("Gemini request failed: unknown error.")
