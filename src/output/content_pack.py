from __future__ import annotations

from typing import Any, Dict, List


class ContentPackBuilder:
    def __init__(self, topic: str):
        self.topic = topic

    def build(self, synthesis: Dict[str, Any]) -> Dict[str, Any]:
        recommendations = synthesis.get("recommendations", [])
        roadmap = synthesis.get("strategic_roadmap", [])
        findings = synthesis.get("key_findings", [])

        return {
            "linkedin_post_ideas": [
                f"What recent research says about {self.topic} and why enterprise teams struggle to scale it.",
                f"Three signals from the literature on {self.topic} that matter for engineering and business leaders.",
                f"Why {self.topic} needs governance, platform maturity, and measurable value delivery—not just experimentation.",
            ],
            "article_topics": [
                f"{self.topic}: market trends, adoption gaps, and strategic implications for enterprise delivery",
                f"Why {self.topic} still stalls in many organizations: research-backed lessons for leaders",
                f"From experimentation to strategic value: a roadmap for {self.topic} in practice",
            ],
            "talk_outline": [
                "The research landscape and why leaders are paying attention",
                "What enterprises are getting wrong in adoption and execution",
                "The strategic roadmap: governance, capability, and operational design",
                "Actionable next steps for engineering and product leaders",
            ],
            "recommended_takeaways": findings[:3] or ["Research suggests adoption depends on governance and operating model maturity.", "The value is highest when strategy is linked to delivery and platform capability."],
            "recommended_callouts": recommendations[:3] or ["Create a measured adoption charter", "Align AI capability with engineering workflow redesign", "Invest in governance and value measurement"],
            "roadmap_summary": roadmap[:3] if isinstance(roadmap, list) else [],
        }
