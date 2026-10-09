from __future__ import annotations

from typing import List, Dict, Any

import requests


class SemanticScholarClient:
    def __init__(self, base_url: str = "https://api.semanticscholar.org/graph/v1/paper/search"):
        self.base_url = base_url

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        params = {
            "query": query,
            "limit": limit,
            "fields": "title,year,authors,abstract,externalIds,url,venue",
        }
        response = requests.get(self.base_url, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("data", [])

        papers = []
        for item in results:
            paper = {
                "title": item.get("title", ""),
                "abstract": item.get("abstract", ""),
                "year": item.get("year"),
                "authors": [a.get("name", "") for a in item.get("authors", [])],
                "source": "Semantic Scholar",
                "url": item.get("url"),
                "venue": item.get("venue"),
            }
            papers.append(paper)
        return papers
