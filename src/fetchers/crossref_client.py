from __future__ import annotations

import re
import time
from typing import Any, Dict, List

import requests


class CrossrefClient:
    """Query Crossref for research papers with polite pool headers."""

    def __init__(self, base_url: str = "https://api.crossref.org/works"):
        self.base_url = base_url
        self.headers = {
            "User-Agent": "EnterpriseResearchAgent/1.0 (mailto:research-agent@enterprise.local)"
        }

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        clean_query = re.sub(r"[^\w\s-]", " ", query).strip()
        params = {
            "query.bibliographic": clean_query,
            "rows": max_results,
            "select": "title,author,issued,URL,publisher,DOI,abstract,container-title",
        }
        
        response = None
        for attempt in range(3):
            try:
                response = requests.get(self.base_url, params=params, headers=self.headers, timeout=25)
                if response.status_code == 200:
                    break
                elif response.status_code in (429, 503):
                    time.sleep(2.0 * (attempt + 1))
                else:
                    response.raise_for_status()
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

        papers: List[Dict[str, Any]] = []
        for item in payload.get("message", {}).get("items", []):
            title = item.get("title", [""])[0] if item.get("title") else ""
            abstract = item.get("abstract", "")
            abstract = re.sub(r"<[^>]+>", " ", abstract) if abstract else ""
            abstract = re.sub(r"\s+", " ", abstract).strip()
            authors = [a.get("family", "") for a in item.get("author", []) if a.get("family")]
            issued = item.get("issued", {}).get("date-parts", [[None]])[0]
            year = issued[0] if isinstance(issued, list) and issued and issued[0] else None
            container_title = item.get("container-title", [""])[0] if item.get("container-title") else ""
            publisher = item.get("publisher") or ""
            venue = container_title or publisher or ""
            papers.append({
                "title": title,
                "abstract": abstract,
                "year": year,
                "authors": authors,
                "source": "Crossref",
                "venue": venue,
                "container_title": container_title,
                "url": item.get("URL"),
                "doi": item.get("DOI"),
            })
        return papers
