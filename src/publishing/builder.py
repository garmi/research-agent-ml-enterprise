"""Static site generator for the personal-brand site.

Reads ``website/profile.yaml`` + published insight records and renders a fully
static site (no runtime server, no JS framework) into ``website/dist``.
"""
from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any, Dict, List
from xml.sax.saxutils import escape as xml_escape

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from .publisher import load_records, slugify

WEB_DIR = Path("website")
_CITE = re.compile(r"\[P(\d+)\]")
_PLACEHOLDER = re.compile(r"\[[^\]]*\]|TODO", re.IGNORECASE)
_REC = re.compile(
    r"^(?P<action>.*?)\s*\(Owner:\s*(?P<owner>[^)]+)\)\s*[-–—:]?\s*(?P<why>.*)$", re.DOTALL
)


# ----------------------------------------------------------------- filters
def _cite(text: str, ref_prefix: str = "") -> Markup:
    """Escape text and turn ``[P3]`` markers into links to the evidence list."""
    safe = str(escape(text or ""))
    safe = _CITE.sub(
        lambda m: f'<a class="cite" href="{ref_prefix}#p{m.group(1)}" aria-label="Source {m.group(1)}">{m.group(1)}</a>',
        safe,
    )
    return Markup(safe)


def _strip_cites(text: str) -> str:
    return re.sub(r"\s*\[P\d+\]", "", text or "").strip()


def _date(value: str, fmt: str = "%-d %b %Y") -> str:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime(fmt)
    except (ValueError, TypeError):
        return value or ""


def _hue(slug: str, base: int = 258) -> int:
    """Stable per-insight hue so cards get unique generative artwork."""
    return (base + sum(ord(c) for c in slug) * 7) % 360


def _split_rec(text: str) -> Dict[str, str]:
    m = _REC.match(text or "")
    if not m:
        return {"action": text, "owner": "", "why": ""}
    return {k: v.strip() for k, v in m.groupdict().items()}


def _roadmap_text(action: Any) -> str:
    if isinstance(action, str):
        return action
    if isinstance(action, dict):
        return " ".join(str(v) for v in action.values())
    return str(action)


def make_env(web_dir: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(web_dir / "templates")),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(
        cite=_cite, strip_cites=_strip_cites, fdate=_date, hue=_hue,
        split_rec=_split_rec, roadmap_text=_roadmap_text, slugify=slugify,
    )
    return env


# ----------------------------------------------------------------- data
def load_profile(web_dir: Path = WEB_DIR) -> Dict[str, Any]:
    return yaml.safe_load((web_dir / "profile.yaml").read_text(encoding="utf-8")) or {}


