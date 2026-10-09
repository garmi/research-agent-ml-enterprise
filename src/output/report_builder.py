from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class ReportBuilder:
    def __init__(self, base_dir: str = "outputs"):
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

        for key, value in synthesis.get("business_context", {}).items():
            if isinstance(value, list):
                sections.append(f"- {key}: {', '.join(str(v) for v in value[:3])}")
            else:
                sections.append(f"- {key}: {value}")

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

    def write_markdown(self, topic: str, synthesis: Dict[str, Any], filename: str = "research_report.md") -> Path:
        content = self.build_markdown(topic, synthesis)
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
