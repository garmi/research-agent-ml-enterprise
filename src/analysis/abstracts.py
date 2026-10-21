"""Real abstracts only (S11). Source text is never invented: a paper whose abstract is missing or too
short gets its real abstract by DOI (OpenAlex, then Semantic Scholar), or is set aside with a reason."""

from __future__ import annotations

import re
from typing import Optional, Any, Dict, List, Sequence, Tuple

MIN_ABSTRACT_CHARS = 60
_FETCHER_LABEL = {"openalex": "OpenAlex", "semantic_scholar": "Semantic Scholar"}


def bare_doi(value: Any) -> str:
    """'https://doi.org/10.1/x' or 'doi:10.1/x' -> '10.1/x'; '' when there is no DOI."""
    m = re.search(r"10\.\d+/\S+", str(value or ""))
    return m.group(0).rstrip(".,;)") if m else ""


def fill_abstracts(papers: List[Dict[str, Any]], fetchers: Sequence[Any], time_budget: Optional[float] = None,
                   workers: int = 1) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(kept, set_aside). Each fetcher has .name and .fetch_abstract(doi) -> str ('' when not found).
    S27: lookups run on `workers` threads; papers not looked up within `time_budget` seconds are set aside."""
    from concurrent.futures import ThreadPoolExecutor, wait

    tried = " or ".join(_FETCHER_LABEL.get(getattr(f, "name", ""), getattr(f, "name", "")) for f in fetchers)
    results: Dict[int, Tuple[str, Dict[str, Any]]] = {}

    def lookup(p: Dict[str, Any], doi: str) -> Tuple[str, Dict[str, Any]]:
        for f in fetchers:
            try:
                text = (f.fetch_abstract(doi) or "").strip()
            except Exception:
                text = ""
            if len(text) >= MIN_ABSTRACT_CHARS:
                return "kept", {**p, "abstract": text, "abstract_source": f.name}
        return "aside", {"title": p.get("title", ""), "reason": f"No abstract available from {tried}."}

    pool = ThreadPoolExecutor(max_workers=max(1, workers))
    futures = {}
    for i, p in enumerate(papers):
        if len((p.get("abstract") or "").strip()) >= MIN_ABSTRACT_CHARS:
            results[i] = ("kept", p)
            continue
        doi = bare_doi(p.get("doi") or p.get("url"))
        if not doi:
            results[i] = ("aside", {"title": p.get("title", ""), "reason": "No abstract and no DOI to look one up."})
            continue
        futures[pool.submit(lookup, p, doi)] = i
    done, _ = wait(list(futures), timeout=time_budget)
    for fut, i in futures.items():
        if fut in done:
            results[i] = fut.result()
        else:
            results[i] = ("aside", {"title": papers[i].get("title", ""),
                                    "reason": "Abstract lookup ran out of time for this run."})
    pool.shutdown(wait=False, cancel_futures=True)
    kept = [results[i][1] for i in sorted(results) if results[i][0] == "kept"]
    set_aside = [results[i][1] for i in sorted(results) if results[i][0] == "aside"]
    return kept, set_aside
