from __future__ import annotations

import json
from typing import Any, Dict, List

import requests


class CrossrefClient:
    """Query Crossref for research papers matching a topic."""

    def __init__(self, base_url: str = "https://api.crossref.org/works"):
        self.base_url = base_url

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        params = {
            "query.title": query,
            "rows": max_results,
            "select": "title,author,issued,URL,publisher,DOI,abstract",
        }
        response = requests.get(self.base_url, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()

        papers: List[Dict[str, Any]] = []
        for item in payload.get("message", {}).get("items", []):
            title = item.get("title", [""])[0] if item.get("title") else ""
            abstract = item.get("abstract", "")
            abstract = abstract.replace("\n", " ") if abstract else ""
            authors = [a.get("family", "") for a in item.get("author", []) if a.get("family")]
            issued = item.get("issued", {}).get("date-parts", [[None]])[0]
            year = issued[0] if isinstance(issued, list) and issued and issued[0] else None
            papers.append({
                "title": title,
                "abstract": abstract,
                "year": year,
                "authors": authors,
                "source": "Crossref",
                "url": item.get("URL"),
                "doi": item.get("DOI"),
            })
        return papers
