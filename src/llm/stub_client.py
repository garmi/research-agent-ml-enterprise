from __future__ import annotations

import json
from typing import Any, Optional


class StubLLM:
    """Deterministic stub LLM for offline tests and fast UI validation."""

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        json_mode: bool = False,
    ) -> str:
        prompt_lower = prompt.lower()
        if "compact summaries of research papers" in prompt_lower:
            return json.dumps({
                "executive_summary": "Empirical analysis across peer-reviewed repositories confirms that agentic automation accelerates software delivery by 32% while introducing bounded governance requirements.",
                "objective": "Assess enterprise impact of agentic workflows",
                "key_findings": [
                    "Empirical velocity increases by 32% across standard delivery tasks [P1].",
                    "Bounded autonomy contracts prevent out-of-band regression risks [P2].",
                    "Platform engineering teams report higher DevEx satisfaction scores [P1].",
                ],
                "themes": [
                    {
                        "name": "Autonomous Governance",
                        "description": "Deterministic contracts and gates governing multi-agent handoffs in production pipelines.",
                    }
                ],
                "business_problems": [
                    "Unverified extrapolation in production pipelines leads to silent architectural drift.",
                    "Lack of centralized audit logging hampers compliance in regulated sectors.",
                ],
                "research_gaps": [
                    "Longitudinal impact on junior engineer skill acquisition remains under-evaluated across empirical cohorts.",
                ],
            })
        if "actionable recommendations" in prompt_lower:
            return json.dumps({
                "recommendations": [
                    {
                        "action": "Deploy deterministic verification gates for all agentic pull requests",
                        "owner": "VP Engineering",
                        "why": "Eliminates silent regression and verifies invariant contracts.",
                        "evidence": ["P1"],
                    },
                    {
                        "action": "Establish bounded autonomy boundaries for automated code generators",
                        "owner": "Platform Architect",
                        "why": "Maintains architectural consistency across microservices.",
                        "evidence": ["P2"],
                    },
                ]
            })
        if "execution roadmap" in prompt_lower:
            return json.dumps({
                "strategic_roadmap": [
                    {
                        "stage": "Phase 1 (Months 0–6)",
                        "objective": "Establish verification infrastructure and telemetry",
                        "actions": ["Instrument developer telemetry", "Deploy review gates"],
                        "kpis": ["Cycle time reduction: 20%", "Zero unverified regressions"],
                    },
                    {
                        "stage": "Phase 2 (Months 6–18)",
                        "objective": "Scale agentic workflows enterprise-wide",
                        "actions": ["Rollout assistant tooling", "Codify architecture contracts"],
                        "kpis": ["Developer adoption > 80%", "Review latency < 2h"],
                    },
                ]
            })
        if "linkedin" in prompt_lower or "content" in prompt_lower:
            return json.dumps({
                "content_ideas": [
                    "Why agentic software delivery requires bounded autonomy contracts.",
                    "3 ways platform engineering teams are measuring generative assistant ROI.",
                ]
            })
        # Default paper analysis map extraction
        return json.dumps({
            "problem_statement": ["Evaluation of agentic tools in enterprise software engineering."],
            "key_findings": "Empirical studies report 30% reduction in lead time with bounded guardrails.",
            "business_relevance": "Direct cost reduction and developer experience improvements.",
            "confidence_score": 0.85,
        })
