from __future__ import annotations

import re
import time
from typing import List, Dict, Any

import requests


class SemanticScholarClient:
    def __init__(self, base_url: str = "https://api.semanticscholar.org/graph/v1/paper/search"):
        self.base_url = base_url
        self.headers = {
            "User-Agent": "EnterpriseResearchAgent/1.0 (mailto:research-agent@enterprise.local)"
        }

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        clean_query = re.sub(r"[^\w\s-]", " ", query).strip()
        params = {
            "query": clean_query,
            "limit": limit,
            "fields": "title,year,authors,abstract,externalIds,url,venue",
        }
        response = None
        for attempt in range(3):
            try:
                response = requests.get(self.base_url, params=params, headers=self.headers, timeout=25)
                if response.status_code == 200:
                    break
                elif response.status_code in (429, 503):
                    time.sleep(2.5 * (attempt + 1))
                else:
                    return []
            except requests.RequestException:
                if attempt == 2:
                    return []
                time.sleep(1.5 * (attempt + 1))

        if not response or response.status_code != 200:
            return []

        try:
            payload = response.json()
        except Exception:
            return []

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
