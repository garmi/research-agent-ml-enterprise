from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List


class SynthesisEngine:
    """Simple synthesis layer that defends against irregular LLM output."""

    def __init__(self, llm_client: Any):
        self.llm_client = llm_client

    def _extract_json_block(self, text: str) -> Dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            candidate = match.group(0)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}

    def analyze(self, topic: str, papers: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        paper_list = list(papers)
        if not paper_list:
            return self.empty_output(topic)

        prompt = (
            "You are a research strategist and business analyst. "
            "Based on the following papers, generate a structured, strategic synthesis. "
            "Return only valid JSON.\n\n"
            f"Topic: {topic}\n\n"
            f"Papers: {json.dumps(paper_list, ensure_ascii=False, indent=2)}"
        )

        response = self.llm_client.generate(
            prompt,
            system_prompt=(
                "You produce concise, executive-grade academic and business analysis. "
                "Use valid JSON only."
            ),
            temperature=0.2,
        )

        parsed = self._extract_json_block(response)
        if not parsed:
            return self.empty_output(topic)

        synthesis = {
            "topic": topic,
            "executive_summary": parsed.get("executive_summary", "No executive summary available."),
            "objective": parsed.get("objective", f"Assess research and market signals for {topic}"),
            "research_questions": parsed.get("research_questions", [
                "What are the dominant research themes?",
                "What market and business problems are emerging?",
                "What strategic roadmaps should leaders prioritize?",
            ]),
            "sources": ["arXiv", "Semantic Scholar", "Crossref"],
            "time_window": "2019-2025",
            "papers": paper_list,
            "key_findings": parsed.get("key_findings", ["No key findings extracted."]),
            "themes": parsed.get("themes", [{"name": "Strategic theme", "description": "No theme extracted."}]),
            "market_trends": parsed.get("market_trends", ["No market trends identified."]),
            "business_problems": parsed.get("business_problems", ["No business problems identified."]),
            "research_gaps": parsed.get("research_gaps", ["No research gaps identified."]),
            "recommendations": parsed.get("recommendations", ["No recommendations extracted."]),
            "strategic_roadmap": parsed.get("strategic_roadmap", [{
                "stage": "0-6 months",
                "objective": "Initial assessment and capability building",
                "actions": ["Define strategic hypothesis", "Benchmark existing capability"],
                "kpis": ["Capability baseline", "Initial roadmap alignment"],
            }]),
            "content_ideas": parsed.get("content_ideas", ["LinkedIn research brief", "Article draft", "Executive memo"]),
            "references": parsed.get("references", [paper.get("title", "") for paper in paper_list]),
        }
        return synthesis

    @staticmethod
    def empty_output(topic: str) -> Dict[str, Any]:
        return {
            "topic": topic,
            "executive_summary": "No synthesis available from model output.",
            "objective": f"Assess research and market signals for {topic}",
            "research_questions": [
                "What are the dominant themes?",
                "What business problems and gaps appear?",
                "What roadmap should leaders prioritize?",
            ],
            "sources": ["arXiv", "Semantic Scholar", "Crossref"],
            "time_window": "2019-2025",
            "papers": [],
            "key_findings": ["Model output was empty."],
            "themes": [{"name": "Default theme", "description": "The synthesis model did not return structured output."}],
            "market_trends": ["No data extracted."],
            "business_problems": ["No data extracted."],
            "research_gaps": ["No data extracted."],
            "recommendations": ["No data extracted."],
            "strategic_roadmap": [{
                "stage": "0-6 months",
                "objective": "Initial research and validation",
                "actions": ["Run the workflow again with a more focused topic"],
                "kpis": ["Research retrieval success"],
            }],
            "content_ideas": ["LinkedIn brief", "Theme-based article"],
            "references": [],
        }
