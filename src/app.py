from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List

from src.config import ensure_directories, load_config
from src.fetchers.arxiv_client import ArxivClient
from src.fetchers.semantic_scholar_client import SemanticScholarClient
from src.llm.ollama_client import OllamaClient
from src.output.report_builder import ReportBuilder


def build_topic_queries(topic: str) -> List[str]:
    query_base = topic.strip()
    variants = [
        query_base,
        f"{query_base} enterprise",
        f"{query_base} agile",
        f"{query_base} software engineering",
        f"{query_base} adoption",
    ]
    return variants


def merge_papers(results: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for batch in results:
        for item in batch:
            key = (item.get("title") or "").lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Research synthesis agent for enterprise AI/ML topics")
    parser.add_argument("--topic", default=os.getenv("DEFAULT_TOPIC", "AI adoption in enterprise software delivery"), help="Research topic")
    parser.add_argument("--max-papers", type=int, default=int(os.getenv("MAX_PAPERS", "10")), help="Maximum papers to review")
    parser.add_argument("--report-name", default="research_report.md", help="Name of generated markdown report")
    args = parser.parse_args()

    config = load_config("config.yaml")
    ensure_directories(config.get("output", {}).get("reports_dir", "outputs"))

    topic = args.topic
    queries = build_topic_queries(topic)

    arxiv_client = ArxivClient()
    sem_client = SemanticScholarClient()

    papers: List[Dict[str, Any]] = []
    for query in queries[:3]:
        try:
            arxiv_results = arxiv_client.search(query, max_results=max(3, args.max_papers // 2))
            sem_results = sem_client.search(query, limit=max(3, args.max_papers // 2))
            papers.extend(merge_papers([arxiv_results, sem_results]))
        except Exception as exc:
            print(f"Warning: fetch failed for query '{query}': {exc}")

    deduped = merge_papers([papers])[: args.max_papers]

    ollama = OllamaClient(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    )

    prompt = f"""
    You are a research strategist and business analyst. Analyze the following list of papers and return a structured synthesis.

    Requirements:
    1. Executive summary
    2. Objective and research questions
    3. Key findings
    4. Themes
    5. Market trends
    6. Business problems
    7. Research gaps
    8. Recommendations
    9. Strategic roadmap
    10. Content ideas for professional sharing
    11. References

    Topic: {topic}

    Papers:
    {json.dumps(deduped, indent=2, ensure_ascii=False)}
    """

    response = ollama.generate(prompt, system_prompt="You produce concise, actionable research synthesis for technology leaders.")

    synthesis = {
        "topic": topic,
        "executive_summary": response[:400],
        "objective": f"Assess research and market signals for {topic}",
        "research_questions": [
            "What are the key research themes in this topic?",
            "What business problems and market gaps are emerging?",
            "What are the strategic recommendations and roadmap implications?",
        ],
        "sources": ["arXiv", "Semantic Scholar", "Crossref"],
        "time_window": "2019-2025",
        "papers": deduped,
        "key_findings": ["Research synthesis will be populated after model analysis."],
        "themes": [{"name": "Strategic research theme", "description": response[:300]}],
        "market_trends": ["To be refined from model output."],
        "business_problems": ["To be refined from model output."],
        "research_gaps": ["To be refined from model output."],
        "recommendations": ["To be refined from model output."],
        "strategic_roadmap": ["To be refined from model output."],
        "content_ideas": ["LinkedIn post, article draft, webinar outline, strategic memo"],
        "references": [paper.get("link") or paper.get("url") or paper.get("title", "") for paper in deduped],
    }

    builder = ReportBuilder()
    builder.write_markdown(topic, synthesis, filename=args.report_name)
    builder.write_json(synthesis, filename="research_report.json")
    builder.write_csv(deduped, filename="paper_index.csv")

    print(f"Saved report: {builder.reports_dir / args.report_name}")
    print(f"Saved JSON: {builder.json_dir / 'research_report.json'}")
    print(f"Saved CSV: {builder.csv_dir / 'paper_index.csv'}")


if __name__ == "__main__":
    main()
