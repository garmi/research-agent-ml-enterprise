from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Iterable, List, Optional

from pydantic import ValidationError

from src.prompts.research_prompts import ResearchPromptLibrary
from src.schemas import PaperSummary, ResearchSynthesisModel

MAP_SYSTEM = "You extract structured facts from research abstracts. Output valid JSON only."
REDUCE_SYSTEM = "You produce concise, executive-grade strategy analysis. Output valid JSON only."


class SynthesisEngine:
    """Map-reduce synthesis: per-paper extraction (map), then cross-paper synthesis (reduce)."""

    def __init__(self, map_llm: Any, reduce_llm: Optional[Any] = None, max_retries: int = 2,
                 on_progress: Optional[Callable[[str], None]] = None):
        self.map_llm = map_llm
        self.reduce_llm = reduce_llm or map_llm
        self.max_retries = max_retries
        self.on_progress = on_progress or (lambda msg: print(msg))

    # ---------- JSON helpers ----------
    @staticmethod
    def _extract_json_block(text: str) -> Dict[str, Any]:
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    def _call_json(self, llm: Any, prompt: str, system: str, temperature: float) -> Dict[str, Any]:
        for _ in range(self.max_retries + 1):
            raw = llm.generate(prompt, system_prompt=system, temperature=temperature, json_mode=True)
            parsed = self._extract_json_block(raw)
            if parsed:
                return parsed
        return {}

    # ---------- MAP ----------
    def summarize_paper(self, topic: str, paper: Dict[str, Any]) -> Optional[PaperSummary]:
        prompt = ResearchPromptLibrary.paper_analysis(topic, paper)
        parsed = self._call_json(self.map_llm, prompt, MAP_SYSTEM, temperature=0.1)
        if not parsed:
            return None
        parsed.setdefault("title", paper.get("title", ""))
        parsed.setdefault("year", paper.get("year"))
        parsed.setdefault("source", paper.get("source", ""))
        try:
            return PaperSummary(**parsed)
        except ValidationError:
            return None

    def map_papers(self, topic: str, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        total = len(papers)
        for idx, paper in enumerate(papers, start=1):
            self.on_progress(f"  [map {idx}/{total}] {str(paper.get('title', ''))[:70]}")
            summary = self.summarize_paper(topic, paper)
            if summary is None:
                self.on_progress("    ! extraction failed, skipping paper")
                continue
            item = summary.model_dump()
            item["paper_id"] = f"P{idx}"
            summaries.append(item)
        return summaries

    # ---------- REDUCE ----------
    def analyze(
        self,
        topic: str,
        papers: Iterable[Dict[str, Any]],
        tone: str = "executive",
        length: str = "detailed",
    ) -> Dict[str, Any]:
        paper_list = list(papers)
        if not paper_list:
            return self.empty_output(topic)

        summaries = self.map_papers(topic, paper_list)
        if not summaries:
            return self.empty_output(topic)

        compact = [self._compact(s) for s in summaries]
        valid_ids = {s["paper_id"] for s in summaries}

        # Stage A: findings, themes, problems, gaps
        self.on_progress(f"  [reduce 1/4] analysis of {len(summaries)} papers (tone: {tone}, length: {length})")
        analysis = self._call_json(
            self.reduce_llm,
            ResearchPromptLibrary.analysis(topic, compact, tone=tone, length=length),
            REDUCE_SYSTEM,
            temperature=0.2,
        )
        if not analysis:
            out = self.empty_output(topic)
            out["paper_summaries"] = summaries
            return out

        # Stage B: concrete recommendations
        self.on_progress(f"  [reduce 2/4] recommendations (tone: {tone})")
        rec_raw = self._call_json(
            self.reduce_llm,
            ResearchPromptLibrary.recommendations(topic, analysis, compact, tone=tone, length=length),
            REDUCE_SYSTEM,
            temperature=0.3,
        )
        recommendations = self._format_recommendations(rec_raw.get("recommendations", []))

        # Stage C: roadmap built only from the recommendations
        roadmap: List[Any] = []
        if recommendations:
            self.on_progress(f"  [reduce 3/4] roadmap (tone: {tone})")
            road_raw = self._call_json(
                self.reduce_llm,
                ResearchPromptLibrary.roadmap(topic, recommendations, tone=tone, length=length),
                REDUCE_SYSTEM,
                temperature=0.3,
            )
            roadmap = self._sanitize_roadmap(road_raw.get("strategic_roadmap", []))

        # Stage D: LinkedIn hooks from the findings
        self.on_progress("  [reduce 4/4] content ideas")
        ideas_raw = self._call_json(
            self.reduce_llm,
            ResearchPromptLibrary.content_ideas(topic, analysis.get("key_findings", []), tone=tone),
            REDUCE_SYSTEM,
            temperature=0.6,
        )

        try:
            model = ResearchSynthesisModel(
                executive_summary=analysis.get("executive_summary", ""),
                objective=analysis.get("objective", ""),
                research_questions=self._as_str_list(analysis.get("research_questions")),
                key_findings=self._as_str_list(analysis.get("key_findings")),
                themes=analysis.get("themes") or [],
                market_trends=self._as_str_list(analysis.get("market_trends")),
                business_problems=self._as_str_list(analysis.get("business_problems")),
                research_gaps=self._as_str_list(analysis.get("research_gaps")),
                recommendations=recommendations,
                strategic_roadmap=roadmap or [],
                content_ideas=self._as_str_list(ideas_raw.get("content_ideas")),
            )
        except ValidationError:
            out = self.empty_output(topic)
            out["paper_summaries"] = summaries
            return out

        data = model.to_dict()
        data["topic"] = topic
        data["objective"] = data["objective"] or f"Assess research and market signals for {topic}"
        data["sources"] = sorted({p.get("source", "") for p in paper_list if p.get("source")})
        data["time_window"] = self._time_window(paper_list)
        data["papers"] = paper_list
        data["paper_summaries"] = summaries
        data["references"] = [
            f"[P{i}] {p.get('title', '')} ({p.get('year', 'n/a')}) {p.get('url') or p.get('link') or ''}".strip()
            for i, p in enumerate(paper_list, start=1)
        ]
        data["citation_check"] = self._check_citations(data, valid_ids)
        return data

    # ---------- helpers ----------
    @staticmethod
    def _compact(summary: Dict[str, Any], limit: int = 600) -> Dict[str, Any]:
        """Keep reduce prompts compact without cutting sentences mid-clause."""
        keys = ["problem_statement", "key_findings", "business_relevance",
                "gap_identified", "adoption_barrier", "limitations"]
        out: Dict[str, Any] = {"paper_id": summary["paper_id"], "title": str(summary.get("title", ""))[:180]}
        for key in keys:
            val = str(summary.get(key, "")).strip()
            if len(val) > limit:
                cut = val[:limit]
                last_period = cut.rfind(".")
                if last_period > limit // 2:
                    val = cut[: last_period + 1]
                else:
                    val = cut.rsplit(" ", 1)[0] + "."
            out[key] = val
        return out

    @staticmethod
    def _as_str_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        items: List[str] = []
        for item in value:
            if isinstance(item, dict):
                items.append(" - ".join(str(v) for v in item.values() if v))
            elif item:
                items.append(str(item))
        return items

    @staticmethod
    def _sanitize_roadmap(raw: Any) -> List[Dict[str, Any]]:
        phases: List[Dict[str, Any]] = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            phases.append({
                "stage": str(item.get("stage", "")),
                "objective": str(item.get("objective", "")),
                "actions": SynthesisEngine._as_str_list(item.get("actions")),
                "kpis": SynthesisEngine._as_str_list(item.get("kpis")),
            })
        return phases

    @staticmethod
    def _format_recommendations(raw: Any) -> List[str]:
        """Turn {action, owner, why, evidence} objects into readable one-liners."""
        results: List[str] = []
        for item in raw or []:
            if isinstance(item, str):
                results.append(item)
                continue
            if not isinstance(item, dict) or not item.get("action"):
                continue
            action = str(item["action"]).strip().rstrip(".")
            owner = str(item.get("owner", "")).strip()
            why = str(item.get("why", "")).strip()
            evidence = item.get("evidence") or []
            if isinstance(evidence, str):
                evidence = [evidence]
            tags = "".join(f"[{str(e).strip('[]')}]" for e in evidence)
            line = action
            if owner:
                line += f" (Owner: {owner})"
            if why:
                line += f" - {why}"
            if tags:
                line += f" {tags}"
            results.append(line)
        return results

    @staticmethod
    def _check_citations(data: Dict[str, Any], valid_ids: set) -> Dict[str, Any]:
        """Count [Pn] tags that point to a real paper vs. ones the model made up."""
        text = json.dumps({k: data.get(k) for k in (
            "key_findings", "themes", "market_trends", "business_problems",
            "research_gaps", "recommendations")}, ensure_ascii=False)
        tags = re.findall(r"\[(P\d+)\]", text)
        invalid = sorted({t for t in tags if t not in valid_ids})
        return {"total_citations": len(tags), "invalid_ids": invalid}

    @staticmethod
    def _time_window(papers: List[Dict[str, Any]]) -> str:
        years = [p["year"] for p in papers if isinstance(p.get("year"), int)]
        if not years:
            return "Not specified"
        return f"{min(years)}-{max(years)}"

    @staticmethod
    def empty_output(topic: str) -> Dict[str, Any]:
        return {
            "topic": topic,
            "executive_summary": "No synthesis available: the model did not return valid structured output.",
            "objective": f"Assess research and market signals for {topic}",
            "research_questions": [],
            "sources": [],
            "time_window": "Not specified",
            "papers": [],
            "key_findings": [],
            "themes": [],
            "market_trends": [],
            "business_problems": [],
            "research_gaps": [],
            "recommendations": [],
            "strategic_roadmap": [],
            "content_ideas": [],
            "references": [],
        }
