"""Academic search across sources in parallel (S27).

Each source keeps its queries in order on its own worker (so its rate limit sees the same pace as before), and the
sources run side by side. Results come back in the old order: for each query, each source in turn. A source that
fails, or a query not started before the time budget ends, gives an empty batch.
"""

from __future__ import annotations

import inspect
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _search(source: Any, query: str, n: int) -> List[Dict[str, Any]]:
    params = inspect.signature(source.search).parameters
    return source.search(query, limit=n) if "limit" in params and "max_results" not in params else source.search(query, max_results=n)


def search_sources(sources: List[Any], queries: List[str], max_per_query: int,
                   time_budget: Optional[float] = None) -> List[List[Dict[str, Any]]]:
    deadline = time.monotonic() + time_budget if time_budget else None

    def run(source: Any) -> List[List[Dict[str, Any]]]:
        out = []
        for q in queries:
            if deadline and time.monotonic() > deadline:
                logger.warning("Search time budget reached; skipped %s for %r", type(source).__name__, q[:60])
                out.append([])
                continue
            try:
                out.append(list(_search(source, q, max_per_query) or []))
            except Exception as e:  # one source failing never stops the others
                logger.warning("Search failed on %s (%s)", type(source).__name__, type(e).__name__)
                out.append([])
        return out

    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as pool:
        per_source = list(pool.map(run, sources))
    return [per_source[s][qi] for qi in range(len(queries)) for s in range(len(sources))]
