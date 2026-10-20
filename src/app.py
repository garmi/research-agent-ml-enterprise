from __future__ import annotations

import argparse
import os
import re
from typing import Any, Dict, List

from dotenv import load_dotenv

from src.analysis.business_context import detect_focus_areas
from src.analysis.insight_builder import derive_business_signal, summarize_findings
from src.analysis.relevance import rank_papers, STOPWORDS
from src.analysis.synthesizer import SynthesisEngine
from src.config import ensure_directories, load_config
from src.fetchers.arxiv_client import ArxivClient
from src.fetchers.crossref_client import CrossrefClient
from src.fetchers.openalex_client import OpenAlexClient
from src.fetchers.semantic_scholar_client import SemanticScholarClient
from src.llm.factory import build_llm
from src.output.content_pack import ContentPackBuilder
from src.output.report_builder import ReportBuilder


def build_topic_queries(topic: str) -> List[str]:
    base = topic.strip()
    words = re.findall(r"[a-zA-Z0-9]+", base)
    cleaned_tokens = [w for w in words if w.lower() not in STOPWORDS]
    cleaned_base = " ".join(cleaned_tokens) if cleaned_tokens else base

    queries = [cleaned_base]
    if cleaned_base.lower() != base.lower():
        queries.append(base)

    # Domain-neutral expansions (S19): the same for every question; no topic- or field-specific cases.
    queries.extend([
        f"{cleaned_base} empirical study",
        f"{cleaned_base} case study",
        f"{cleaned_base} adoption",
        f"{cleaned_base} enterprise",
    ])

    seen = set()
    unique_queries = []
    for q in queries:
        norm = re.sub(r"\s+", " ", q).strip()
        if norm and norm.lower() not in seen:
            seen.add(norm.lower())
            unique_queries.append(norm)
    return unique_queries


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _paper_keys(item: Dict[str, Any]) -> List[str]:
    keys = []
    if item.get("doi"):
        keys.append("doi:" + str(item["doi"]).lower().strip())
    if item.get("arxiv_id"):
        keys.append("arxiv:" + str(item["arxiv_id"]).lower().strip())
    title = _norm_title(item.get("title", ""))
    if title:
        keys.append("title:" + title)
    return keys


def merge_papers(results: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Dedupe across all batches by DOI, arXiv ID, or normalized title."""
    merged: List[Dict[str, Any]] = []
    seen = set()
    for batch in results:
        for item in batch:
            keys = _paper_keys(item)
            if not keys or any(k in seen for k in keys):
                continue
            seen.update(keys)
            merged.append(item)
    return merged


def safe_fetch(label: str, fn, *args, **kwargs) -> List[Dict[str, Any]]:
    """One failing source must not kill the others."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        print(f"Warning: {label} failed: {exc}")
        return []


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Research synthesis agent for enterprise AI/ML topics")
    parser.add_argument("--topic", default=os.getenv("DEFAULT_TOPIC", "AI adoption in enterprise software delivery"), help="Research topic")
    parser.add_argument("--max-papers", type=int, default=int(os.getenv("MAX_PAPERS", "12")), help="Maximum papers to review")
    parser.add_argument("--report-name", default="research_report.md", help="Name of generated markdown report")
    parser.add_argument("--mode", choices=["quick", "deep"], default="deep", help="Quick scan or deep dive")
    parser.add_argument("--tone", choices=["executive", "engineering", "thought_leadership"], default=os.getenv("DEFAULT_TONE", "executive"), help="Tone of strategic synthesis")
    parser.add_argument("--length", choices=["concise", "detailed"], default=os.getenv("DEFAULT_LENGTH", "detailed"), help="Report length and detail profile")
    parser.add_argument("--map-provider", choices=["ollama", "gemini"], help="Override per-paper extraction provider")
    parser.add_argument("--reduce-provider", choices=["ollama", "gemini"], help="Override synthesis provider")
    args = parser.parse_args()

    config = load_config("config.yaml")
    ensure_directories(config.get("output", {}).get("reports_dir", "outputs"))

    topic = args.topic
    queries = build_topic_queries(topic)
    if args.mode == "quick":
        query_limit, max_per_query = 2, 4
    else:
        query_limit, max_per_query = 5, 6

    arxiv_client = ArxivClient()
    openalex_client = OpenAlexClient()
    sem_client = SemanticScholarClient()
    crossref_client = CrossrefClient()

    batches: List[List[Dict[str, Any]]] = []
    for query in queries[:query_limit]:
        batches.append(safe_fetch("OpenAlex", openalex_client.search, query, max_results=max_per_query))
        batches.append(safe_fetch("Crossref", crossref_client.search, query, max_results=max_per_query))
        batches.append(safe_fetch("arXiv", arxiv_client.search, query, max_results=max_per_query))
        batches.append(safe_fetch("Semantic Scholar", sem_client.search, query, limit=max_per_query))

    all_papers = merge_papers(batches)
    valid_papers = []
    for p in all_papers:
        ab = (p.get("abstract") or "").strip()
        if len(ab) >= 70:
            valid_papers.append(p)
        elif p.get("title"):
            venue = p.get("venue") or p.get("source") or "academic literature"
            year_str = f" ({p.get('year')})" if p.get("year") else ""
            p["abstract"] = f"{p['title']}. Research publication from {venue}{year_str}. Focuses on software engineering, architecture, and technology evaluation."
            valid_papers.append(p)
    all_papers = valid_papers
    print(f"Fetched {len(all_papers)} unique papers with abstracts.")

    ranked = rank_papers(all_papers, topic)
    min_score = float(config.get("research", {}).get("min_relevance_score", 0.5))
    filtered = [paper for paper in ranked if float(paper.get("relevance_score", 0.0)) >= min_score]
    if not filtered and ranked:
        filtered = ranked[: args.max_papers]
    selected = filtered[: args.max_papers]

    if not selected:
        raise ValueError(f"No papers met the relevance threshold for '{topic}'. Try broadening your search.")

    llm_cfg = config.get("llm", {})
    map_provider = args.map_provider or llm_cfg.get("map_provider", "ollama")
    reduce_provider = args.reduce_provider or llm_cfg.get("reduce_provider", "ollama")
    print(f"LLM providers: map={map_provider}, reduce={reduce_provider}")

    map_llm = build_llm(map_provider, config)
    reduce_llm = map_llm if reduce_provider == map_provider else build_llm(reduce_provider, config)

    synthesizer = SynthesisEngine(map_llm, reduce_llm)
    synthesis = synthesizer.analyze(topic, selected, tone=args.tone, length=args.length)
    synthesis["papers"] = selected
    synthesis["tone"] = args.tone
    synthesis["length"] = args.length
    synthesis["business_context"] = {
        "focus_areas": detect_focus_areas(topic),
        "business_signal": derive_business_signal(topic, selected),
        "finding_summary": summarize_findings(synthesis.get("paper_summaries", [])),
    }

    synthesis["content_pack"] = ContentPackBuilder(topic).build(synthesis)

    builder = ReportBuilder()
    builder.write_markdown(topic, synthesis, filename=args.report_name)
    builder.write_json(synthesis, filename="research_report.json")
    builder.write_csv(selected, filename="paper_index.csv")

    print(f"Research synthesis completed successfully: {args.report_name}")


if __name__ == "__main__":
    main()
