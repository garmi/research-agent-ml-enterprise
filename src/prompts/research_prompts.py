from __future__ import annotations

import json
import re
from typing import Any, Dict, List


class ResearchPromptLibrary:
    """Prompt templates used by the research synthesis workflow."""

    @staticmethod
    def paper_analysis(topic: str, paper: Dict[str, Any]) -> str:
        return f"""
You are a research analyst and strategy consultant.

Evaluate the following paper for the topic: {topic}

Paper metadata:
{json.dumps(paper, ensure_ascii=False, indent=2)}

Return valid JSON with these keys:
- title
- year
- source
- problem_statement
- key_findings
- research_method
- limitations
- business_relevance
- engineering_relevance
- gap_identified
- strategic_opportunity
- adoption_barrier
- confidence_score

Keep values concise but actionable.
"""

    @staticmethod
    def synthesis(topic: str, papers: List[Dict[str, Any]]) -> str:
        return f"""
You are a technology strategy researcher. Synthesize the following research papers for the topic: {topic}

Your task:
1. Identify the most important themes.
2. Summarize market trends and technology movements.
3. Identify business problems, operational bottlenecks, and adoption risks.
4. Highlight research and practice gaps.
5. Propose strategic recommendations and a roadmap for enterprise leaders.
6. Recommend content ideas for professional sharing.

Return valid JSON with this structure:
{
  "executive_summary": "...",
  "objective": "...",
  "research_questions": ["..."],
  "key_findings": ["..."],
  "themes": [
    {"name": "...", "description": "..."}
  ],
  "market_trends": ["..."],
  "business_problems": ["..."],
  "research_gaps": ["..."],
  "recommendations": ["..."],
  "strategic_roadmap": [
    {"stage": "0-6 months", "objective": "...", "actions": ["..."], "kpis": ["..."]}
  ],
  "content_ideas": ["..."],
  "references": ["..."]
}

Papers:
{json.dumps(papers, ensure_ascii=False, indent=2)}
"""
