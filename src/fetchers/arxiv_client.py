from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import List, Dict, Any

import requests


class ArxivClient:
    """arXiv API client with rate-limiting backoff and polite headers."""

    def __init__(self, base_url: str = "https://export.arxiv.org/api/query"):
        self.base_url = base_url
        self.headers = {
            "User-Agent": "EnterpriseResearchAgent/1.0 (academic-research; mailto:research-agent@enterprise.local)"
        }

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        # Clean query: strip characters that corrupt arXiv query parser
        clean_query = re.sub(r"[^\w\s-]", " ", query).strip()
        params = {
            "search_query": f"all:{clean_query}",
            "start": 0,
            "max_results": max_results,
        }
        
        response = None
        for attempt in range(3):
            try:
                response = requests.get(self.base_url, params=params, headers=self.headers, timeout=30)
                if response.status_code == 200:
                    break
                elif response.status_code in (429, 503):
                    time.sleep(3.0 * (attempt + 1))
                else:
                    response.raise_for_status()
            except requests.RequestException:
                if attempt == 2:
                    return []
                time.sleep(2.0 * (attempt + 1))

        if not response or response.status_code != 200:
            return []

        try:
            return self._parse_response(response.text)
        except Exception:
            return []

    def _parse_response(self, xml_text: str) -> List[Dict[str, Any]]:
        root = ET.fromstring(xml_text)
        namespace = {"a": "http://www.w3.org/2005/Atom"}
        entries = []

        for entry in root.findall("a:entry", namespace):
            title = entry.findtext("a:title", default="", namespaces=namespace).strip().replace("\n", " ")
            summary = entry.findtext("a:summary", default="", namespaces=namespace).strip().replace("\n", " ")
            published = entry.findtext("a:published", default="", namespaces=namespace)
            link = None
            for item in entry.findall("a:link", namespace):
                rel = item.attrib.get("rel")
                href = item.attrib.get("href")
                if rel == "alternate" and href:
                    link = href
                    break
            entry_id = entry.findtext("a:id", default="", namespaces=namespace).strip()
            arxiv_id = re.sub(r"v\d+$", "", entry_id.rsplit("/abs/", 1)[-1]) if entry_id else ""
            year = int(published[:4]) if published[:4].isdigit() else None
            entries.append({
                "title": title,
                "abstract": summary,
                "published": published,
                "year": year,
                "source": "arXiv",
                "link": link,
                "url": link,
                "arxiv_id": arxiv_id,
            })
        return entries
