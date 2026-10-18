from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class ReportBuilder:
    def __init__(self, base_dir: Optional[str] = None):
        import os
        if base_dir is None or base_dir == "outputs":
            base_dir = os.getenv("OUTPUT_DIR", "outputs")
        from src.engine.stub_mode import is_stub_mode
        if is_stub_mode() and str(base_dir) == "outputs":
            import tempfile
            self._temp_dir_obj = tempfile.TemporaryDirectory()
            self.base_dir = Path(self._temp_dir_obj.name)
        else:
            self._temp_dir_obj = None
            self.base_dir = Path(base_dir)
        self.reports_dir = self.base_dir / "reports"
        self.json_dir = self.base_dir / "json"
        self.csv_dir = self.base_dir / "csv"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.csv_dir.mkdir(parents=True, exist_ok=True)

    def build_markdown(self, topic: str, synthesis: Dict[str, Any]) -> str:
        content_pack = synthesis.get("content_pack", {})
        sections = [
            f"# Research Brief: {topic}",
            "",
            "## 1. Executive Summary",
            synthesis.get("executive_summary", "- No executive summary available."),
            "",
            "## 2. Research Scope and Questions",
            "- Objective: " + synthesis.get("objective", "Not specified"),
            "- Questions:",
        ]

        for q in synthesis.get("research_questions", []):
            sections.append(f"  - {q}")

        sections.extend([
            "",
            "## 3. Search Strategy and Sources",
            "- Sources: " + ", ".join(synthesis.get("sources", ["Not specified"])),
            "- Time window: " + synthesis.get("time_window", "Not specified"),
            "",
            "## 4. Business Context",
        ])

        ctx = synthesis.get("business_context", {})
        focus = ctx.get("focus_areas", {})
        if focus:
            sections.append("- Focus areas: " + ", ".join(focus.keys()))
        signal = ctx.get("business_signal", {})
        if isinstance(signal, dict) and signal:
            sections.append(f"- Papers analysed: {signal.get('papers_analysed', 'n/a')}")
            sections.append(f"- Year range: {signal.get('year_range', 'n/a')}")
            mix = signal.get("source_mix", {})
            if mix:
                sections.append("- Source mix: " + ", ".join(f"{k} ({v})" for k, v in mix.items()))
        for item in ctx.get("finding_summary", []):
            sections.append(f"- {item}")

        sections.extend([
            "",
            "## 5. Papers Reviewed",
        ])

        for paper in synthesis.get("papers", []):
            sections.append(f"- {paper.get('title', 'Untitled')} ({paper.get('year', 'n/a')})")

        sections.extend([
            "",
            "## 6. Summary of Key Findings",
        ])

        for idx, finding in enumerate(synthesis.get("key_findings", []), start=1):
            sections.append(f"### Finding {idx}")
            sections.append(f"- {finding}")

        sections.extend([
            "",
            "## 7. Research Themes",
        ])
        for theme in synthesis.get("themes", []):
            sections.append(f"### {theme.get('name', 'Theme')}")
            sections.append(f"- {theme.get('description', 'No description')}")

        sections.extend([
            "",
            "## 8. Market Trends",
        ])
        for trend in synthesis.get("market_trends", []):
            sections.append(f"- {trend}")

        sections.extend([
            "",
            "## 9. Business Problems",
        ])
        for problem in synthesis.get("business_problems", []):
            sections.append(f"- {problem}")

        sections.extend([
            "",
            "## 10. Gaps in Current Research and Practice",
        ])
        for gap in synthesis.get("research_gaps", []):
            sections.append(f"- {gap}")

        sections.extend([
            "",
            "## 11. Recommendations",
        ])
        for rec in synthesis.get("recommendations", []):
            sections.append(f"- {rec}")

        sections.extend([
            "",
            "## 12. Strategic Roadmap",
        ])
        for road in synthesis.get("strategic_roadmap", []):
            if isinstance(road, dict):
                sections.append(f"### {road.get('stage', 'Stage')}")
                sections.append(f"- Objective: {road.get('objective', 'N/A')}")
                for action in road.get('actions', []):
                    sections.append(f"  - {action}")
                for kpi in road.get('kpis', []):
                    sections.append(f"  - KPI: {kpi}")
            else:
                sections.append(f"- {road}")

        sections.extend([
            "",
            "## 13. Content Ideas for Professional Sharing",
        ])
        for item in content_pack.get("linkedin_post_ideas", []):
            sections.append(f"- {item}")

        for item in content_pack.get("article_topics", []):
            sections.append(f"- Article idea: {item}")

        sections.extend([
            "",
            "## 14. References",
        ])
        for ref in synthesis.get("references", []):
            sections.append(f"- {ref}")

        return "\n".join(sections) + "\n"

    def build_draft_markdown(
        self,
        topic: str,
        synthesis: Dict[str, Any],
        failing_gates: Optional[List[str]] = None,
        status: str = "NOT_PUBLISHABLE",
    ) -> str:
        """Render report markdown watermarked as DRAFT with failing gates listed at top."""
        header = [
            "# DRAFT, NOT FOR PUBLICATION",
            "",
            "> **WARNING: DRAFT EXPORT ONLY — NOT FOR PUBLICATION**",
            f"> **Quality Status:** {status}",
            "> **Failing Gates / Unmet Governance Criteria:**",
        ]
        if failing_gates:
            for g in failing_gates:
                header.append(f"> - {g}")
        else:
            header.append("> - Output has not met PUBLISH_READY composite quality criteria (≥ 85)")
        header.extend(["", "---", ""])
        return "\n".join(header) + "\n" + self.build_markdown(topic, synthesis)

    def write_markdown(self, topic: str, synthesis: Dict[str, Any], filename: str = "research_report.md") -> Path:
        content = self.build_markdown(topic, synthesis)
        path = self.reports_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def build_html_storyline(self, topic: str, synthesis: Dict[str, Any]) -> str:
        from src.output.html_storyline_builder import HtmlStorylineBuilder
        return HtmlStorylineBuilder(topic).build(synthesis)

    def write_html_storyline(self, topic: str, synthesis: Dict[str, Any], filename: str = "strategic_storyline.html") -> Path:
        content = self.build_html_storyline(topic, synthesis)
        path = self.reports_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def build_linkedin_pack(self, topic: str, synthesis: Dict[str, Any]) -> str:
        from src.output.linkedin_pack_builder import LinkedInPackBuilder
        return LinkedInPackBuilder(topic).build(synthesis)

    def write_linkedin_pack(self, topic: str, synthesis: Dict[str, Any], filename: str = "linkedin_professional_pack.md") -> Path:
        content = self.build_linkedin_pack(topic, synthesis)
        path = self.reports_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def write_json(self, data: Dict[str, Any], filename: str = "research_report.json") -> Path:
        path = self.json_dir / filename
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def write_csv(self, papers: List[Dict[str, Any]], filename: str = "paper_index.csv") -> Path:
        path = self.csv_dir / filename
        if not papers:
            path.write_text("title,year,source,url\n", encoding="utf-8")
            return path

        keys = ["title", "year", "source", "url"]
        lines = [",".join(keys)]
        for paper in papers:
            row = [str(paper.get(key, "")).replace(",", " ") for key in keys]
            lines.append(",".join(row))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

