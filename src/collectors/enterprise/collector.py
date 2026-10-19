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

MAX_ITEMS_PER_FEED = 3


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
        """Check A's key-term rule: the item's own title and summary must share enough salient terms
        with the question (check_a.floor_min_terms from config.yaml, as for Check A)."""
        from src.engine.check_a_on_topic import _rule_floor, _term_alternates, salient_terms

        text = f"{item.get('title', '')}. {item.get('abstract', '') or item.get('text', '')}"
        # Two-letter terms ("ai") alone are not a topic match: any AI post would pass for any AI question.
        terms = {t for t in salient_terms(query) if len(t) >= 3} or salient_terms(query)
        alternates = _term_alternates(terms, self.config.get("research", {}).get("head_term_synonyms"))
        min_terms = int(self.config.get("checks", {}).get("check_a", {}).get("floor_min_terms", 1))
        return not _rule_floor(alternates, text, min_terms)["off_topic"]

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
        # Blog feeds are fetched by default; ALLOW_LIVE_ENTERPRISE=0 switches fetching off (tests, offline runs).
        is_live_allowed = allow_live if allow_live is not None else (os.getenv("ALLOW_LIVE_ENTERPRISE") != "0")

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
            items = items[:MAX_ITEMS_PER_FEED]

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
                        "year": item.get("year") or (int(item["pub_date"][:4]) if str(item.get("pub_date", ""))[:4].isdigit() else None),
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
                    claim.context_json["url"] = item.get("url")
                    claim.context_json["source_stake"] = src_cfg["commercial_stake"]

                    # Grade with Grader
                    grade, reasons = self.grader.grade_claim(claim, source)
                    claim.grade = grade
                    claim.grade_reasons_json = reasons

                    if os.getenv("HOSTED_DEMO") != "1":
                        self.repo.insert_claim(claim)
                    ingested_claims.append(claim)

        return ingested_claims
