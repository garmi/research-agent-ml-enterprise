from __future__ import annotations

from typing import Any, Dict, List


class LinkedInPackBuilder:
    """Generates a structured, modular LinkedIn & Professional Sharing content pack.
    
    Generates content strictly from verified synthesis deliverables without
    hardcoded metrics, canned themes, or fabricated findings (enforcing A1 integrity).
    """

    def __init__(self, topic: str):
        self.topic = topic

    def build(self, synthesis: Dict[str, Any]) -> str:
        exec_summary = (synthesis.get("executive_summary") or "").strip()
        findings = [f.strip() for f in synthesis.get("key_findings", []) if f and f.strip()]
        recommendations = [r.strip() for r in synthesis.get("recommendations", []) if r and r.strip()]
        papers = synthesis.get("papers", [])

        findings_block = "\n".join(f"- {f}" for f in findings) if findings else "- No verified empirical findings available."
        recs_block = "\n".join(f"- {r}" for r in recommendations) if recommendations else "- No verified recommendations available."
        papers_count = len(papers)

        posts = [
            f"# 📱 Professional Sharing & Executive Briefing Pack",
            f"**Topic:** {self.topic}",
            f"**Evidence Base:** {papers_count} papers reviewed across evidence repositories.",
            "",
            "---",
            "",
            "## 📌 Post 1: Executive Briefing",
            "```markdown",
            f"Strategic analysis on: {self.topic}",
            "",
            exec_summary if exec_summary else f"Evidence-based analysis regarding {self.topic}.",
            "",
            "Key verified findings:",
            findings_block,
            "",
            "Actionable recommendations:",
            recs_block,
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
            recs_block,
            "```",
        ]

        return "\n".join(posts) + "\n"
