"""Turn a research-agent synthesis into a publishable insight record.

The research agent (``src.app`` / ``web_app.py``) produces a rich synthesis JSON.
This module is the bridge: it adds editorial metadata (slug, title, dek, tags,
reading time, provenance) and stores one JSON file per insight in
``website/content/insights/``. The site builder renders those files.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

CONTENT_DIR = Path("website/content/insights")

# Deterministic topic tagging so every insight gets sensible filters without an LLM call.
_TAG_RULES: List[tuple] = [
    ("Agentic AI", r"\bagent|autonomous|agentic|kiro|copilot|coding assistant"),
    ("Engineering Excellence", r"\bsdlc|software|engineering|developer|ci/cd|devops|devex|platform"),
    ("Governance & Risk", r"governance|guardrail|security|risk|compliance|provenance"),
    ("Value & ROI", r"\broi\b|productivity|cost|value|throughput|metric"),
    ("Operating Model", r"operating model|organi[sz]ation|talent|team structure|culture|adoption"),
    ("Artificial Intelligence", r"\bai\b|\bllm|machine learning|generative"),
]


def slugify(text: str, max_len: int = 64) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:max_len].strip("-") or "insight"


def _first_sentence(text: str, limit: int = 230) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    sentence = match.group(1) if match else text
    if len(sentence) > limit:
        sentence = sentence[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return sentence


def _headline(topic: str) -> str:
    topic = re.sub(r"\s+", " ", (topic or "").strip())
    return topic[:1].upper() + topic[1:] if topic else "Untitled insight"


def _to_text(item: Any) -> str:
    """Synthesis lists may hold strings or dicts depending on the LLM; flatten to text."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return " ".join(str(v) for v in item.values() if isinstance(v, (str, int, float)))
    return str(item)


def auto_tags(synthesis: Dict[str, Any], limit: int = 4) -> List[str]:
    haystack = " ".join(
        [
            synthesis.get("topic", ""),
            synthesis.get("executive_summary", ""),
            " ".join(_to_text(t) for t in synthesis.get("themes", [])),
        ]
    ).lower()
    tags = [name for name, pattern in _TAG_RULES if re.search(pattern, haystack)]
    return (tags or ["Artificial Intelligence"])[:limit]


def reading_minutes(synthesis: Dict[str, Any]) -> int:
    words = 0
    for key in ("executive_summary", "objective"):
        words += len(str(synthesis.get(key, "")).split())
    for key in ("key_findings", "market_trends", "business_problems", "research_gaps",
                "recommendations", "themes"):
        words += sum(len(_to_text(i).split()) for i in synthesis.get(key, []))
    for phase in synthesis.get("strategic_roadmap", []):
        words += len(_to_text(phase).split())
    return max(2, round(words / 215))


def _papers(synthesis: Dict[str, Any]) -> List[Dict[str, Any]]:
    papers = []
    for idx, p in enumerate(synthesis.get("papers", []), start=1):
        papers.append(
            {
                "id": f"P{idx}",
                "title": p.get("title", "Untitled"),
                "year": p.get("year"),
                "authors": (p.get("authors") or [])[:6],
                "venue": p.get("venue") or "",
                "source": p.get("source") or "",
                "url": p.get("url") or p.get("doi") or "",
                "relevance_score": p.get("relevance_score"),
            }
        )
    return papers


def build_record(
    synthesis: Dict[str, Any],
    *,
    title: Optional[str] = None,
    dek: Optional[str] = None,
    tags: Optional[Iterable[str]] = None,
    slug: Optional[str] = None,
    published: Optional[str] = None,
    featured: bool = False,
    draft: bool = False,
) -> Dict[str, Any]:
    topic = synthesis.get("topic", "")
    title = title or _headline(topic)
    citation = synthesis.get("citation_check") or {}
    signal = (synthesis.get("business_context") or {}).get("business_signal") or {}
    papers = _papers(synthesis)

    return {
        "slug": slug or slugify(title),
        "title": title,
        "dek": dek or _first_sentence(synthesis.get("executive_summary", "")),
        "topic": topic,
        "tags": list(tags) if tags else auto_tags(synthesis),
        "published": published or date.today().isoformat(),
        "featured": featured,
        "draft": draft,
        "read_minutes": reading_minutes(synthesis),
        "provenance": {
            "sources": synthesis.get("sources", []),
            "papers_analysed": len(papers),
            "time_window": synthesis.get("time_window", ""),
            "year_range": signal.get("year_range", ""),
            "citations_verified": int(citation.get("total_citations", 0)),
            "invalid_citations": len(citation.get("invalid_ids", [])),
            "tone": synthesis.get("tone", ""),
        },
        "body": {
            "executive_summary": synthesis.get("executive_summary", ""),
            "objective": synthesis.get("objective", ""),
            "research_questions": [_to_text(i) for i in synthesis.get("research_questions", [])],
            "key_findings": [_to_text(i) for i in synthesis.get("key_findings", [])],
            "themes": synthesis.get("themes", []),
            "market_trends": [_to_text(i) for i in synthesis.get("market_trends", [])],
            "business_problems": [_to_text(i) for i in synthesis.get("business_problems", [])],
            "research_gaps": [_to_text(i) for i in synthesis.get("research_gaps", [])],
            "recommendations": [_to_text(i) for i in synthesis.get("recommendations", [])],
            "strategic_roadmap": synthesis.get("strategic_roadmap", []),
        },
        "papers": papers,
    }


def save_record(record: Dict[str, Any], content_dir: Path = CONTENT_DIR) -> Path:
    content_dir.mkdir(parents=True, exist_ok=True)
    path = content_dir / f"{record['slug']}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def publish_json(path: str | Path, content_dir: Path = CONTENT_DIR, **editorial: Any) -> Path:
    synthesis = json.loads(Path(path).read_text(encoding="utf-8"))
    if not synthesis.get("executive_summary"):
        raise ValueError(f"{path} does not look like a research-agent synthesis (no executive_summary).")
    return save_record(build_record(synthesis, **editorial), content_dir)


def load_records(content_dir: Path = CONTENT_DIR, include_drafts: bool = False) -> List[Dict[str, Any]]:
    records = []
    for file in sorted(Path(content_dir).glob("*.json")):
        try:
            rec = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid insight file {file}: {exc}") from exc
        if rec.get("draft") and not include_drafts:
            continue
        records.append(rec)
    records.sort(key=lambda r: (r.get("published", ""), r.get("slug", "")), reverse=True)
    return records
