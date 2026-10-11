from __future__ import annotations

import os
import time
from typing import Optional

import requests


class GeminiClient:
    """Minimal Gemini REST client (Google AI Studio key). Same interface as OllamaClient."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None, retries: int = 2, timeout: int = 120):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env (AI Studio key).")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
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

        url = f"{self.base_url}/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

        last_exc: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                response = requests.post(url, json=body, headers=headers, timeout=self.timeout)
                if response.status_code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                response.raise_for_status()
                data = response.json()
                parts = data["candidates"][0]["content"]["parts"]
                return "".join(part.get("text", "") for part in parts)
            except (requests.RequestException, KeyError, IndexError) as exc:
                last_exc = exc
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Gemini request failed after retries: {last_exc}")
