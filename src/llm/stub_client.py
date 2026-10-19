from __future__ import annotations

import json
from typing import Any, Optional


class StubLLM:
    """Deterministic stub LLM for offline tests and fast UI validation.
    
    Returns structured empty/minimal responses without fabricated findings,
    metrics, or canned conclusions (enforcing A1 integrity).
    """

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        json_mode: bool = False,
    ) -> str:
        prompt_lower = prompt.lower()
        if "you are check a" in prompt_lower:
            # The stub cannot judge relevance: abstain so the rules decide.
            return json.dumps({"verdicts": []})
        if "compact summaries of research papers" in prompt_lower:
            return json.dumps({
                "executive_summary": "",
                "objective": "",
                "key_findings": [],
                "themes": [],
                "business_problems": [],
                "research_gaps": [],
            })
        if "actionable recommendations" in prompt_lower:
            return json.dumps({
                "recommendations": []
            })
        if "execution roadmap" in prompt_lower:
            return json.dumps({
                "strategic_roadmap": []
            })
        if "linkedin" in prompt_lower or "content" in prompt_lower:
            return json.dumps({
                "content_ideas": []
            })
        # Default paper analysis map extraction
        return json.dumps({
            "problem_statement": [],
            "key_findings": "",
            "business_relevance": "",
            "confidence_score": 0.0,
        })
