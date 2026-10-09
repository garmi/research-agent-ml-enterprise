from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List

from src.analysis.synthesizer import SynthesisEngine
from src.config import ensure_directories, load_config
from src.fetchers.arxiv_client import ArxivClient
from src.fetchers.crossref_client import CrossrefClient
from src.fetchers.semantic_scholar_client import SemanticScholarClient
from src.llm.ollama_client import OllamaClient
from src.output.report_builder import ReportBuilder


def build_topic_queries(topic: str) -> List[str]:
    base = topic.strip()
    return [
        base,
        f"{base} enterprise",
        f"{base} agile",
        f"{base} software engineering",
        f"{base} adoption",
    ]


def merge_papers(results: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for batch in results:
        for item in batch:
            title = (item.get("title") or "").strip().lower()
            if not title or title in seen:
                continue
            seen.add(title)
            merged.append(item)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Research synthesis agent for enterprise AI/ML topics")
    parser.add_argument("--topic", default=os.getenv("DEFAULT_TOPIC", "AI adoption in enterprise software delivery"), help="Research topic")
    parser.add_argument("--max-papers", type=int, default=int(os.getenv("MAX_PAPERS", "12")), help="Maximum papers to review")
    parser.add_argument("--report-name", default="research_report.md", help="Name of generated markdown report")
    args = parser.parse_args()

    config = load_config("config.yaml")
    ensure_directories(config.get("output", {}).get("reports_dir", "outputs"))

    topic = args.topic
    queries = build_topic_queries(topic)

    arxiv_client = ArxivClient()
    sem_client = SemanticScholarClient()
    crossref_client = CrossrefClient()

    papers: List[Dict[str, Any]] = []
    for query in queries[:4]:
        try:
            arxiv_results = arxiv_client.search(query, max_results=max(3, args.max_papers // 2))
            sem_results = sem_client.search(query, limit=max(3, args.max_papers // 2))
            crossref_results = crossref_client.search(query, max_results=max(3, args.max_papers // 2))
            papers.extend(merge_papers([arxiv_results, sem_results, crossref_results]))
        except Exception as exc:
            print(f"Warning: fetch failed for query '{query}': {exc}")

    deduped = merge_papers([papers])[: args.max_papers]

    ollama = OllamaClient(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    )

    synthesizer = SynthesisEngine(ollama)
    synthesis = synthesizer.analyze(topic, deduped)

    if not synthesis.get("papers"):
        synthesis["papers"] = deduped

    builder = ReportBuilder()
    builder.write_markdown(topic, synthesis, filename=args.report_name)
    builder.write_json(synthesis, filename="research_report.json")
    builder.write_csv(deduped, filename="paper_index.csv")

    print(f"Saved report: {builder.reports_dir / args.report_name}")
    print(f"Saved JSON: {builder.json_dir / 'research_report.json'}")
    print(f"Saved CSV: {builder.csv_dir / 'paper_index.csv'}")


if __name__ == "__main__":
    main()
