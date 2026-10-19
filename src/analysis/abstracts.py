"""Real abstracts only (S11). Source text is never invented: a paper whose abstract is missing or too
short gets its real abstract by DOI (OpenAlex, then Semantic Scholar), or is set aside with a reason."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

MIN_ABSTRACT_CHARS = 60
_FETCHER_LABEL = {"openalex": "OpenAlex", "semantic_scholar": "Semantic Scholar"}


def bare_doi(value: Any) -> str:
    """'https://doi.org/10.1/x' or 'doi:10.1/x' -> '10.1/x'; '' when there is no DOI."""
    m = re.search(r"10\.\d+/\S+", str(value or ""))
    return m.group(0).rstrip(".,;)") if m else ""


def fill_abstracts(papers: List[Dict[str, Any]], fetchers: Sequence[Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(kept, set_aside). Each fetcher has .name and .fetch_abstract(doi) -> str ('' when not found)."""
    kept: List[Dict[str, Any]] = []
    set_aside: List[Dict[str, Any]] = []
    tried = " or ".join(_FETCHER_LABEL.get(getattr(f, "name", ""), getattr(f, "name", "")) for f in fetchers)
    for p in papers:
        if len((p.get("abstract") or "").strip()) >= MIN_ABSTRACT_CHARS:
            kept.append(p)
            continue
        doi = bare_doi(p.get("doi") or p.get("url"))
        if not doi:
            set_aside.append({"title": p.get("title", ""), "reason": "No abstract and no DOI to look one up."})
            continue
        for f in fetchers:
            text = (f.fetch_abstract(doi) or "").strip()
            if len(text) >= MIN_ABSTRACT_CHARS:
                kept.append({**p, "abstract": text, "abstract_source": f.name})
                break
        else:
            set_aside.append({"title": p.get("title", ""), "reason": f"No abstract available from {tried}."})
    return kept, set_aside
