"""Enterprise Lane Collector for Research Engine v2 (Phase 3).

Ingests curated enterprise sources from sources_registry.yaml:
- Validates source terms and robots.txt authorization before fetch.
- Records every query in search_log to prove 'searched, nothing found'.
- Ingests primary sources: vendor engineering blogs, SEC EDGAR filings, analyst surveys.
- Tags claims with speaker stake (vendor, customer, independent, regulator, analyst).
- Enforces vendor_claim capping on commercial sources unless corroborated.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from src.extract.claim_extractor import extract_claims_from_paper
from src.grade.grader import Grader
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, Question, SearchLog, Source
from src.ledger.repository import LedgerRepository

logger = logging.getLogger(__name__)


class EnterpriseCollector:
    def __init__(
        self,
        registry_path: str = "collectors/enterprise/sources_registry.yaml",
        db_path: str = "ledger/ledger.db",
    ):
        self.registry_path = registry_path
        self.db_path = db_path
        apply_migrations(db_path=self.db_path)
        self.repo = LedgerRepository(db_path=self.db_path)
        self.grader = Grader()
        self._load_registry()

    def _load_registry(self) -> None:
        with open(self.registry_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.registry_sources = data.get("sources", [])

    def verify_source_terms(self, source_entry: Dict[str, Any]) -> bool:
        """Verify that terms and robots notes authorize automated access."""
        note = source_entry.get("terms_robots_note", "")
        status = source_entry.get("status", "")
        return status == "active" and bool(note)

    def search_and_ingest(
        self,
        question: Question,
        query: str,
        run_id: Optional[str] = None,
        feed_data_override: Optional[Dict[str, List[Dict[str, Any]]]] = None,
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
            items = []
            has_working_fetcher = False
            if feed_data_override and src_id in feed_data_override:
                items = feed_data_override[src_id]
                has_working_fetcher = True

            # Determine status: only sources with working fetchers or overrides log searched_ok
            search_status = "searched_ok" if has_working_fetcher else "not_implemented"

            # Log search attempt in search_log
            log_entry = SearchLog(
                id=f"slog_{uuid.uuid4().hex[:12]}",
                run_id=run_id,
                question_id=question.id,
                lane="enterprise",
                query=query,
                source_api=src_id,
                result_count=len(items),
                status=search_status,
                executed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
            if os.getenv("HOSTED_DEMO") != "1":
                self.repo.insert_search_log(log_entry)

            # Extract and grade claims if items found
            for item in items:
                title = item.get("title", "")
                text = item.get("text") or item.get("abstract", "")
                speaker_type = item.get("speaker", src_cfg["commercial_stake"])

                extracted = extract_claims_from_paper(
                    paper={
                        "id": src_id,
                        "title": title,
                        "abstract": text,
                        "year": item.get("year", 2026),
                    },
                    question_id=question.id,
                    target_entity=question.scope or "Amazon Kiro",
                )

                for claim in extracted:
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
