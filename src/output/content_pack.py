from __future__ import annotations

from typing import Any, Dict, List


class ContentPackBuilder:
    def __init__(self, topic: str):
        self.topic = topic

    def build(self, synthesis: Dict[str, Any]) -> Dict[str, Any]:
        recommendations = synthesis.get("recommendations", [])
        roadmap = synthesis.get("strategic_roadmap", [])
        findings = synthesis.get("key_findings", [])
        content_ideas = synthesis.get("content_ideas") or []

        article_topics = [f"Empirical findings on {self.topic}: {f}" for f in findings[:3]] if findings else []
        talk_outline = [
            f"Overview of research on {self.topic}",
            *[f"Finding: {f}" for f in findings[:2]],
            *[f"Recommendation: {r}" for r in recommendations[:2]],
        ] if (findings or recommendations) else []

        return {
            "linkedin_post_ideas": content_ideas,
            "article_topics": article_topics,
            "talk_outline": talk_outline,
            "recommended_takeaways": findings[:3],
            "recommended_callouts": recommendations[:3],
            "roadmap_summary": roadmap[:3] if isinstance(roadmap, list) else [],
        }