def find_placeholders(node: Any, path: str = "") -> List[str]:
    """Return dotted paths of profile values that still look like template placeholders."""
    found: List[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            found += find_placeholders(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found += find_placeholders(v, f"{path}[{i}]")
    elif isinstance(node, str) and _PLACEHOLDER.search(node):
        found.append(path)
    return found


def compute_stats(insights: List[Dict[str, Any]]) -> Dict[str, Any]:
    prov = [i.get("provenance", {}) for i in insights]
    sources = sorted({s for p in prov for s in p.get("sources", [])})
    return {
        "insights": len(insights),
        "papers": sum(p.get("papers_analysed", 0) for p in prov),
        "citations": sum(p.get("citations_verified", 0) for p in prov),
        "invalid": sum(p.get("invalid_citations", 0) for p in prov),
        "sources": sources,
    }


def json_resume(profile: Dict[str, Any], insights: List[Dict[str, Any]], site_url: str) -> Dict[str, Any]:
    """Machine-readable resume (jsonresume.org schema) so agents and ATS tools can consume it."""
    p = profile["person"]
    return {
        "$schema": "https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json",
        "basics": {
            "name": p["name"],
            "label": p.get("role", ""),
            "email": p.get("email", ""),
            "summary": " ".join(p.get("summary", [])),
            "location": {"address": p.get("location", "")},
            "url": site_url,
            "profiles": [{"network": k.title(), "url": v} for k, v in p.get("links", {}).items()],
        },
        "work": [
            {
                "name": w["company"], "position": w["role"], "location": w.get("location", ""),
                "startDate": w["period"], "summary": w.get("summary", ""),
                "highlights": w.get("achievements", []),
            }
            for w in profile.get("experience", [])
        ],
        "education": [
            {"institution": e["school"], "studyType": e["degree"], "startDate": e.get("period", "")}
            for e in profile.get("education", [])
        ],
        "skills": [{"name": s["group"], "keywords": s["items"]} for s in profile.get("skills", [])],
        "publications": [
            {
                "name": i["title"], "releaseDate": i["published"], "summary": i["dek"],
                "url": f"{site_url}/insights/{i['slug']}/" if site_url else f"insights/{i['slug']}/",
            }
            for i in insights
        ],
    }


# ----------------------------------------------------------------- build
class SiteBuilder:
    def __init__(self, web_dir: Path = WEB_DIR, include_drafts: bool = False):
        self.web_dir = Path(web_dir)
        self.dist = self.web_dir / "dist"
        self.env = make_env(self.web_dir)
        self.profile = load_profile(self.web_dir)
        self.insights = load_records(self.web_dir / "content" / "insights", include_drafts)
        self.stats = compute_stats(self.insights)
        self.site_url = (self.profile.get("site", {}).get("url") or "").rstrip("/")
        counts = Counter(t for i in self.insights for t in i.get("tags", []))
        self.topics = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    # -- rendering helpers
    def _render(self, template: str, out: str, **ctx: Any) -> None:
        depth = out.count("/")
        page = ctx.pop("page", {})
        page.setdefault("path", out.replace("index.html", ""))
        html = self.env.get_template(template).render(
            profile=self.profile, site=self.profile.get("site", {}), person=self.profile.get("person", {}),
            insights=self.insights, topics=self.topics, stats=self.stats,
            root="../" * depth, site_url=self.site_url, page=page,
            year=datetime.now().year, **ctx,
        )
        target = self.dist / out
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")

    def _write(self, rel: str, content: str) -> None:
        target = self.dist / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def build(self) -> Path:
        if self.dist.exists():
            shutil.rmtree(self.dist)
        self.dist.mkdir(parents=True)
        static = self.web_dir / "static"
        if static.exists():
            shutil.copytree(static, self.dist / "static")

        featured = next((i for i in self.insights if i.get("featured")), self.insights[0] if self.insights else None)
        rest = [i for i in self.insights if i is not featured]
        site = self.profile.get("site", {})

        self._render("home.html", "index.html", featured=featured, latest=rest[:3],
                     page={"title": site.get("title"), "description": site.get("description")})
        self._render("insights.html", "insights/index.html",
                     page={"title": "Insights", "description": "Research-backed perspectives on enterprise AI and engineering."})
        for rec in self.insights:
            related = [r for r in self.insights if r is not rec and set(r.get("tags", [])) & set(rec.get("tags", []))][:3]
            self._render("article.html", f"insights/{rec['slug']}/index.html", insight=rec, related=related,
                         page={"title": rec["title"], "description": rec["dek"], "type": "article"})
        self._render("about.html", "about/index.html",
                     page={"title": "About & Resume", "description": self.profile["person"].get("positioning", "")})
        self._render("method.html", "method/index.html",
                     page={"title": "How the research engine works",
                           "description": "The evidence pipeline behind every insight: discover, verify, synthesise, publish."})
        self._render("404.html", "404.html", page={"title": "Page not found"})

        self._write("search-index.json", json.dumps([
            {"slug": i["slug"], "title": i["title"], "dek": i["dek"], "tags": i["tags"]} for i in self.insights
        ], ensure_ascii=False))
        self._write("resume.json", json.dumps(json_resume(self.profile, self.insights, self.site_url), indent=2, ensure_ascii=False))
        self._write("robots.txt", "User-agent: *\nAllow: /\n" + (f"Sitemap: {self.site_url}/sitemap.xml\n" if self.site_url else ""))
        if self.site_url:
            self._write_sitemap()
            self._write_feed()
        return self.dist

    # -- machine-readable outputs
    def _write_sitemap(self) -> None:
        paths = ["", "insights/", "about/", "method/"] + [f"insights/{i['slug']}/" for i in self.insights]
        urls = "".join(f"<url><loc>{xml_escape(self.site_url + '/' + p)}</loc></url>" for p in paths)
        self._write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')

    def _write_feed(self) -> None:
        site = self.profile.get("site", {})
        items = ""
        for i in self.insights:
            when = datetime.strptime(i["published"][:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            link = f"{self.site_url}/insights/{i['slug']}/"
            items += (
                f"<item><title>{xml_escape(i['title'])}</title><link>{xml_escape(link)}</link>"
                f"<guid>{xml_escape(link)}</guid><pubDate>{format_datetime(when)}</pubDate>"
                f"<description>{xml_escape(i['dek'])}</description></item>"
            )
        self._write("feed.xml", (
            '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            f"<title>{xml_escape(site.get('title', ''))}</title><link>{xml_escape(self.site_url)}</link>"
            f"<description>{xml_escape(site.get('description', '').strip())}</description>{items}</channel></rss>"
        ))
