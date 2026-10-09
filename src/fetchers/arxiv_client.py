from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List, Dict, Any

import requests


class ArxivClient:
    """Minimal arXiv API client for title, abstract, and metadata retrieval."""

    def __init__(self, base_url: str = "https://export.arxiv.org/api/query"):
        self.base_url = base_url

    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
        }
        response = requests.get(self.base_url, params=params, timeout=60)
        response.raise_for_status()
        return self._parse_response(response.text)

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
            entries.append({
                "title": title,
                "abstract": summary,
                "published": published,
                "source": "arXiv",
                "link": link,
            })
        return entries
