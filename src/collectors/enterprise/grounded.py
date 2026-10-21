"""Enterprise and practice evidence found with Gemini's Google Search grounding (S22).

Gemini searches; our pipeline reads; Check A and the gates judge.
- Only the grounding metadata is used: the source URLs and titles, the queries Google ran, and the Search
  Suggestions markup (shown in the Evidence tab, as Google's terms require). Gemini's answer text is discarded.
- Each page is fetched by us (HTML, or PDF via pypdf) and becomes its own source, so Check A judges every page.
- Sources are classified and capped by rule; only passages carrying the question's terms become claims.
"""

from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (compatible; ResearchAgent/2.0; +https://github.com/garmi/research-agent-ml-enterprise)"}

# Domains are matched on the host or any parent domain ("blog.example.com" matches "example.com").
VENDORS = ("microsoft.com", "aws.amazon.com", "amazon.com", "cloud.google.com", "google.com", "github.blog", "github.com",
           "ibm.com", "oracle.com", "salesforce.com", "sap.com", "atlassian.com", "gitlab.com", "jetbrains.com",
           "openai.com", "anthropic.com", "nvidia.com", "databricks.com", "snowflake.com", "servicenow.com",
           "sonarsource.com", "coderabbit.ai", "codacy.com", "snyk.io", "datadoghq.com", "redhat.com", "vmware.com")
INDUSTRY = ("dora.dev", "gartner.com", "forrester.com", "mckinsey.com", "deloitte.com", "pwc.com", "kpmg.com", "ey.com",
            "accenture.com", "bcg.com", "bain.com", "idc.com", "stackoverflow.co", "survey.stackoverflow.co",
            "stateofdevops.com", "weforum.org", "oecd.org", "hbr.org", "sloanreview.mit.edu", "linuxfoundation.org",
            "cncf.io", "thoughtworks.com", "infoq.com")
REGULATORS = ("nist.gov", "iso.org", "europa.eu", "ncsc.gov.uk", "cisa.gov", "who.int", "fda.gov", "ftc.gov", "gov.uk")
NEWS = ("reuters.com", "bloomberg.com", "ft.com", "wsj.com", "nytimes.com", "theverge.com", "techcrunch.com", "zdnet.com",
        "wired.com", "venturebeat.com", "theregister.com", "cnbc.com", "forbes.com", "businessinsider.com", "axios.com",
        "economictimes.indiatimes.com", "livemint.com")
BLOCKED = ("pinterest.com", "quora.com", "facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com",
           "slideshare.net", "scribd.com", "coursehero.com", "studocu.com", "chegg.com", "youtube.com", "reddit.com")
PAYWALLED = ("gartner.com", "forrester.com", "idc.com", "ft.com", "wsj.com", "bloomberg.com", "hbr.org")
_SALES_CUES = re.compile(r"\b(book a demo|request a demo|schedule a demo|get a demo|start (your |a )?free trial|"
                         r"try (it )?(for )?free|sign up (for )?free|get started (for )?free|see pricing|pricing plans?|"
                         r"view pricing|contact sales|talk to sales)\b", re.IGNORECASE)
_PAYWALL_CUES = re.compile(r"\b(subscribe to (continue|read)|become a client|log ?in to (read|continue)|sign in to (read|continue)|"
                           r"for subscribers only|this content is for (clients|members))\b", re.IGNORECASE)


def _host(url: str) -> str:
    return (urlparse(url).netloc or "").lower().split(":")[0].removeprefix("www.")


def _matches(host: str, domains: Tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def page_is_selling(page: str) -> bool:
    """S22c: sales cues anywhere in the page, navigation and footer included (the article text drops them)."""
    return bool(_SALES_CUES.search(re.sub(r"<[^>]+>", " ", page or "")))


def classify_source(url: str, title: str, text: str, selling: bool = False) -> Optional[Dict[str, str]]:
    """source_type, grade (the cap for its claims), commercial stake and a reader label; None for a blocked site."""
    host = _host(url)
    if not host or _matches(host, BLOCKED):
        return None
    if "sec.gov" in host:
        return {"source_type": "filing", "grade": "weak", "stake": "unknown", "label": "Company filing"}
    if _matches(host, REGULATORS) or host.endswith(".gov") or ".gov." in host:
        return {"source_type": "regulator_standard", "grade": "moderate", "stake": "none", "label": "Standard or regulator"}
    if _matches(host, INDUSTRY) or re.search(r"\b(state of|survey|benchmark report|industry report)\b", title or "", re.IGNORECASE):
        if not _matches(host, VENDORS):
            return {"source_type": "analyst_survey", "grade": "moderate", "stake": "unknown", "label": "Industry report"}
    # S22b: a page that sells (demo, trial, pricing) is a vendor page even when its domain is not listed.
    if _matches(host, VENDORS) or "vendor" in host or selling or _SALES_CUES.search(text or ""):
        return {"source_type": "vendor_blog", "grade": "vendor_claim", "stake": "vendor", "label": "Vendor says"}
    if _matches(host, NEWS):
        return {"source_type": "incident_report", "grade": "weak", "stake": "unknown", "label": "News"}
    return {"source_type": "customer_case_study", "grade": "weak", "stake": "unknown", "label": "Practitioner write-up"}


def resolve_redirect(url: str) -> str:
    """The page a grounding redirect link points to; the link itself when it cannot be resolved."""
    try:
        r = requests.head(url, allow_redirects=True, timeout=8, headers=UA)
        if getattr(r, "url", "") and "grounding-api-redirect" not in r.url:
            return r.url
        r = requests.get(url, allow_redirects=True, timeout=8, headers=UA, stream=True)
        return getattr(r, "url", "") or url
    except Exception:
        return url


def page_date(page: str) -> str:
    """YYYY-MM-DD from a page's publication metadata, or ''."""
    for pat in (r'(?:article:published_time|datePublished|pubdate|publish[-_]?date|dc\.date)["\']?\s*(?:content|:)\s*=?\s*["\']?(\d{4}-\d{2}-\d{2})',
                r'<time[^>]+datetime=["\'](\d{4}-\d{2}-\d{2})'):
        m = re.search(pat, page or "", re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def older_than(date: str, months: int, today: Optional[str] = None) -> bool:
    if not date:
        return False
    try:
        d = datetime.date.fromisoformat(date[:10])
        t = datetime.date.fromisoformat(today) if today else datetime.date.today()
    except ValueError:
        return False
    return (t.year - d.year) * 12 + (t.month - d.month) > months


def is_paywalled(url: str, text: str) -> bool:
    return _matches(_host(url), PAYWALLED) and (len(text or "") < 800 or bool(_PAYWALL_CUES.search(text or "")))


def _terms(text: str) -> set:
    return {w.lower() for w in re.findall(r"[A-Za-z0-9]+", text or "") if len(w) > 2 or w.lower() == "ai"}


def select_passages(text: str, terms: List[str], max_sentences: int = 8) -> List[str]:
    """Sentences sharing two or more of the question's terms, in page order, at most `max_sentences`."""
    want = {t.lower() for t in terms}
    out = []
    for s in re.split(r"(?<=[.!?])\s+", text or ""):
        s = s.strip()
        if 40 <= len(s) <= 400 and len(_terms(s) & want) >= 2:
            out.append(s)
            if len(out) == max_sentences:
                break
    return out


def fetch_page(url: str) -> Tuple[Any, ...]:
    """(title, readable text, YYYY-MM-DD or '', 'html' | 'pdf', selling) for a page; empty text when unreadable."""
    from src.analysis.multilane_runner import readable_text

    r = requests.get(url, timeout=15, headers=UA)
    ctype = (r.headers.get("content-type") or "").lower()
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(r.content[:15_000_000]))
        text = " ".join((p.extract_text() or "") for p in reader.pages[:30])
        title = str((reader.metadata or {}).get("/Title") or "") if reader.metadata else ""
        return title or url.rsplit("/", 1)[-1], " ".join(text.split())[:20000], "", "pdf", False
    page = r.text[:2_000_000]
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
    import html as _html

    title = " ".join(_html.unescape(m.group(1)).split()) if m else url
    return title[:160], readable_text(page)[:20000], page_date(page), "html", page_is_selling(page)


SEARCH_PROMPT = (
    "Find enterprise and practice evidence on this question: {q}\n"
    "Look for industry surveys and reports, engineering and practitioner write-ups, company case studies, regulator "
    "and standards guidance, and company filings. Do not include academic papers. List the sources you used."
)


@dataclass
class GroundedSearch:
    client: Any
    max_calls: int = 5
    max_per_call: int = 5
    max_docs: int = 15
    recency_months: int = 24
    status: str = "not_searched"
    queries: List[str] = field(default_factory=list)
    entry_point: str = ""
    coverage: List[str] = field(default_factory=list)
    error: str = ""

    def run(self, questions: List[str], terms: List[str]) -> List[Dict[str, Any]]:
        """Pages to ingest, newest first: url, title, text passages, date, classification."""
        seen, found = set(), []
        for q in [q for q in questions if q][: self.max_calls]:
            try:
                res = self.client.search_sources(SEARCH_PROMPT.format(q=q))
            except Exception as e:
                self.status, self.error = "searched_error", type(e).__name__
                logger.warning("Grounded search failed (%s)", type(e).__name__)
                break
            self.status = "searched_ok"
            self.queries += [x for x in res.get("queries") or [] if x not in self.queries]
            self.entry_point = self.entry_point or res.get("entry_point") or ""
            for chunk in (res.get("chunks") or [])[: self.max_per_call]:
                if chunk["uri"] not in seen:
                    seen.add(chunk["uri"])
                    found.append(chunk)
        # S22c: pages are resolved and read side by side (5 at a time); results keep the search order.
        from concurrent.futures import ThreadPoolExecutor

        def read(chunk: Dict[str, str]) -> Optional[Dict[str, Any]]:
            url = resolve_redirect(chunk["uri"])
            if classify_source(url, chunk.get("title", ""), "") is None:
                return None
            try:
                res = fetch_page(url)
            except Exception as e:
                logger.warning("Could not read %s (%s)", _host(url), type(e).__name__)
                return None
            title, text, date, fmt = res[:4]
            selling = bool(res[4]) if len(res) > 4 else False
            if is_paywalled(url, text):
                return {"paywalled": _host(url)}
            passages = select_passages(text, terms)
            if not passages:
                return None
            kind = classify_source(url, title, text, selling=selling)
            if kind is None:
                return None
            return {"url": url, "title": title or chunk.get("title", ""), "host": _host(url), "date": date,
                    "format": fmt, "passages": passages, "older": older_than(date, self.recency_months), **kind}

        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(read, found[: self.max_docs * 2]))
        docs: List[Dict[str, Any]] = []
        real = set()
        for d in results:
            if d is None:
                continue
            if "paywalled" in d:
                self.coverage.append(f"Paywalled page not read: {d['paywalled']}")
                continue
            if d["url"] in real or len(docs) >= self.max_docs:
                continue
            real.add(d["url"])
            docs.append(d)
        docs.sort(key=lambda d: (d["older"], d["date"] == ""), reverse=False)
        return docs
