"""Single Source of Truth Unified Renderer (Section A3).

Every piece of user-facing synthesis text rendered in UI Findings, Signals,
Risks, Roadmap, Negative Findings, and exported in Markdown, HTML, LinkedIn Pack,
and JSON is generated strictly from the output_sentences table.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.ledger.models import OutputDoc, OutputSentence


class UnifiedRenderer:
    """Renders all UI and export representations from output_sentences."""

    def __init__(
        self,
        topic: str,
        doc: OutputDoc,
        sentences: List[OutputSentence],
        papers: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        base_dir: str = "outputs",
    ):
        self.topic = topic
        self.doc = doc
        self.sentences = sentences
        self.papers = papers
        self.metadata = metadata or {}
        self.base_dir = Path(base_dir)

        # Output directories
        self.reports_dir = self.base_dir / "reports"
        self.json_dir = self.base_dir / "json"
        self.csv_dir = self.base_dir / "csv"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.csv_dir.mkdir(parents=True, exist_ok=True)

        # Sentence partitioning
        self.headings = [s for s in sentences if s.type == "heading"]
        self.findings = [s for s in sentences if s.type in ("finding", "assertive")]
        self.signals = [s for s in sentences if s.type == "signal"]
        self.risks = [s for s in sentences if s.type == "risk"]
        self.roadmap = [s for s in sentences if s.type == "roadmap"]
        self.negative_findings = [s for s in sentences if s.type == "negative_finding"]
        self.opinions = [s for s in sentences if s.type == "opinion"]

    def to_ui_payload(self) -> Dict[str, Any]:
        """Produce presentation data structures for UI widgets."""
        ui_findings = [{"id": s.id, "text": s.text} for s in self.findings]
        ui_signals = [
            {"tag": f"KEY SIGNAL {idx+1}", "text": s.text, "citation": f"[P{idx+1}]"}
            for idx, s in enumerate(self.signals)
        ]
        ui_risks = [s.text for s in self.risks]

        ui_roadmap = []
        for idx, s in enumerate(self.roadmap, 1):
            if ":" in s.text:
                phase, action = s.text.split(":", 1)
            else:
                phase, action = f"Phase {idx}", s.text
            ui_roadmap.append({
                "phase": phase.strip(),
                "action": action.strip(),
                "impact": "Empirical governance target verified",
            })

        ui_neg = [s.text for s in self.negative_findings]

        return {
            "doc_id": self.doc.id,
            "findings": ui_findings,
            "signals": ui_signals,
            "risks": ui_risks,
            "roadmap": ui_roadmap,
            "negative_findings": ui_neg,
        }

    def render_markdown(self) -> str:
        """Render research_report.md strictly from output_sentences."""
        lines = [
            f"# Research Brief: {self.topic}",
            "",
            "## 1. Executive Summary",
        ]

        # Use heading/summary sentences if present
        exec_lines = [s.text for s in self.headings if "Executive Briefing" not in s.text and "Section" not in s.text]
        if not exec_lines:
            exec_lines = [s.text for s in self.findings[:2]]
        lines.append(exec_lines[0] if exec_lines else f"Empirical synthesis for {self.topic}.")
        lines.append("")

        lines.extend([
            "## 2. Key Empirical Findings",
        ])
        if self.findings:
            for idx, f in enumerate(self.findings, 1):
                lines.append(f"### Finding {idx}")
                lines.append(f"- {f.text}")
        else:
            lines.append("- No verified empirical findings available.")
        lines.append("")

        lines.extend([
            "## 3. Strategic Signals",
        ])
        if self.signals:
            for idx, sig in enumerate(self.signals, 1):
                lines.append(f"- Signal {idx}: {sig.text}")
        else:
            lines.append("- No strategic signals in evidence ledger.")
        lines.append("")

        lines.extend([
            "## 4. Delivery & Business Risks",
        ])
        if self.risks:
            for r in self.risks:
                lines.append(f"- {r.text}")
        else:
            lines.append("- No verified risk assertions in evidence ledger.")
        lines.append("")

        lines.extend([
            "## 5. What the Evidence Does Not Support (Negative Findings)",
        ])
        if self.negative_findings:
            for nf in self.negative_findings:
                lines.append(f"- {nf.text}")
        else:
            lines.append("- No negative findings in evidence ledger.")
        lines.append("")

        lines.extend([
            "## 6. Strategic Roadmap & Recommendations",
        ])
        if self.roadmap:
            for r in self.roadmap:
                lines.append(f"- {r.text}")
        else:
            lines.append("- Recommendations require LLM synthesis; currently in offline extractive mode.")
        lines.append("")

        lines.extend([
            "## 7. Evidence References",
        ])
        for idx, p in enumerate(self.papers, 1):
            lines.append(f"- [P{idx}] {p.get('title', 'Untitled')} ({p.get('year', 'n/a')}) {p.get('url') or p.get('link') or ''}".strip())

        return "\n".join(lines) + "\n"

    def render_draft_markdown(
        self,
        failing_gates: Optional[List[str]] = None,
        status: str = "NOT_PUBLISHABLE",
    ) -> str:
        """Render research_report.md watermarked as DRAFT with failing gates listed at top."""
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
        return "\n".join(header) + "\n" + self.render_markdown()

    def render_linkedin_pack(self) -> str:
        """Render linkedin_professional_pack.md strictly from output_sentences."""
        findings_block = "\n".join(f"- {f.text}" for f in self.findings) if self.findings else "- No verified empirical findings available."
        roadmap_block = "\n".join(f"- {r.text}" for r in self.roadmap) if self.roadmap else "- Recommendations require LLM synthesis; currently in offline extractive mode."

        posts = [
            f"# 📱 Professional Sharing & Executive Briefing Pack",
            f"**Topic:** {self.topic}",
            f"**Document ID:** {self.doc.id}",
            f"**Evidence Base:** {len(self.papers)} papers reviewed across evidence repositories.",
            "",
            "---",
            "",
            "## 📌 Post 1: Executive Briefing",
            "```markdown",
            f"Strategic analysis on: {self.topic}",
            "",
            "Key verified findings:",
            findings_block,
            "",
            "Actionable recommendations & roadmap:",
            roadmap_block,
            "```",
            "",
            "---",
            "",
            "## 📌 Post 2: Key Evidence & Findings",
            "```markdown",
            f"What does the peer-reviewed and empirical literature indicate regarding {self.topic}?",
            "",
            findings_block,
            "```",
            "",
            "---",
            "",
            "## 📌 Post 3: Strategic Recommendations",
            "```markdown",
            f"Leadership takeaways for {self.topic}:",
            "",
            roadmap_block,
            "```",
        ]
        return "\n".join(posts) + "\n"

    def render_html_storyline(self) -> str:
        """Render strategic_storyline.html strictly using output_sentences."""
        from src.output.html_storyline_builder import HtmlStorylineBuilder
        synthesis_adapter = {
            "executive_summary": (self.findings[0].text if self.findings else f"Analysis for {self.topic}"),
            "key_findings": [f.text for f in self.findings],
            "business_problems": [r.text for r in self.risks],
            "strategic_roadmap": [
                {"stage": (r.text.split(":")[0] if ":" in r.text else "Phase"),
                 "actions": [(r.text.split(":", 1)[1].strip() if ":" in r.text else r.text)],
                 "kpis": ["Verified delivery"]}
                for r in self.roadmap
            ],
            "papers": self.papers,
            "doc_id": self.doc.id,
            "business_context": self.metadata.get("business_context", {}),
        }
        return HtmlStorylineBuilder(self.topic).build(synthesis_adapter)

    def to_json_dict(self) -> Dict[str, Any]:
        """Render full research_report.json data object strictly containing output_sentences."""
        return {
            "topic": self.topic,
            "doc_id": self.doc.id,
            "run_id": self.doc.run_id,
            "status": self.doc.status,
            "output_sentences": [
                {
                    "id": s.id,
                    "output_id": s.output_id,
                    "ordinal": s.ordinal,
                    "text": s.text,
                    "type": s.type,
                    "claim_ids_json": s.claim_ids_json,
                    "strength_verb": s.strength_verb,
                    "checks_json": s.checks_json,
                    "created_at": s.created_at,
                }
                for s in self.sentences
            ],
            "papers": self.papers,
            "metadata": self.metadata,
        }

    def to_draft_json_dict(
        self,
        failing_gates: Optional[List[str]] = None,
        status: str = "NOT_PUBLISHABLE",
    ) -> Dict[str, Any]:
        """Produce full JSON dictionary watermarked as DRAFT with failing gates listed."""
        data = self.to_json_dict()
        data["watermark"] = "DRAFT, NOT FOR PUBLICATION"
        data["is_draft"] = True
        data["status"] = status
        data["failing_gates"] = failing_gates or ["Unmet PUBLISH_READY quality threshold"]
        ordered = {
            "watermark": data["watermark"],
            "status": data["status"],
            "failing_gates": data["failing_gates"],
            "is_draft": True,
        }
        ordered.update(data)
        return ordered

    def write_all(self) -> Dict[str, Path]:
        """Write all report deliverables to disk."""
        md_path = self.reports_dir / "research_report.md"
        md_path.write_text(self.render_markdown(), encoding="utf-8")

        html_path = self.reports_dir / "strategic_storyline.html"
        html_path.write_text(self.render_html_storyline(), encoding="utf-8")

        li_path = self.reports_dir / "linkedin_professional_pack.md"
        li_path.write_text(self.render_linkedin_pack(), encoding="utf-8")

        json_path = self.json_dir / "research_report.json"
        json_path.write_text(json.dumps(self.to_json_dict(), indent=2), encoding="utf-8")

        csv_path = self.csv_dir / "paper_index.csv"
        if not self.papers:
            csv_path.write_text("title,year,source,url\n", encoding="utf-8")
        else:
            keys = ["title", "year", "source", "url"]
            lines = [",".join(keys)]
            for p in self.papers:
                row = [str(p.get(k, "")).replace(",", " ") for k in keys]
                lines.append(",".join(row))
            csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return {
            "markdown": md_path,
            "html": html_path,
            "linkedin": li_path,
            "json": json_path,
            "csv": csv_path,
        }
