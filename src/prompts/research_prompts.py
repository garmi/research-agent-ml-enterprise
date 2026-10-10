from __future__ import annotations

import json
import re
from typing import Any, Dict, List


class ResearchPromptLibrary:
    """Prompt templates used by the research synthesis workflow."""

    @staticmethod
    def paper_analysis(topic: str, paper: Dict[str, Any]) -> str:
        slim = {
            "title": paper.get("title"),
            "year": paper.get("year"),
            "source": paper.get("source"),
            "abstract": (paper.get("abstract") or "")[:1800],
        }
        return f"""
You are a research analyst and strategy consultant.

Evaluate the following paper for the topic: {topic}

Paper metadata:
{json.dumps(slim, ensure_ascii=False, indent=2)}

Return valid JSON with these keys (all string values except confidence_score, a number 0-1):
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

Rules: use only what the abstract supports. If something is not stated, write "not stated".
Keep values concise but actionable.
"""

    TONE_INSTRUCTIONS = {
        "executive": "Tone: Executive & Board-Level. Focus on strategic enterprise risk, financial ROI, organizational readiness, governance, and business impact. Use authoritative, C-suite aligned prose.",
        "engineering": "Tone: Engineering Leadership & Architecture. Focus on technical architecture, platform engineering, DevSecOps pipelines, code quality, developer experience, and technical metrics.",
        "thought_leadership": "Tone: Visionary Thought Leadership. Focus on emerging paradigms, mental model shifts, counter-intuitive industry insights, and provocative perspectives for LinkedIn and peer communities.",
    }

    LENGTH_INSTRUCTIONS = {
        "concise": "Length & Density: Concise Executive Memo. Deliver high signal-to-noise ratio. Use tight, punchy bullet points and 1-2 sentence paragraphs. Maximum brevity without sacrificing empirical citations.",
        "detailed": "Length & Density: Comprehensive In-Depth Strategy Document. Provide thorough, multi-sentence elaborations of mechanisms, architectural trade-offs, organizational dependencies, and deep execution steps.",
    }

    # ---- Staged reduce prompts (small, focused tasks suit small local models) ----

    @classmethod
    def analysis(cls, topic: str, compact: List[Dict[str, Any]], tone: str = "executive", length: str = "detailed") -> str:
        tone_guide = cls.TONE_INSTRUCTIONS.get(tone, cls.TONE_INSTRUCTIONS["executive"])
        length_guide = cls.LENGTH_INSTRUCTIONS.get(length, cls.LENGTH_INSTRUCTIONS["detailed"])
        return f"""
You are a technology strategy analyst. Topic: {topic}

{tone_guide}
{length_guide}

Below are compact summaries of research papers, each with an id like P1.
Analyse them and return valid JSON with exactly these keys:
{{
  "executive_summary": "Summary for a busy executive: what the research says and why it matters",
  "objective": "one sentence",
  "research_questions": ["3 questions the evidence helps answer"],
  "key_findings": ["4-6 complete descriptive findings, each followed by supporting paper ids, e.g. Deployment frequency increased significantly under automated testing frameworks [P1][P3]"],
  "themes": [{{"name": "Theme Name", "description": "Complete description of the theme [P2]"}}],
  "market_trends": ["3-4 complete descriptive market trend statements, each citing paper ids"],
  "business_problems": ["3-5 complete descriptive problem statements explaining what goes wrong in the enterprise, each citing paper ids"],
  "research_gaps": ["3-4 complete descriptive gap statements explaining what the papers do NOT answer, each citing paper ids"]
}}

Rules:
- IMPORTANT: Every item in key_findings, market_trends, business_problems, and research_gaps MUST be a full descriptive statement, NOT just a paper ID like ['P1'].
- Use ONLY the provided summaries. Do not invent numbers, companies, or studies.
- Every finding, trend, and problem must cite at least one paper id in square brackets.
- If evidence on a point is thin, explicitly state that evidence is limited.

Paper summaries:
{json.dumps(compact, ensure_ascii=False, indent=1)}
"""

    @classmethod
    def recommendations(cls, topic: str, analysis: Dict[str, Any], compact: List[Dict[str, Any]], tone: str = "executive", length: str = "detailed") -> str:
        tone_guide = cls.TONE_INSTRUCTIONS.get(tone, cls.TONE_INSTRUCTIONS["executive"])
        length_guide = cls.LENGTH_INSTRUCTIONS.get(length, cls.LENGTH_INSTRUCTIONS["detailed"])
        brief = {
            "business_problems": analysis.get("business_problems", []),
            "research_gaps": analysis.get("research_gaps", []),
            "key_findings": analysis.get("key_findings", []),
        }
        return f"""
You advise engineering and technology leaders at large enterprises. Topic: {topic}

{tone_guide}
{length_guide}

Turn the research findings, business problems, and gaps into 4-6 concrete, actionable recommendations derived directly from the evidence.

Return valid JSON: {{"recommendations": [
  {{"action": "Action statement starting with an imperative verb", "owner": "Executive or Engineering Role", "why": "One sentence rationale tied to the findings/problems", "evidence": ["P1"]}}
]}}

Rules for each recommendation:
- "action" must start with an active verb and prescribe a concrete organizational or technical deliverable.
- "owner" must be a realistic enterprise role (CTO, VP Engineering, Head of Platform, Lead Enterprise Architect, Security Lead, Product VP).
- "why" must link directly to the problem, gap, or finding identified in the analysis.
- "evidence" lists the supporting paper ID(s) (e.g. ["P1", "P2"]).
- Ground recommendations strictly in the supplied analysis. Do NOT copy generic filler.
- FORBIDDEN actions: "conduct research", "invest in research", "develop a research agenda", "publish findings", "develop a paradigm shift", or vague placeholders like "improve", "consider", or "address" without a concrete deliverable.

Analysis:
{json.dumps(brief, ensure_ascii=False, indent=1)}

Paper ids available: {[c.get("paper_id") for c in compact]}
"""

    @classmethod
    def roadmap(cls, topic: str, recommendations: List[str], tone: str = "executive", length: str = "detailed") -> str:
        tone_guide = cls.TONE_INSTRUCTIONS.get(tone, cls.TONE_INSTRUCTIONS["executive"])
        length_guide = cls.LENGTH_INSTRUCTIONS.get(length, cls.LENGTH_INSTRUCTIONS["detailed"])
        return f"""
You are building an execution roadmap for enterprise leaders. Topic: {topic}

{tone_guide}
{length_guide}

Place the recommendations below into three distinct execution phases (0-6 months, 6-18 months, 18-36 months). Every action must come from one of the recommendations and represent concrete organizational execution.

Return valid JSON: {{"strategic_roadmap": [
  {{"stage": "0-6 months", "objective": "Foundation & Baseline", "actions": ["..."], "kpis": ["..."]}},
  {{"stage": "6-18 months", "objective": "Scale & Operationalize", "actions": ["..."], "kpis": ["..."]}},
  {{"stage": "18-36 months", "objective": "Optimize & Institutionalize", "actions": ["..."], "kpis": ["..."]}}
]}}

Rules:
- 3-4 actions per phase, each starting with an active verb and naming the owner role in brackets (e.g. "Deploy automated policy-as-code guardrails across CI/CD [Security Lead]").
- KPIs must be measurable metrics with a direction or target (e.g. "Deployment frequency", "Mean Time to Remediate (MTTR)", "Coverage %").
- FORBIDDEN: research agendas, publishing papers, or generic phrases like "completion of framework".

Recommendations:
{json.dumps(recommendations, ensure_ascii=False, indent=1)}
"""

    @classmethod
    def content_ideas(cls, topic: str, findings: List[str], tone: str = "thought_leadership") -> str:
        tone_guide = cls.TONE_INSTRUCTIONS.get(tone, cls.TONE_INSTRUCTIONS["thought_leadership"])
        return f"""
You help a technology leader build high-credibility thought leadership on LinkedIn. Topic: {topic}

{tone_guide}

Using the actual research findings below, write 3 punchy, data-grounded LinkedIn post opening hooks (1-2 sentences each).

Return valid JSON: {{"content_ideas": ["...", "...", "..."]}}

Rules:
- Ground each hook in specific findings, trade-offs, or metrics from the research.
- Sound like an experienced industry practitioner sharing hard-earned strategic insights.
- FORBIDDEN: Marketing hype, buzzwords, or clichés like "game-changer", "revolutionize", "unlock the full potential", "supercharge", "in today's fast-paced world". No hashtags.

Findings:
{json.dumps(findings, ensure_ascii=False, indent=1)}
"""

    @staticmethod
    def synthesis(topic: str, summaries: List[Dict[str, Any]]) -> str:

        schema = """{
  "executive_summary": "...",
  "objective": "...",
  "research_questions": ["..."],
  "key_findings": ["..."],
  "themes": [{"name": "...", "description": "..."}],
  "market_trends": ["..."],
  "business_problems": ["..."],
  "research_gaps": ["..."],
  "recommendations": ["..."],
  "strategic_roadmap": [
    {"stage": "0-6 months", "objective": "...", "actions": ["..."], "kpis": ["..."]},
    {"stage": "6-18 months", "objective": "...", "actions": ["..."], "kpis": ["..."]},
    {"stage": "18-36 months", "objective": "...", "actions": ["..."], "kpis": ["..."]}
  ],
  "content_ideas": ["..."],
  "references": ["..."]
}"""
        return f"""
You are a technology strategy researcher. Synthesize the structured paper summaries below for the topic: {topic}

Your task:
1. Identify the most important themes.
2. Summarize market trends and technology movements.
3. Identify business problems, operational bottlenecks, and adoption risks.
4. Highlight research and practice gaps.
5. Propose strategic recommendations and a roadmap for enterprise leaders.
6. Recommend content ideas for professional sharing.

Rules: ground every claim in the summaries; do not invent statistics; say so when evidence is thin.

Return valid JSON with exactly this structure:
{schema}

Paper summaries:
{json.dumps(summaries, ensure_ascii=False, indent=2)}
"""
