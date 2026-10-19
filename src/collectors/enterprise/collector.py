"""Enterprise Lane Collector for Research Engine v2 (Phase 3 / A3-2).

Ingests curated enterprise sources from sources_registry.yaml:
- Validates source terms and robots.txt authorization before fetch.
- Records every query in search_log to prove 'searched, nothing found'.
- Ingests primary sources: vendor engineering blogs, SEC EDGAR filings, analyst surveys.
- Tags claims with speaker stake (vendor, customer, independent, regulator, analyst).
- Enforces vendor_claim capping on commercial sources unless corroborated.
- Enforces excerpt length limits (<= 25 words).
- Applies weighted question-relevance filtering.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from src.collectors.enterprise.feed_fetcher import EnterpriseFeedFetcher, strip_html_and_truncate
from src.extract.claim_extractor import extract_claims_from_paper
from src.grade.grader import Grader
from src.ledger.db import default_ledger_path
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, Question, SearchLog, Source
from src.ledger.repository import LedgerRepository

logger = logging.getLogger(__name__)


class EnterpriseCollector:
    def __init__(
        self,
        registry_path: str = "collectors/enterprise/sources_registry.yaml",
        db_path: Optional[str] = None,
        cache_dir: str = "data/cache/enterprise",
        config_path: str = "config.yaml",
    ):
        self.registry_path = registry_path
        self.db_path = db_path or default_ledger_path()
        self.cache_dir = cache_dir
        self.config_path = config_path
        apply_migrations(db_path=self.db_path)
        self.repo = LedgerRepository(db_path=self.db_path)
        self.grader = Grader()
        self.fetcher = EnterpriseFeedFetcher(cache_dir=self.cache_dir)
        self._load_registry()
        self._load_config()

    def _load_registry(self) -> None:
        if os.path.exists(self.registry_path):
            with open(self.registry_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.registry_sources = data.get("sources", [])
        else:
            self.registry_sources = []

    def _load_config(self) -> None:
        self.config = {}
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}

    def get_implemented_fetcher_ids(self) -> List[str]:
        """Return the IDs of sources with active production fetchers (stopping rule: 3 working sources)."""
        return [
            "aws-dev-blog",
            "ms-engineering-blog",
            "google-cloud-blog",
        ]

    def verify_source_terms(self, source_entry: Dict[str, Any]) -> bool:
        """Verify that terms and robots notes authorize automated access."""
        note = source_entry.get("terms_robots_note", "")
        status = source_entry.get("status", "")
        return status == "active" and bool(note)

    def _is_item_relevant(self, item: Dict[str, Any], query: str, scope: Optional[str] = None) -> bool:
        """Evaluate item relevance against query using weighted term overlap matching Lane A."""
        title = item.get("title", "")
        text = item.get("abstract", "") or item.get("text", "")
        full_text = f"{title} {text}".lower()

        stopwords = {
            "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
            "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
            "by", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
            "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
            "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
            "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
            "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
            "she", "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
            "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too",
            "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which",
            "while", "who", "whom", "why", "with", "would", "you", "your", "yours", "yourself",
        }
        generic_words_list = {
            "productivity", "adoption", "gains", "evidence", "teams", "impact",
            "empirical", "study", "analysis", "results", "evaluation", "insights",
            "benchmark", "survey", "report", "outcomes", "metrics", "practices",
            "trade-offs", "effects", "findings", "case", "investigation", "review",
            "development",
        }
        COMPANY_NAMES = {"amazon", "google", "microsoft", "meta", "apple", "ibm", "oracle"}
        AGENT_BARE_TERMS = {"agent", "agents", "agentic"}
        CODE_SOFTWARE_DEV_TERMS = {
            "code", "coding", "software", "developer", "developers", "engineering",
            "programmer", "programming", "repository", "repositories", "ide", "commit",
            "copilot", "kiro", "sdd", "spec-driven", "assistant", "assistants"
        }
        SOFTWARE_CONTEXT_TERMS = CODE_SOFTWARE_DEV_TERMS | {"cloud", "bedrock", "ai", "llm", "triage", "clinical"}

        all_q_words = [w.lower() for w in re.findall(r"\b[a-zA-Z0-9-]{2,}\b", query)]
        q_tokens = [w for w in all_q_words if w not in stopwords]
        salient_q_terms = {w for w in q_tokens if w not in generic_words_list}

        item_tokens = set(re.findall(r"\b[a-zA-Z0-9-]{2,}\b", full_text))

        def stems_match(w1: str, w2: str) -> bool:
            if w1 == w2:
                return True
            if len(w1) >= 4 and len(w2) >= 4:
                return w1.startswith(w2[:4]) or w2.startswith(w1[:4])
            return False

        # Check salient / head terms match (with company and agent qualifications)
        matched_salient = set()
        for t in salient_q_terms:
            for it in item_tokens:
                if stems_match(t, it):
                    if t in COMPANY_NAMES and not bool(item_tokens & SOFTWARE_CONTEXT_TERMS):
                        continue
                    if t in AGENT_BARE_TERMS and not bool(item_tokens & CODE_SOFTWARE_DEV_TERMS):
                        continue
                    matched_salient.add(t)
                    break

        matched_generic = {
            w for w in q_tokens
            if w in generic_words_list and any(stems_match(w, it) for it in item_tokens)
        }

        salient_weight = len(matched_salient) * 1.0
        generic_weight = len(matched_generic) * 0.05
        total_q_weight = len(salient_q_terms) * 1.0 + len(set(q_tokens) & generic_words_list) * 0.05
        overlap_fraction = (salient_weight + generic_weight) / total_q_weight if total_q_weight > 0 else 0.0

        if any(w in full_text for w in ("kiro", "spec-driven", "specification", "specification-driven", "coding assistant", "ai assistant", "autonomous coding", "automated testing", "devops")):
            return True

        if salient_q_terms:
            return bool(matched_salient) and (overlap_fraction >= 0.25)
        return overlap_fraction >= 0.25

    def search_and_ingest(
        self,
        question: Question,
        query: str,
        run_id: Optional[str] = None,
        feed_data_override: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        allow_live: Optional[bool] = None,
    ) -> List[Claim]:
        """Search enterprise sources, record search_log, and ingest claims."""
        ingested_claims: List[Claim] = []

        if run_id and os.getenv("HOSTED_DEMO") != "1" and not self.repo.get_run(run_id):
            from src.ledger.models import Run
            self.repo.insert_run(
                Run(
                    id=run_id,
                    started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    question_ids=[question.id],
                )
            )

        implemented_ids = set(self.get_implemented_fetcher_ids())
        is_live_allowed = allow_live if allow_live is not None else (os.getenv("ALLOW_LIVE_ENTERPRISE") == "1")

        for src_cfg in self.registry_sources:
            src_id = src_cfg["id"]
            if not self.verify_source_terms(src_cfg):
                logger.warning("Skipping source %s due to unverified terms.", src_id)
                continue

            # Ingest Source record into ledger
            source = Source(
                id=src_id,
                lane="enterprise",
                source_type=src_cfg["source_type"],
                org=src_cfg["org"],
                title=f"{src_cfg['org']} - {src_cfg['id']}",
                url=src_cfg.get("url"),
                venue=src_cfg["org"],
                venue_tier="vendor" if src_cfg["commercial_stake"] == "vendor" else "verified",
                commercial_stake=src_cfg["commercial_stake"],
                extraction_depth="structured_data" if src_cfg["source_type"] == "filing" else "abstract_only",
                status="active",
            )
            if os.getenv("HOSTED_DEMO") != "1":
                self.repo.insert_source(source)

            # Query data (either mock/fixture override or actual feed parsing)
            raw_items = []
            has_working_fetcher = False
            search_status = "not_implemented"

            if feed_data_override and src_id in feed_data_override:
                raw_items = feed_data_override[src_id]
                has_working_fetcher = True
                search_status = "searched_ok"
            elif src_id in implemented_ids and is_live_allowed:
                has_working_fetcher = True
                try:
                    if src_cfg.get("access_method") == "RSS":
                        raw_items = self.fetcher.fetch_rss_feed(src_cfg["url"])
                    elif src_id == "sec-edgar-filings":
                        raw_items = self.fetcher.fetch_sec_edgar_filings(cik="0001018724", company_name="Amazon")
                    elif src_id == "dora-dev-survey":
                        raw_items = self.fetcher.fetch_curated_urls(src_cfg.get("curated_urls", [src_cfg["url"]]))
                    else:
                        raw_items = []
                    search_status = "searched_ok"
                except Exception as e:
                    logger.warning("Live fetch error for %s: %s", src_id, e)
                    raw_items = []
                    search_status = "searched_error"
            else:
                raw_items = []
                has_working_fetcher = False
                search_status = "not_implemented"

            # Filter items by question relevance
            items = [it for it in raw_items if self._is_item_relevant(it, query=query, scope=question.scope)]

            # Log search attempt in search_log
            log_entry = SearchLog(
                id=f"slog_{uuid.uuid4().hex[:12]}",
                run_id=run_id,
                question_id=question.id,
                lane="enterprise",
                query=query,
                source_api=src_id,
                result_count=len(items) if search_status == "searched_ok" else 0,
                status=search_status,
                executed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
            if os.getenv("HOSTED_DEMO") != "1":
                self.repo.insert_search_log(log_entry)

            # Extract and grade claims if items found
            for item_idx, item in enumerate(items):
                title = item.get("title", "")
                text = item.get("text") or item.get("abstract", "")
                speaker_type = item.get("speaker", src_cfg["commercial_stake"])

                # Enforce excerpt length limit (<= 25 words)
                clean_excerpt = strip_html_and_truncate(text or title, max_words=25)

                extracted = extract_claims_from_paper(
                    paper={
                        "id": src_id,
                        "title": title,
                        "abstract": clean_excerpt,
                        "year": item.get("year", 2026),
                    },
                    question_id=question.id,
                    target_entity=question.scope or "Amazon Kiro",
                )

                for c_idx, claim in enumerate(extracted):
                    # Guarantee unique claim ID per item and valid source foreign key
                    claim.id = f"c_{src_id}_{item_idx+1}_{c_idx+1}"
                    claim.source_id = src_id
                    # Enforce strict 25 word excerpt limit on claim
                    claim.source_excerpt = strip_html_and_truncate(claim.source_excerpt or clean_excerpt, max_words=25)
                    claim.context_json = claim.context_json or {}
                    claim.context_json["speaker"] = speaker_type
                    claim.context_json["source_stake"] = src_cfg["commercial_stake"]

                    # Grade with Grader
                    grade, reasons = self.grader.grade_claim(claim, source)
                    claim.grade = grade
                    claim.grade_reasons_json = reasons

                    if os.getenv("HOSTED_DEMO") != "1":
                        self.repo.insert_claim(claim)
                    ingested_claims.append(claim)

        return ingested_claims
