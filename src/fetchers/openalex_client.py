from __future__ import annotations

import re
from typing import Any, Dict, List
import requests


class OpenAlexClient:
    """Fetch scholarly works from the OpenAlex open-access API."""

    def __init__(self, base_url: str = "https://api.openalex.org/works"):
        self.base_url = base_url
        self.headers = {
            "User-Agent": "EnterpriseResearchAgent/1.0 (mailto:research-agent@enterprise.local)"
        }

    @staticmethod
    def _reconstruct_abstract(inverted_index: Any) -> str:
        if not isinstance(inverted_index, dict) or not inverted_index:
            return ""
        positions: List[tuple[int, str]] = []
        for word, idxs in inverted_index.items():
            if isinstance(idxs, list):
                for idx in idxs:
                    positions.append((idx, str(word)))
        positions.sort(key=lambda x: x[0])
        return " ".join(w for _, w in positions)

    name = "openalex"

    def fetch_abstract(self, doi: str) -> str:
        """The work's abstract by DOI, or '' when OpenAlex has none (S11: never invented)."""
        from src.analysis.abstracts import bare_doi

        d = bare_doi(doi)
        if not d:
            return ""
        try:
            resp = requests.get(f"{self.base_url}/doi:{d}", headers=self.headers, timeout=20)
            if resp.status_code != 200:
                return ""
            return self._reconstruct_abstract((resp.json() or {}).get("abstract_inverted_index"))
        except Exception:
            return ""

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        # Clean query for URL encoding
        clean_q = re.sub(r"[^\w\s-]", " ", query).strip()
        params = {
            "search": clean_q,
            "per-page": max_results,
        }
        try:
            resp = requests.get(self.base_url, params=params, headers=self.headers, timeout=20)
            if resp.status_code != 200:
                return []
            payload = resp.json()
        except Exception:
            return []

        papers: List[Dict[str, Any]] = []
        for item in payload.get("results", []):
            title = item.get("title") or ""
            abstract = self._reconstruct_abstract(item.get("abstract_inverted_index"))
            year = item.get("publication_year")
            doi = item.get("doi")
            url = doi or item.get("id")
            authors = []
            for authorship in item.get("authorships", []):
                author = authorship.get("author", {})
                if author.get("display_name"):
                    authors.append(author["display_name"])

            venue = None
            primary_location = item.get("primary_location") or {}
            source = primary_location.get("source") or {}
            if source.get("display_name"):
                venue = source["display_name"]

            papers.append({
                "title": title,
                "abstract": abstract,
                "year": year,
                "authors": authors,
                "source": "OpenAlex",
                "url": url,
                "doi": doi,
                "venue": venue,
            })
        return papers
