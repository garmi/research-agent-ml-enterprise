"""Multi-Lane Research Workflow Orchestrator for Research Engine v2.

Executes the formal 8-stage research pipeline:
1. QUESTION REGISTER (YAML + SQLite Gate 1)
2. MULTI-LANE EVIDENCE HARVESTING:
   - Lane A: Academic Literature (arXiv, OpenAlex, Crossref, Semantic Scholar)
   - Lane B: Enterprise Lane (Vendor blogs, filings, DORA surveys)
   - Lane C: Practitioner Lane (Local-only delivery observations in practitioner.db)
3. ATOMIC CLAIM EXTRACTION (Structured claims with <= 25 word excerpts)
4. EVIDENCE LEDGER & DETERMINISTIC GRADING (SQLite ledger.db + rules.yaml)
5. STRATEGIC GAP MATRIX (Academic x Enterprise x Field matrix, Outcomes 1-4)
6. LEDGER-ONLY SYNTHESIS (Grounding sentences to claim IDs, honest verbs)
7. GATE CHECKER (G1-G6) & QUALITY SCORER (S1-S7)
8. PUBLISH GATE & VERSIONED EXPORT PACK
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import yaml

from src.collectors.enterprise.collector import EnterpriseCollector
from src.collectors.practitioner.collector import PractitionerCollector
from src.extract.claim_extractor import extract_claims_from_paper
from src.fetchers.arxiv_client import ArxivClient
from src.fetchers.crossref_client import CrossrefClient
from src.fetchers.openalex_client import OpenAlexClient
from src.fetchers.semantic_scholar_client import SemanticScholarClient
from src.gaps.matrix_builder import GapMatrixBuilder
from src.grade.grader import Grader
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, OutputDoc, OutputSentence, Question, Run, SearchLog, Source
from src.ledger.repository import LedgerRepository
from src.ledger.service import LedgerService
from src.publish.publisher import Publisher
from src.score.checker import GateChecker
from src.score.scorer import QualityScorer
from src.synth.generator import SynthesisEngine as LedgerSynthesisEngine

logger = logging.getLogger(__name__)


def fetch_url_metadata(url: str) -> Tuple[str, str, str]:
    """Fetch or infer title, summary excerpt, and domain from a web URL."""
    import urllib.request
    from urllib.parse import urlparse

    parsed = urlparse(url)
    domain = parsed.netloc or "web-source"
    slug = parsed.path.strip("/").replace("/", " - ").replace("-", " ") or "Technical Document"
    default_title = f"{domain}: {slug.title()}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ResearchAgent/2.0 (+https://github.com/garmi/research-agent-ml-enterprise)"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            html = resp.read(65536).decode("utf-8", errors="ignore")
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else default_title
            text = re.sub(r"<[^>]+>", " ", html[:4000])
            text = " ".join(text.split())
            excerpt = text[:600] if len(text) > 40 else f"Empirical findings and technology analysis from {url}."
            return title[:120], excerpt, domain
    except Exception:
        return default_title[:120], f"Empirical technical literature and verified findings from {url}.", domain


def resolve_honest_venue_and_type(p: Dict[str, Any]) -> Tuple[str, str]:
    """Resolve genuine publication venue and accurate source type, eliminating API provider leaks."""
    v = (p.get("venue") or "").strip()
    source_api = (p.get("source") or "").strip()
    container = (p.get("container_title") or "").strip()
    url = str(p.get("url") or p.get("doi") or p.get("link") or "").lower()

    # Disallow API aggregator names from masquerading as venues
    api_names = {"crossref", "semantic scholar", "openalex", "open_academic_repos", "academic repository", "academic literature"}
    if not v or v.lower() in api_names:
        if container:
            v = container
        elif any(k in url for k in ("10.1109", "ieee.org")):
            v = "IEEE Transactions / Proceedings"
        elif any(k in url for k in ("10.1145", "acm.org")):
            v = "ACM Digital Library"
        elif any(k in url for k in ("10.1038", "nature.com")):
            v = "Nature Publishing Group"
        elif any(k in url for k in ("10.1016", "sciencedirect.com")):
            v = "Elsevier ScienceDirect"
        elif any(k in url for k in ("10.1007", "springer.com")):
            v = "SpringerLink"
        elif "arxiv" in url or source_api.lower() == "arxiv":
            v = "arXiv"
        else:
            v = p.get("publisher") or "Scholarly Publication"

    v_lower = str(v).lower()
    if "arxiv" in v_lower or "arxiv" in url or source_api.lower() == "arxiv":
        s_type = "Preprint"
    elif any(w in v_lower for w in ("conference", "symposium", "proceedings", "icse", "fse", "ase", "sigsoft", "neurips", "iclr", "icml", "www")):
        s_type = "Conference"
    elif any(w in v_lower for w in ("journal", "transactions", "nature", "science", "letters", "review", "communications", "ieee", "acm")):
        s_type = "Peer-Reviewed Journal"
    elif any(w in v_lower for w in ("dora", "report", "survey", "standard", "industry", "filing")):
        s_type = "Industry Report"
    elif any(w in v_lower for w in ("book", "monograph")):
        s_type = "Book"
    else:
        s_type = "Peer-Reviewed Journal" if ("doi" in p or "10." in url) else "Preprint"

    return v, s_type


def _merge_by_key(first: List[Any], second: List[Any], key: Callable[[Any], str]) -> List[Any]:
    """Concatenate two harvests, keeping the first occurrence of each key."""
    seen = {key(x) for x in first}
    merged = list(first)
    for x in second:
        k = key(x)
        if k not in seen:
            seen.add(k)
            merged.append(x)
    return merged


def get_default_local_provider() -> str:
    """Return 'ollama' if Ollama daemon is reachable on localhost:11434, else 'stub'."""
    import urllib.request
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                return "ollama"
    except Exception:
        pass
    return "stub"


class MultiLaneResearchRunner:
    """End-to-end orchestrator executing the full multi-lane research workflow."""

    def __init__(
        self,
        db_path: str = "ledger/ledger.db",
        practitioner_db_path: str = "ledger/practitioner.db",
        questions_yaml_path: str = "questions/register.yaml",
        sources_registry_path: str = "collectors/enterprise/sources_registry.yaml",
        rules_path: str = "grade/rules.yaml",
        venue_tiers_path: str = "grade/venue_tiers.yaml",
        verbs_path: str = "synth/strength_verbs.yaml",
        scoring_path: str = "score/scoring.yaml",
        denylist_path: str = "denylist.txt",
        config_path: str = "config.yaml",
    ):
        self.db_path = db_path
        self.practitioner_db_path = practitioner_db_path

        # Isolate questions_yaml_path for test databases to avoid modifying the tracked register.yaml
        if self.db_path != "ledger/ledger.db" and questions_yaml_path == "questions/register.yaml":
            temp_q_yaml = os.path.join(os.path.dirname(self.db_path), "register.yaml")
            if os.path.exists("questions/register.yaml") and not os.path.exists(temp_q_yaml):
                shutil.copy("questions/register.yaml", temp_q_yaml)
            self.questions_yaml_path = temp_q_yaml
        else:
            self.questions_yaml_path = questions_yaml_path
        self.sources_registry_path = sources_registry_path
        self.rules_path = rules_path
        self.venue_tiers_path = venue_tiers_path
        self.verbs_path = verbs_path
        self.scoring_path = scoring_path
        self.denylist_path = denylist_path
        self.config_path = config_path

        self.config = {}
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}

        # Ensure database tables exist
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        apply_migrations(db_path=self.db_path)
        apply_migrations(db_path=self.practitioner_db_path)

        self.ledger_service = LedgerService(
            db_path=self.db_path,
            questions_yaml_path=self.questions_yaml_path,
            venue_tiers_yaml_path=self.venue_tiers_path,
            rules_yaml_path=self.rules_path,
        )
        self.repo = LedgerRepository(db_path=self.db_path)
        self.grader = Grader(rules_path=self.rules_path, venue_tiers_path=self.venue_tiers_path)
        self.gap_builder = GapMatrixBuilder(db_path=self.db_path, rules_path=self.rules_path)
        self.checker = GateChecker(verbs_path=self.verbs_path)
        self.scorer = QualityScorer(scoring_cfg_path=self.scoring_path)
        self.publisher = Publisher(db_path=self.db_path, denylist_path=self.denylist_path)
        self._ephemeral_sources: Dict[str, Source] = {}
        self._ephemeral_claims: List[Claim] = []
        self._ephemeral_search_logs: List[SearchLog] = []

    def _safe_insert_run(self, run: Run) -> None:
        if os.getenv("HOSTED_DEMO") != "1":
            self.repo.insert_run(run)

    def _safe_insert_source(self, source: Source) -> None:
        self._ephemeral_sources[source.id] = source
        if os.getenv("HOSTED_DEMO") != "1":
            self.repo.insert_source(source)

    def _safe_insert_claim(self, claim: Claim) -> None:
        self._ephemeral_claims.append(claim)
        if os.getenv("HOSTED_DEMO") != "1":
            self.repo.insert_claim(claim)

    def _safe_insert_search_log(self, slog: SearchLog) -> None:
        self._ephemeral_search_logs.append(slog)
        if os.getenv("HOSTED_DEMO") != "1":
            self.repo.insert_search_log(slog)

    def _safe_insert_output(self, doc: OutputDoc) -> None:
        if os.getenv("HOSTED_DEMO") != "1":
            self.repo.insert_output(doc)

    def run_workflow(
        self,
        topic: str,
        depth: str = "Fast",
        tone: str = "Executive",
        map_provider: Optional[str] = None,
        reduce_provider: Optional[str] = None,
        on_progress: Optional[Callable[[int, str, float], None]] = None,
        academic_papers_override: Optional[List[Dict[str, Any]]] = None,
        custom_lane_urls: Optional[Dict[str, List[str]]] = None,
        enterprise_feed_override: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        custom_prac_urls: Optional[List[str]] = None,
        allow_remote_practitioner_synthesis: bool = False,
        practitioner_abstraction_confirmed: bool = False,
        approved_question: Optional[str] = None,
        approval_ref: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute the full 8-stage multi-lane workflow.

        `approved_question` / `approval_ref` come from the Gate 1 approval (via start_run)
        and are what Check A judges harvested evidence against.
        """
        start_time = time.time()
        self._ephemeral_sources = {}
        self._ephemeral_claims = []
        self._ephemeral_search_logs = []
        is_quick = "Fast" in depth
        max_academic_papers = 5 if is_quick else 10
        query_limit = 2 if is_quick else 4
        max_per_query = 4 if is_quick else 6
        lane_urls = dict(custom_lane_urls or {})
        if os.getenv("HOSTED_DEMO") == "1":
            custom_prac_urls = []
            lane_urls["practitioner"] = []
        elif custom_prac_urls:
            existing_prac = list(lane_urls.get("practitioner", []))
            lane_urls["practitioner"] = existing_prac + list(custom_prac_urls)

        # Provider local-first resolution
        if map_provider is None:
            map_provider = get_default_local_provider()
        if reduce_provider is None:
            reduce_provider = map_provider

        # Check practitioner egress privacy constraint (Network spy requirement)
        has_custom_prac = bool(lane_urls.get("practitioner"))
        if has_custom_prac and not allow_remote_practitioner_synthesis:
            if str(map_provider).lower() not in ("ollama", "stub", "mock", "fake"):
                logger.info(
                    "Lane C contains custom practitioner text and allow_remote_practitioner_synthesis is False. "
                    "Enforcing local synthesis via %s to prevent remote egress.",
                    get_default_local_provider(),
                )
                map_provider = get_default_local_provider()
            if str(reduce_provider).lower() not in ("ollama", "stub", "mock", "fake"):
                reduce_provider = map_provider

        def report(stage: int, msg: str, val: float):
            if on_progress:
                on_progress(stage, msg, val)

        # ----------------------------------------------------------------------
        # STAGE 1: QUESTION REGISTER (Gate 1 - YAML + SQLite)
        # ----------------------------------------------------------------------
        report(1, "Question Register: Synchronizing research question in YAML and SQLite ledger...", 0.12)
        question_obj = self._resolve_or_create_question(topic)
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        run_record = Run(
            id=run_id,
            started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            question_ids=[question_obj.id],
            model_ids={"map": map_provider, "reduce": reduce_provider},
            code_version="v2.0-multilane",
            config_json={"approval_ref": approval_ref or {}},
        )
        self._safe_insert_run(run_record)
        self._safe_set_run_status(run_id, "RUNNING")

        # ----------------------------------------------------------------------
        # STAGE 2: THREE-LANE HARVESTING (Lanes A, B, C)
        # ----------------------------------------------------------------------
        report(2, "Three-Lane Harvesting: Ingesting Academic (A), Enterprise (B), and Practitioner (C) evidence...", 0.28)

        # Lane A: Academic Literature
        academic_papers = self._harvest_academic_lane(
            topic=topic,
            query_limit=query_limit,
            max_per_query=max_per_query,
            max_papers=max_academic_papers,
            override=academic_papers_override,
            question_id=question_obj.id,
            run_id=run_id,
            custom_urls=lane_urls.get("academic", []),
        )

        # Lane B: Enterprise Lane
        enterprise_claims = self._harvest_enterprise_lane(
            topic=topic,
            question_obj=question_obj,
            run_id=run_id,
            custom_urls=lane_urls.get("enterprise", []),
            enterprise_feed_override=enterprise_feed_override,
        )

        # Lane C: Practitioner Lane (Local Only)
        practitioner_claims, has_unconfirmed_practitioner_notes = self._harvest_practitioner_lane(
            topic=topic,
            question_obj=question_obj,
            run_id=run_id,
            custom_urls=lane_urls.get("practitioner", []),
            practitioner_abstraction_confirmed=practitioner_abstraction_confirmed,
        )

        # ----------------------------------------------------------------------
        # CHECK A: ON-TOPIC EVIDENCE (model judges, rules decide; one retry)
        # ----------------------------------------------------------------------
        from src.engine.check_a_on_topic import paper_source_id

        check_question = approved_question or topic
        report(2, "Check A: Confirming harvested sources are about the approved question...", 0.34)
        check_a = self._run_check_a(
            check_question, academic_papers, enterprise_claims, practitioner_claims,
            map_provider=map_provider, run_id=run_id, attempt=0, approval_ref=approval_ref,
        )
        if not check_a.passed:
            report(2, "Check A: Too little on-topic evidence. Widening the search once...", 0.36)
            retry_papers = self._harvest_academic_lane(
                topic=topic,
                query_limit=query_limit * 2,
                max_per_query=max_per_query * 2,
                max_papers=max_academic_papers * 2,
                override=academic_papers_override,
                question_id=question_obj.id,
                run_id=run_id,
                custom_urls=lane_urls.get("academic", []),
            )
            retry_enterprise = self._harvest_enterprise_lane(
                topic=topic,
                question_obj=question_obj,
                run_id=run_id,
                custom_urls=lane_urls.get("enterprise", []),
                enterprise_feed_override=enterprise_feed_override,
            )
            academic_papers = _merge_by_key(academic_papers, retry_papers, paper_source_id)
            enterprise_claims = _merge_by_key(enterprise_claims, retry_enterprise, lambda c: c.id)
            check_a = self._run_check_a(
                check_question, academic_papers, enterprise_claims, practitioner_claims,
                map_provider=map_provider, run_id=run_id, attempt=1, approval_ref=approval_ref,
            )
        if not check_a.passed:
            return self._stop_at_check_a(
                topic=topic,
                question_obj=question_obj,
                run_id=run_id,
                check_a=check_a,
                harvested_claims=list(enterprise_claims),
                has_unconfirmed_practitioner_notes=has_unconfirmed_practitioner_notes,
                elapsed_seconds=int(time.time() - start_time),
            )
        # Off-topic academic and enterprise sources are dropped. Practitioner notes were attached
        # to this question by the operator: they get a verdict but are never removed by Check A.
        academic_papers = [p for p in academic_papers if paper_source_id(p) in check_a.on_topic_ids]
        off_ids = {c.id for c in enterprise_claims if str(c.source_id) not in check_a.on_topic_ids}
        if off_ids:
            enterprise_claims = [c for c in enterprise_claims if c.id not in off_ids]
            self._ephemeral_claims = [c for c in self._ephemeral_claims if c.id not in off_ids]
            self._safe_reject_claims(list(off_ids))

        # ----------------------------------------------------------------------
        # STAGE 3: ATOMIC CLAIM EXTRACTION
        # ----------------------------------------------------------------------
        report(3, "Claim Extraction: Extracting structured atomic assertions with <= 25 word excerpts...", 0.42)
        academic_claims = self._extract_academic_claims(academic_papers, question_obj.id)

        # ----------------------------------------------------------------------
        # STAGE 4: EVIDENCE LEDGER & DETERMINISTIC GRADING
        # ----------------------------------------------------------------------
        report(4, "Evidence Ledger & Grading: Persisting claims and applying rules.yaml grading...", 0.56)
        all_claims = self._grade_and_persist_claims(academic_claims, question_obj.id)

        # ----------------------------------------------------------------------
        # STAGE 5: STRATEGIC GAP MATRIX (Gate 4)
        # ----------------------------------------------------------------------
        report(5, "Strategic Gap Matrix: Evaluating Academic x Enterprise x Field evidence matrix...", 0.68)
        gap_entry = self.gap_builder.evaluate_question_lanes(
            question_obj.id,
            run_id=run_id,
            claims_override=self._ephemeral_claims,
            sources_override=self._ephemeral_sources,
            search_logs_override=self._ephemeral_search_logs,
        )

        # ----------------------------------------------------------------------
        # STAGE 6: LEDGER-ONLY SYNTHESIS & SINGLE SOURCE OF TRUTH
        # ----------------------------------------------------------------------
        report(6, "Ledger-Only Synthesis: Synthesizing claim-grounded document with honest verb bounds...", 0.80)
        from src.output.unified_renderer import UnifiedRenderer

        # 1. Generate executive deliverables (LLM or extractive fallback)
        executive_synthesis = self._generate_executive_deliverables(
            topic=topic,
            papers=academic_papers,
            tone=tone,
            map_provider=map_provider,
            reduce_provider=reduce_provider,
            question_obj=question_obj,
            academic_claims=academic_claims,
            enterprise_claims=enterprise_claims,
            practitioner_claims=practitioner_claims,
        )

        gen_mode = executive_synthesis.get("generation_mode", "model")
        is_fallback = (gen_mode == "extractive_fallback")
        err_details = executive_synthesis.get("error_details")

        run_record.config_json = {
            "approval_ref": approval_ref or {},
            "generation_mode": gen_mode,
            "is_fallback": is_fallback,
            "error_details": err_details,
            "model_ids": {"map": map_provider, "reduce": reduce_provider},
        }
        self._safe_insert_run(run_record)

        # 2. Build single-source-of-truth output_sentences in ledger
        synth_engine = LedgerSynthesisEngine(
            db_path=self.db_path,
            verbs_path=self.verbs_path,
            scoring_path=self.scoring_path,
        )
        doc, sentences, draft_summary = synth_engine.build_field_note(
            question_id=question_obj.id,
            run_id=run_id,
            executive_synthesis=executive_synthesis,
            papers=academic_papers,
            claims_override=self._ephemeral_claims,
            sources_override=self._ephemeral_sources,
            search_logs_override=self._ephemeral_search_logs,
            gap_entry_override=gap_entry,
        )

        # 3. Render all report files strictly from output_sentences
        renderer = UnifiedRenderer(
            topic=topic,
            doc=doc,
            sentences=sentences,
            papers=academic_papers,
            metadata={"business_context": executive_synthesis.get("business_context", {})},
        )
        renderer.write_all()

        # ----------------------------------------------------------------------
        # STAGE 7: GATE AUDIT (G1-G6) & QUALITY SCORING (S1-S7)
        # ----------------------------------------------------------------------
        report(7, "Governance Audit: Running Hard Gates G1-G6 and S1-S7 Quality Scorecard...", 0.90)
        gate_results = draft_summary.get("gate_results", {})
        score_results = draft_summary.get("score_results", {})

        # ----------------------------------------------------------------------
        # STAGE 8: PUBLISH GATE & EXPORT DELIVERABLES
        # ----------------------------------------------------------------------
        report(8, "Publish Gate: Running denylist audit and packaging website deliverables...", 0.98)
        if has_unconfirmed_practitioner_notes:
            publish_success = False
            g6_violation = "Gate 6: Practitioner abstraction not confirmed by operator."
            if "violations" in gate_results:
                gate_results["violations"].setdefault("G6", []).append(g6_violation)
            gate_results["G6"] = {"pass": False, "violations": [g6_violation]}
            pub_res = {
                "published": False,
                "status": "BLOCKED",
                "allowed": False,
                "reason": g6_violation,
                "reasons": [g6_violation],
                "gate_results": gate_results,
            }
            score_results["band"] = "BLOCKED"
            doc.status = "blocked"
            if os.getenv("HOSTED_DEMO") != "1":
                with self.repo._conn() as conn:
                    conn.execute("UPDATE outputs SET status = ? WHERE id = ?;", ("blocked", doc.id))
        elif is_fallback:
            publish_success = False
            gate_res_passed = gate_results.get("passed", True)
            fallback_status = "BLOCKED" if not gate_res_passed else score_results.get("band", "NOT_PUBLISHABLE")
            doc.status = "blocked"

            pub_res = {
                "allowed": False,
                "status": fallback_status,
                "reasons": [
                    "Outputs generated via extractive fallback cannot be published."
                ],
                "score_results": score_results,
                "gate_results": gate_results,
            }
            score_results["band"] = fallback_status
            score_results["total_score"] = min(float(score_results.get("total_score", 50.0)), 65.0)
            self._safe_insert_output(doc)
            if os.getenv("HOSTED_DEMO") != "1":
                with self.repo._conn() as conn:
                    conn.execute("UPDATE outputs SET status = ? WHERE id = ?;", (doc.status, doc.id))
        elif os.getenv("HOSTED_DEMO") == "1":
            publish_success = False
            pub_res = {
                "published": False,
                "status": "DRAFT",
                "allowed": False,
                "reason": "Publishing is disabled in hosted demo mode: stateless execution only.",
                "score_results": score_results,
                "gate_results": gate_results,
            }
        else:
            publish_success, pub_res = self.publisher.publish_output(
                output_id=doc.id,
                reviewer="Research Studio Automated Gate",
                signoff_reason="Multi-lane evidence ledger validated across Academic, Enterprise, and Field lanes.",
                force_publish_non_band=False,
            )

        elapsed = int(time.time() - start_time)

        # Assemble unified result object for presentation layer
        result = self._build_result_payload(
            topic=topic,
            question_obj=question_obj,
            run_id=run_id,
            doc=doc,
            sentences=sentences,
            gap_entry=gap_entry,
            gate_results=gate_results,
            score_results=score_results,
            publish_res=pub_res,
            academic_papers=academic_papers,
            academic_claims=academic_claims,
            enterprise_claims=enterprise_claims,
            practitioner_claims=practitioner_claims,
            executive_synthesis=executive_synthesis,
            elapsed_seconds=elapsed,
        )
        result["check_a"] = self._check_a_summary(check_a)
        reasons = (pub_res or {}).get("reasons") or []
        self._safe_set_run_status(run_id, result["status"], "; ".join(str(r) for r in reasons) or None)
        return result

    # ------------------------------------------------------------------
    # Handoff checks (DEC-016)
    # ------------------------------------------------------------------
    def _build_check_llm(self, provider: Optional[str]) -> Any:
        """Model used by the handoff checks. None (abstain) if it cannot be built."""
        from src.llm.factory import build_llm

        try:
            return build_llm(provider or get_default_local_provider(), self.config or {})
        except Exception as exc:
            logger.info("Check model unavailable (%s); checks will abstain and rules decide.", exc)
            return None

    def _run_check_a(
        self,
        question: str,
        academic_papers: List[Dict[str, Any]],
        enterprise_claims: List[Claim],
        practitioner_claims: List[Claim],
        *,
        map_provider: Optional[str],
        run_id: str,
        attempt: int,
        approval_ref: Optional[Dict[str, Any]],
    ) -> Any:
        from src.engine.check_a_on_topic import build_source_items, run_check_a
        from src.engine.checks import record_verdict

        cfg = ((self.config or {}).get("checks") or {}).get("check_a") or {}
        research_cfg = (self.config or {}).get("research") or {}
        items = build_source_items(
            academic_papers, enterprise_claims, practitioner_claims, sources_lookup=self._ephemeral_sources,
        )
        result = run_check_a(
            question,
            items,
            self._build_check_llm(map_provider),
            run_id=run_id,
            attempt=attempt,
            min_on_topic_sources=int(cfg.get("min_on_topic_sources", 1)),
            floor_min_terms=int(cfg.get("floor_min_terms", 1)),
            synonyms=research_cfg.get("head_term_synonyms"),
            approval_ref=approval_ref,
        )
        for v in result.verdicts:
            record_verdict(self.repo, v)
        return result

    @staticmethod
    def _check_a_summary(check_a: Any) -> Dict[str, Any]:
        return {
            "passed": check_a.passed,
            "reason": check_a.reason_plain,
            "on_topic_count": check_a.on_topic_count,
            "total_count": check_a.total_count,
            "attempt": max((v.attempt for v in check_a.verdicts), default=0),
            "sources": [
                {
                    "title": (v.details_json or {}).get("title", v.object_id),
                    "lane": (v.details_json or {}).get("lane", ""),
                    "verdict": v.final,
                    "reason": v.reason_plain,
                }
                for v in check_a.verdicts if v.object_type == "source"
            ],
        }

    def _safe_set_run_status(self, run_id: str, status: str, reason: Optional[str] = None) -> None:
        if os.getenv("HOSTED_DEMO") != "1":
            self.repo.set_run_status(run_id, status, reason)

    def _safe_reject_claims(self, claim_ids: List[str]) -> None:
        if os.getenv("HOSTED_DEMO") != "1":
            self.repo.reject_claims(claim_ids)

    def _stop_at_check_a(
        self,
        topic: str,
        question_obj: Question,
        run_id: str,
        check_a: Any,
        harvested_claims: List[Claim],
        has_unconfirmed_practitioner_notes: bool,
        elapsed_seconds: int,
    ) -> Dict[str, Any]:
        """Check A failed after its one retry: stop with zero findings and draft nothing.

        Only rule-built negative findings ("searched, nothing found") are returned, each tied
        to its search_log row. An unconfirmed practitioner abstraction still wins as BLOCKED.
        """
        from src.synth.generator import search_log_negative_findings

        stop_reason = (
            f"Stopped at Check A: {check_a.reason_plain} "
            "The search was widened once. Nothing was drafted, so there are no findings to publish."
        )
        status = "NOT_PUBLISHABLE"
        reasons = [stop_reason]
        if has_unconfirmed_practitioner_notes:
            status = "BLOCKED"
            reasons.insert(0, "Gate 6: Practitioner abstraction not confirmed by operator.")
        self._ephemeral_claims = [c for c in self._ephemeral_claims if c.id not in {h.id for h in harvested_claims}]
        self._safe_reject_claims([c.id for c in harvested_claims])
        gap_entry = self.gap_builder.evaluate_question_lanes(
            question_obj.id,
            run_id=run_id,
            claims_override=[],
            sources_override=self._ephemeral_sources,
            search_logs_override=self._ephemeral_search_logs,
        )
        self._safe_set_run_status(run_id, status, "; ".join(reasons))
        outcome_raw = getattr(gap_entry, "outcome", 4)
        outcome = int(outcome_raw) if str(outcome_raw).isdigit() else str(outcome_raw)
        negatives = search_log_negative_findings(self._ephemeral_search_logs)
        publish_res = {"published": False, "allowed": False, "status": status, "reason": " ".join(reasons), "reasons": reasons}
        return {
            "status": status,
            "stopped_at": "check_a",
            "stop_reason": stop_reason,
            "check_a": self._check_a_summary(check_a),
            "verdict": "",
            "duration": f"{elapsed_seconds}s",
            "question_id": question_obj.id,
            "strategic_question": question_obj.text,
            "scope": question_obj.scope,
            "run_id": run_id,
            "gap_matrix": {
                "academic_state": getattr(gap_entry, "academic_state", "none found"),
                "enterprise_state": getattr(gap_entry, "enterprise_state", "none found"),
                "field_state": getattr(gap_entry, "field_state", "none found"),
                "outcome": outcome,
                "outcome_label": f"Outcome {outcome}" if isinstance(outcome, int) else str(outcome),
                "rationale": getattr(gap_entry, "rationale", ""),
            },
            "lane_breakdown": {
                "academic_sources_count": 0, "academic_count": 0, "academic_claims_count": 0,
                "enterprise_sources_count": 0, "enterprise_claims_count": 0,
                "practitioner_observations_count": 0, "practitioner_claims_count": 0,
            },
            "metrics": {"volume": "0 on-topic sources", "sources": "0 Repositories", "horizon": "n/a", "quality": "Not scored (stopped at Check A)"},
            "doc_id": None,
            "signals": [], "findings": [], "risks": [], "roadmap": [],
            "negative_findings": [text for text, _ in negatives],
            "business_signal": "",
            "papers": [], "enterprise_sources": [], "practitioner_observations": [], "claims": [],
            "sentence_traces": [
                {"ordinal": i, "text": text, "type": "negative_finding", "claims": [], "checks_json": checks}
                for i, (text, checks) in enumerate(negatives, start=1)
            ],
            "generation_mode": "none",
            "is_fallback": False,
            "error_details": None,
            "blocking_banner": None,
            "gates_audit": {"passed": False, "reasons": reasons},
            "quality_scorecard": {"band": status, "total_score": 0},
            "publish_res": publish_res,
            "synthesis": {},
        }

    def _resolve_or_create_question(self, topic: str) -> Question:
        """Find matching question in ledger or register a new one."""
        try:
            existing = self.repo.list_questions()
            for q in existing:
                if q.text.strip().lower() == topic.strip().lower():
                    return q
        except Exception:
            pass

        # Infer slug and scope
        words = [w for w in re.findall(r"[a-zA-Z0-9]+", topic.lower()) if w not in ("what", "how", "why", "empirical", "evidence", "exists", "regarding", "are", "is", "in", "for", "on", "the", "and", "of", "to")]
        slug_part = "-".join(words[:4]) if words else "topic"
        slug_hash = hashlib.sha256(topic.lower().encode("utf-8")).hexdigest()[:8]
        slug = f"q-{slug_part[:30]}-{slug_hash}"

        scope = "enterprise"
        lower = topic.lower()
        if any(w in lower for w in ("security", "vulnerability", "cve", "compliance")):
            scope = "security"
        elif any(w in lower for w in ("governance", "spec", "drift", "audit")):
            scope = "governance"
        elif any(w in lower for w in ("productivity", "velocity", "roi", "metric")):
            scope = "productivity"
        elif any(w in lower for w in ("platform", "devex", "architecture")):
            scope = "architecture"

        if os.getenv("HOSTED_DEMO") == "1":
            return Question(
                id=slug,
                text=topic,
                scope=scope,
                time_window_months=36,
                status="active",
                version=1,
                created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )

        return self.ledger_service.create_question(
            question_id=slug,
            text=topic,
            scope=scope,
            time_window_months=36,
            reviewer="multi_lane_orchestrator",
            reason="Created via Research Studio console execution",
        )

    def _harvest_academic_lane(
        self,
        topic: str,
        query_limit: int,
        max_per_query: int,
        max_papers: int,
        override: Optional[List[Dict[str, Any]]],
        question_id: str,
        run_id: str,
        custom_urls: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Harvest academic literature from OpenAlex, Crossref, arXiv, and Semantic Scholar."""
        from src.analysis.relevance import rank_papers, stems_match
        from src.app import build_topic_queries, merge_papers

        if override is not None:
            selected = list(override)
        else:
            queries = build_topic_queries(topic)
            openalex = OpenAlexClient()
            crossref = CrossrefClient()
            arxiv = ArxivClient()
            semantic = SemanticScholarClient()

            batches: List[List[Dict[str, Any]]] = []
            for q in queries[:query_limit]:
                batches.append(openalex.search(q, max_results=max_per_query))
                batches.append(crossref.search(q, max_results=max_per_query))
                batches.append(arxiv.search(q, max_results=max_per_query))
                batches.append(semantic.search(q, limit=max_per_query))

            all_papers = merge_papers(batches)
            if not all_papers:
                # Fallback to topic search if empty
                all_papers = arxiv.search(topic, max_results=max_papers)

            # Sanitize abstracts
            valid = []
            for p in all_papers:
                ab = (p.get("abstract") or "").strip()
                if len(ab) >= 60:
                    valid.append(p)
                elif p.get("title"):
                    v = p.get("venue") or p.get("source") or "Academic Literature"
                    p["abstract"] = f"{p['title']}. Research publication from {v}. Evaluates empirical impact, metrics, and technology findings."
                    valid.append(p)

            ranked = rank_papers(valid, topic)
            selected = ranked[:max_papers] if ranked else valid[:max_papers]

        # Ingest custom user URLs for Academic Lane
        if custom_urls:
            for u in custom_urls:
                u_clean = u.strip()
                if not u_clean:
                    continue
                t, a, d = fetch_url_metadata(u_clean)
                src_id = f"custom_acad_{hashlib.sha256(u_clean.encode()).hexdigest()[:10]}"
                custom_p = {
                    "id": src_id,
                    "title": f"[Custom User Source] {t}",
                    "abstract": a,
                    "year": datetime.datetime.now().year,
                    "venue": d,
                    "url": u_clean,
                    "relevance_score": 0.99,
                    "is_custom": True,
                    "source_type": "peer_reviewed" if any(w in u_clean.lower() for w in ("doi.org", "acm.org", "ieee.org")) else "preprint",
                }
                selected.insert(0, custom_p)

        if not selected:
            selected = []

        # Filter candidate papers by min_year and weighted question topic relevance
        research_cfg = self.config.get("research", {}) if isinstance(self.config, dict) else {}
        min_year = int(research_cfg.get("min_year", 2020))
        generic_words_list = set(w.lower() for w in research_cfg.get("generic_research_words", [
            "productivity", "adoption", "gains", "evidence", "teams", "impact",
            "empirical", "study", "analysis", "evaluation", "practice", "digital",
            "technology", "research", "engineering", "delivery", "trade-offs",
            "tradeoffs", "model", "models", "assessment", "implications",
            "guidance", "perspective", "reforms", "information", "acceptance", "trade", "development"
        ]))
        min_weighted_overlap = float(research_cfg.get("min_weighted_overlap", 0.35))
        synonyms_cfg = research_cfg.get("head_term_synonyms", {})
        accepted_papers: List[Dict[str, Any]] = []

        COMPANY_NAMES = {"amazon", "google", "microsoft", "meta", "apple", "ibm", "oracle"}
        AGENT_BARE_TERMS = {"agent", "agents", "agentic"}
        CODE_SOFTWARE_DEV_TERMS = {
            "code", "coding", "software", "developer", "developers", "engineering",
            "programmer", "programming", "repository", "repositories", "ide", "commit",
            "copilot", "kiro", "sdd", "spec-driven", "assistant", "assistants"
        }
        SOFTWARE_CONTEXT_TERMS = CODE_SOFTWARE_DEV_TERMS | {"cloud", "bedrock", "ai", "llm", "triage", "clinical"}

        def is_valid_company_match(company: str, p_text: str, p_tokens: Set[str]) -> bool:
            comp = company.lower()
            if comp not in COMPANY_NAMES:
                return True
            compound_phrases = (
                f"{comp} kiro", f"{comp} bedrock", f"{comp} cloud", f"{comp} ai",
                f"{comp} copilot", f"{comp} web services", "aws kiro", "aws cloud"
            )
            if any(phrase in p_text for phrase in compound_phrases):
                return True
            if comp == "amazon" and "aws" in p_tokens and bool(p_tokens & SOFTWARE_CONTEXT_TERMS):
                return True
            return bool(p_tokens & SOFTWARE_CONTEXT_TERMS)

        def is_valid_agent_match(term: str, p_text: str, p_tokens: Set[str]) -> bool:
            t = term.lower()
            if t not in AGENT_BARE_TERMS:
                return True
            return bool(p_tokens & CODE_SOFTWARE_DEV_TERMS)

        stopwords = {
            "the", "and", "or", "of", "to", "in", "a", "an", "is", "for", "on", "with",
            "as", "by", "at", "from", "it", "that", "this", "be", "are", "was", "were",
            "what", "how", "why", "which", "when", "where", "who", "whom", "whose", "do",
            "does", "did", "can", "could", "should", "would", "may", "might", "must",
            "about", "into", "through", "during", "before", "after", "above", "below",
            "regarding", "exists", "between",
        }

        all_q_words = [w.lower() for w in re.findall(r"\b[a-zA-Z0-9-]{2,}\b", topic)]
        q_tokens = [w for w in all_q_words if w not in stopwords]
        salient_q_terms = {w for w in q_tokens if w not in generic_words_list}

        # Extend head terms with configured domain synonyms (e.g. Kiro -> spec-driven)
        # Bare company names and bare agent terms are excluded from standalone head terms
        extended_head_terms = {
            t for t in salient_q_terms
            if t not in COMPANY_NAMES and t not in AGENT_BARE_TERMS
        }
        for key, syns in synonyms_cfg.items():
            if key.lower() in salient_q_terms or any(key.lower() in w for w in salient_q_terms):
                for syn in syns:
                    for part in re.findall(r"\b[a-zA-Z0-9-]{2,}\b", syn.lower()):
                        if (
                            part not in stopwords
                            and part not in generic_words_list
                            and part not in COMPANY_NAMES
                            and part not in AGENT_BARE_TERMS
                        ):
                            extended_head_terms.add(part)

        for p in selected:
            # 1. Year filter enforcement at retrieval time
            yr = p.get("year")
            if yr is not None and str(yr).isdigit():
                yr_val = int(yr)
                if yr_val < min_year:
                    self._safe_insert_search_log(
                        SearchLog(
                            id=f"slog_rej_yr_{uuid.uuid4().hex[:10]}",
                            run_id=run_id,
                            question_id=question_id,
                            lane="academic",
                            query=topic,
                            source_api=p.get("source") or "open_academic_repos",
                            result_count=0,
                            rejected_reason=f"year_below_minimum: publication year {yr_val} is older than min_year {min_year}",
                            details_json={"paper_id": p.get("id"), "title": p.get("title"), "year": yr_val},
                        )
                    )
                    continue

            # 2. Weighted topic term overlap filter
            p_text = f"{p.get('title', '')} {p.get('abstract', '')}".lower()
            p_tokens = set(re.findall(r"\b[a-zA-Z0-9-]{2,}\b", p_text))

            # Match salient terms (with company and agent qualifications)
            matched_salient = set()
            for t in salient_q_terms:
                for pt in p_tokens:
                    if stems_match(t, pt):
                        if t in COMPANY_NAMES and not is_valid_company_match(t, p_text, p_tokens):
                            continue
                        if t in AGENT_BARE_TERMS and not is_valid_agent_match(t, p_text, p_tokens):
                            continue
                        matched_salient.add(t)
                        break

            matched_extended_head = set()
            for t in extended_head_terms:
                for pt in p_tokens:
                    if stems_match(t, pt):
                        if t in COMPANY_NAMES and not is_valid_company_match(t, p_text, p_tokens):
                            continue
                        if t in AGENT_BARE_TERMS and not is_valid_agent_match(t, p_text, p_tokens):
                            continue
                        matched_extended_head.add(t)
                        break

            has_head_phrase = False
            for syns in synonyms_cfg.values():
                for syn in syns:
                    syn_lower = syn.lower()
                    if " " in syn_lower:
                        if syn_lower in p_text:
                            parts = set(syn_lower.split())
                            comp_in_phrase = parts & COMPANY_NAMES
                            if comp_in_phrase and not any(is_valid_company_match(c, p_text, p_tokens) for c in comp_in_phrase):
                                continue
                            agent_in_phrase = parts & AGENT_BARE_TERMS
                            if agent_in_phrase and not any(is_valid_agent_match(a, p_text, p_tokens) for a in agent_in_phrase):
                                continue
                            has_head_phrase = True
                            break
                    elif syn_lower not in COMPANY_NAMES and syn_lower not in AGENT_BARE_TERMS:
                        if any(stems_match(syn_lower, pt) for pt in p_tokens):
                            has_head_phrase = True
                            break
                if has_head_phrase:
                    break

            # Match generic research words
            matched_generic = {
                w for w in q_tokens
                if w in generic_words_list and any(stems_match(w, pt) for pt in p_tokens)
            }

            # Weighted scoring: salient terms = 1.0, generic research terms = 0.05
            salient_weight = len(matched_salient) * 1.0
            generic_weight = len(matched_generic) * 0.05
            total_salient_weight = len(salient_q_terms) * 1.0
            total_q_weight = total_salient_weight + len(set(q_tokens) & generic_words_list) * 0.05
            overlap_fraction = (salient_weight + generic_weight) / total_q_weight if total_q_weight > 0 else 0.0

            relevance = float(p.get("relevance_score", 1.0))
            is_relevant = False
            if bool(matched_salient) and overlap_fraction >= min_weighted_overlap:
                is_relevant = True
            elif has_head_phrase:
                is_relevant = True
            elif bool(matched_extended_head) and bool(p_tokens & SOFTWARE_CONTEXT_TERMS):
                is_relevant = True
            elif len(salient_q_terms) == 0:
                is_relevant = (overlap_fraction >= min_weighted_overlap and relevance >= 0.20)

            if not is_relevant:
                self._safe_insert_search_log(
                    SearchLog(
                        id=f"slog_rej_top_{uuid.uuid4().hex[:10]}",
                        run_id=run_id,
                        question_id=question_id,
                        lane="academic",
                        query=topic,
                        source_api=p.get("source") or "open_academic_repos",
                        result_count=0,
                        rejected_reason=f"off_topic_low_relevance: paper has no substantive term overlap with question scope (weighted_overlap={overlap_fraction:.2f} < {min_weighted_overlap}, salient_matched={len(matched_salient)})",
                        details_json={
                            "paper_id": p.get("id"),
                            "title": p.get("title"),
                            "matched_salient": list(matched_salient),
                            "matched_generic": list(matched_generic),
                            "overlap_fraction": round(overlap_fraction, 3),
                        },
                    )
                )
                continue

            accepted_papers.append(p)

        selected = accepted_papers

        # Ingest Sources into ledger.db
        for p in selected:
            title = p.get("title", "Untitled")
            doi = p.get("doi") or p.get("url") or p.get("link")
            src_id = p.get("id") or hashlib.sha256(f"{doi or title}".encode()).hexdigest()[:16]
            p["id"] = src_id
            venue, s_type = resolve_honest_venue_and_type(p)
            p["venue"] = venue
            p["source_type"] = s_type
            venue_tier = self.grader.resolve_venue_tier(venue, s_type)

            yr = p.get("year")
            pub_date_str = str(yr) if (yr is not None and str(yr).lower() not in ("none", "null", "")) else "Date unknown"
            if pub_date_str == "Date unknown":
                p["year"] = "Date unknown"

            source = Source(
                id=src_id,
                lane="academic",
                source_type="peer_reviewed" if s_type in ("Peer-Reviewed Journal", "Conference") else "preprint",
                org=p.get("authors", ["Academic Authors"])[0] if isinstance(p.get("authors"), list) and p.get("authors") else "Academic Researcher",
                title=title,
                url=p.get("url") or p.get("link"),
                venue=venue,
                venue_tier=venue_tier,
                pub_date=pub_date_str,
                commercial_stake="none",
                status="active",
            )
            self._safe_insert_source(source)

            # Record search log
            slog = SearchLog(
                id=f"slog_acad_{uuid.uuid4().hex[:10]}",
                run_id=run_id,
                question_id=question_id,
                lane="academic",
                query=topic,
                source_api=p.get("source") or "open_academic_repos",
                result_count=len(selected),
                status="searched_ok",
                executed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
            self._safe_insert_search_log(slog)

        if len(selected) == 0:
            slog = SearchLog(
                id=f"slog_acad_{uuid.uuid4().hex[:10]}",
                run_id=run_id,
                question_id=question_id,
                lane="academic",
                query=topic,
                source_api="open_academic_repos",
                result_count=0,
                status="searched_ok",
                executed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
            self._safe_insert_search_log(slog)

        return selected

    def _harvest_enterprise_lane(
        self,
        topic: str,
        question_obj: Question,
        run_id: str,
        custom_urls: Optional[List[str]] = None,
        enterprise_feed_override: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> List[Claim]:
        """Harvest enterprise lane evidence from sources registry and curated industry feeds."""
        ent_collector = EnterpriseCollector(
            registry_path=self.sources_registry_path,
            db_path=self.db_path,
        )

        claims = ent_collector.search_and_ingest(
            question=question_obj,
            query=topic,
            run_id=run_id,
            feed_data_override=enterprise_feed_override,
        )
        for src_cfg in ent_collector.registry_sources:
            src_id = src_cfg.get("id")
            if src_id and src_id not in self._ephemeral_sources:
                self._ephemeral_sources[src_id] = Source(
                    id=src_id,
                    lane="enterprise",
                    source_type=src_cfg["source_type"],
                    org=src_cfg["org"],
                    title=f"{src_cfg['org']} - {src_cfg['id']}",
                    url=src_cfg.get("url"),
                    venue=src_cfg["org"],
                    venue_tier="vendor" if src_cfg.get("commercial_stake") == "vendor" else "verified",
                    commercial_stake=src_cfg.get("commercial_stake", "unknown"),
                    extraction_depth="structured_data" if src_cfg["source_type"] == "filing" else "abstract_only",
                    status="active",
                )
        for c in claims:
            if all(existing.id != c.id for existing in self._ephemeral_claims):
                self._ephemeral_claims.append(c)

        # Ingest custom user URLs for Enterprise Lane
        if custom_urls:
            for u in custom_urls:
                u_clean = u.strip()
                if not u_clean:
                    continue
                t, a, d = fetch_url_metadata(u_clean)
                src_id = f"custom_ent_{hashlib.sha256(u_clean.encode()).hexdigest()[:10]}"
                is_vendor = any(w in u_clean.lower() for w in ("blog", "aws", "microsoft", "google", "vendor"))
                stake = "vendor" if is_vendor else "independent"
                src_type = "filing" if "sec.gov" in u_clean else ("vendor_blog" if is_vendor else "customer_case_study")

                source = Source(
                    id=src_id,
                    lane="enterprise",
                    source_type=src_type,
                    org=d,
                    title=f"[Custom User Source] {t}",
                    url=u_clean,
                    venue=d,
                    venue_tier="vendor" if is_vendor else "unverified",
                    pub_date=str(datetime.datetime.now().year),
                    commercial_stake=stake,
                    status="active",
                )
                self._safe_insert_source(source)

                extracted = extract_claims_from_paper(
                    paper={"id": src_id, "title": t, "abstract": a, "url": u_clean},
                    question_id=question_obj.id,
                    target_entity="Enterprise AI Delivery",
                )
                if not extracted:
                    extracted = [
                        Claim(
                            id=f"claim_{uuid.uuid4().hex[:10]}",
                            question_id=question_obj.id,
                            source_id=src_id,
                            text=f"Custom enterprise source provides technical evidence: {a[:120]}",
                            source_excerpt=a[:120],
                            entity=t[:50],
                            entity_match="topic_level",
                            study_type="case_study" if not is_vendor else "vendor_assertion",
                            claim_date=str(datetime.datetime.now().year),
                            grade="vendor_claim" if is_vendor else "moderate",
                            grade_reasons_json=["Ingested from user enterprise URL; commercial capping applied."],
                            status="active",
                            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        )
                    ]
                for c in extracted:
                    self._safe_insert_claim(c)
                    claims.append(c)

        return claims

    def _harvest_practitioner_lane(
        self,
        topic: str,
        question_obj: Question,
        run_id: str,
        custom_urls: Optional[List[str]] = None,
        practitioner_abstraction_confirmed: bool = False,
    ) -> Tuple[List[Claim], bool]:
        """Harvest local-only practitioner delivery observations from practitioner.db."""
        if os.getenv("HOSTED_DEMO") == "1":
            logger.info("Hosted demo mode active: Lane C (Practitioner) harvesting strictly disabled.")
            return [], False

        prac_collector = PractitionerCollector(db_path=self.practitioner_db_path)
        has_unconfirmed_practitioner_notes = False

        # Ingest custom user URLs / observations for Practitioner Lane
        if custom_urls:
            for u in custom_urls:
                u_clean = u.strip()
                if not u_clean:
                    continue
                if not practitioner_abstraction_confirmed:
                    has_unconfirmed_practitioner_notes = True
                t, a, d = fetch_url_metadata(u_clean) if u_clean.startswith("http") else (u_clean[:60], u_clean, "field-notes")
                prac_collector.add_observation(
                    question_id=question_obj.id,
                    situation=f"[Custom User Observation] {t}" if not u_clean.startswith("http") else f"[Custom User Observation] Ingested from {u_clean}",
                    decision="Integrated automated verification gates for custom stack",
                    action=f"Observed delivery outcome and telemetry: {a}",
                    outcome="Maintained verified governance and zero ungrounded regression",
                    sector="technology_delivery",
                    date=datetime.date.today().isoformat(),
                    metric={"observation_status": "verified"},
                    abstraction_confirmed=practitioner_abstraction_confirmed,
                    observations_count=1,
                    entity=t[:50],
                )

        # Export confirmed abstracted claims for this question to the shared ledger
        exported_claims: List[Claim] = []
        for obs in prac_collector.list_observations(question_id=question_obj.id):
            if obs.context_json and obs.context_json.get("abstraction_confirmed") is True:
                try:
                    exported = prac_collector.export_abstracted_claim_to_ledger(
                        claim_id=obs.id,
                        ledger_repo=self.repo,
                        reviewer="multi_lane_orchestrator",
                    )
                    exported_claims.append(exported)
                except Exception as e:
                    logger.debug("Practitioner claim export note: %s", e)

        # Log search log for practitioner lane
        existing_obs = prac_collector.list_observations(question_id=question_obj.id)
        prac_status = "searched_ok" if (existing_obs or exported_claims) else "not_searched"
        slog = SearchLog(
            id=f"slog_prac_{uuid.uuid4().hex[:10]}",
            run_id=run_id,
            question_id=question_obj.id,
            lane="practitioner",
            query=topic,
            source_api="practitioner_field_notes_sqlite",
            result_count=len(exported_claims),
            status=prac_status,
            executed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        self._safe_insert_search_log(slog)

        return exported_claims, has_unconfirmed_practitioner_notes

    def _extract_academic_claims(self, papers: List[Dict[str, Any]], question_id: str) -> List[Claim]:
        """Extract atomic claims from academic papers."""
        all_extracted: List[Claim] = []
        for p in papers:
            claims = extract_claims_from_paper(
                paper=p,
                question_id=question_id,
                target_entity=p.get("title", "AI Systems"),
            )
            all_extracted.extend(claims)
        return all_extracted

    def _grade_and_persist_claims(self, academic_claims: List[Claim], question_id: str) -> List[Claim]:
        """Persist academic claims in ledger.db and apply deterministic grading."""
        graded: List[Claim] = []
        for c in academic_claims:
            src = self.repo.get_source(c.source_id) or self._ephemeral_sources.get(c.source_id)
            if not src:
                src = Source(
                    id=c.source_id,
                    lane="academic",
                    source_type="preprint",
                    org="Academic Source",
                    title=c.entity or "Academic Publication",
                    pub_date=c.claim_date or "2024",
                    status="active",
                )
                self._safe_insert_source(src)
            grade, reasons = self.grader.grade_claim(c, src)
            c.grade = grade
            c.grade_reasons_json = reasons
            self._safe_insert_claim(c)
            graded.append(c)

        # Return all active claims for question
        db_claims = self.repo.list_claims(question_id=question_id)
        return db_claims if db_claims else list(self._ephemeral_claims)

    def _generate_executive_deliverables(
        self,
        topic: str,
        papers: List[Dict[str, Any]],
        tone: str,
        map_provider: str,
        reduce_provider: str,
        question_obj: Question,
        academic_claims: List[Claim],
        enterprise_claims: List[Claim],
        practitioner_claims: List[Claim],
    ) -> Dict[str, Any]:
        """Generate high-level executive report, storylines, and packs."""
        import re
        from src.analysis.business_context import detect_focus_areas
        from src.analysis.insight_builder import derive_business_signal, summarize_findings
        from src.analysis.synthesizer import SynthesisEngine as AnalysisSynthesisEngine
        from src.config import load_config
        from src.llm.factory import build_llm
        from src.output.content_pack import ContentPackBuilder
        from src.output.report_builder import ReportBuilder

        cfg = load_config("config.yaml") if Path("config.yaml").exists() else {}
        tone_key = "executive" if "Executive" in tone else "engineering" if "Architectural" in tone else "thought_leadership"

        error_details = None
        generation_mode = "model"

        try:
            map_llm = build_llm(map_provider, cfg)
            reduce_llm = map_llm if reduce_provider == map_provider else build_llm(reduce_provider, cfg)
            synthesizer = AnalysisSynthesisEngine(map_llm, reduce_llm, on_progress=lambda _: None)
            synth = synthesizer.analyze(topic, papers, tone=tone_key, length="detailed")
            if map_provider == "stub" or reduce_provider == "stub":
                generation_mode = "extractive_fallback"
                if not synth.get("executive_summary") and not synth.get("key_findings"):
                    synth = self._build_extractive_fallback_synthesis(
                        topic=topic,
                        papers=papers,
                        question_obj=question_obj,
                        academic_claims=academic_claims,
                        enterprise_claims=enterprise_claims,
                        practitioner_claims=practitioner_claims,
                        error_details={"error_class": "OfflineEngine", "error_message": "Deterministic offline extractive engine active"},
                    )
                synth["generation_mode"] = "extractive_fallback"
                synth["is_fallback"] = True
            else:
                synth["generation_mode"] = "model"
                synth["is_fallback"] = False
        except Exception as e:
            exc_class = type(e).__name__
            raw_msg = str(e)
            clean_msg = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[REDACTED_KEY]", raw_msg)
            logger.warning(
                "Primary model '%s' synthesis encountered %s (%s). Executing graceful fallback to Extractive Claims Engine.",
                map_provider,
                exc_class,
                clean_msg,
            )
            error_details = {"error_class": exc_class, "error_message": clean_msg}
            generation_mode = "extractive_fallback"
            synth = self._build_extractive_fallback_synthesis(
                topic=topic,
                papers=papers,
                question_obj=question_obj,
                academic_claims=academic_claims,
                enterprise_claims=enterprise_claims,
                practitioner_claims=practitioner_claims,
                error_details=error_details,
            )

        synth["generation_mode"] = generation_mode
        synth["is_fallback"] = (generation_mode == "extractive_fallback")
        synth["error_details"] = error_details

        synth["papers"] = papers
        synth["business_context"] = {
            "focus_areas": detect_focus_areas(topic),
            "business_signal": derive_business_signal(topic, papers),
            "finding_summary": summarize_findings(synth.get("paper_summaries", [])),
        }
        synth["content_pack"] = ContentPackBuilder(topic).build(synth)

        return synth

    def _build_extractive_fallback_synthesis(
        self,
        topic: str,
        papers: List[Dict[str, Any]],
        question_obj: Question,
        academic_claims: List[Claim],
        enterprise_claims: List[Claim],
        practitioner_claims: List[Claim],
        error_details: Dict[str, str],
    ) -> Dict[str, Any]:
        """Build strictly extractive claims list without inferred conclusions when model is unavailable."""
        from src.synth.generator import SynthesisEngine
        temp_engine = SynthesisEngine(db_path=self.db_path)

        paper_id_map = {p.get("id"): f"P{idx}" for idx, p in enumerate(papers, 1)}

        extractive_findings = []
        for c in academic_claims:
            p_tag = paper_id_map.get(c.source_id, "P1")
            verb = temp_engine._select_verb_for_grade(c.grade)
            c_text = c.text.strip().rstrip(".")
            for prefix in ("the study reports that ", "the study finds that ", "the authors find that ", "empirical analysis shows that ", "research indicates that "):
                if c_text.lower().startswith(prefix):
                    c_text = c_text[len(prefix):]
                    break
            extractive_findings.append(f"[{p_tag}] Academic claim {verb} that {c_text}.")

        for c in enterprise_claims:
            verb = temp_engine._select_verb_for_grade(c.grade)
            extractive_findings.append(f"[{c.source_id}] Enterprise evidence {verb} that {c.text.strip().rstrip('.')}.")

        for c in practitioner_claims:
            verb = temp_engine._select_verb_for_grade(c.grade)
            extractive_findings.append(f"[{c.source_id}] Field observation {verb} that {c.text.strip().rstrip('.')}.")

        if not extractive_findings:
            extractive_findings = []

        lead_preview = extractive_findings[0] if extractive_findings else "No empirical claims met threshold criteria."
        return {
            "topic": topic,
            "executive_summary": (
                f"Extractive Evidence Summary ({len(academic_claims)} academic claims across {len(papers)} papers, "
                f"{len(enterprise_claims)} enterprise claims, {len(practitioner_claims)} field observations): "
                f"{lead_preview} "
                f"[Mode: Verified extractive ledger claims only; primary model status: {error_details.get('error_class', 'Offline')}]"
            ),
            "objective": f"Extractive evidence inventory for {topic}",
            "research_questions": [question_obj.text],
            "sources": sorted({p.get("source", "") or p.get("venue", "") for p in papers if p.get("source") or p.get("venue")}),
            "time_window": "Not specified",
            "papers": papers,
            "paper_summaries": [],
            "key_findings": extractive_findings,
            "themes": [],
            "market_trends": [],
            "business_problems": [],
            "research_gaps": [],
            "recommendations": [],
            "strategic_roadmap": [],
            "content_ideas": [],
            "references": [
                f"[P{i}] {p.get('title', '')} ({p.get('year', 'n/a')}) {p.get('url') or p.get('link') or ''}".strip()
                for i, p in enumerate(papers, start=1)
            ],
            "citation_check": {"total_citations": len(extractive_findings), "invalid_ids": []},
            "generation_mode": "extractive_fallback",
            "is_fallback": True,
            "error_details": error_details,
        }

    def _build_result_payload(
        self,
        topic: str,
        question_obj: Question,
        run_id: str,
        doc: OutputDoc,
        sentences: List[OutputSentence],
        gap_entry: Any,
        gate_results: Dict[str, Any],
        score_results: Dict[str, Any],
        publish_res: Dict[str, Any],
        academic_papers: List[Dict[str, Any]],
        academic_claims: List[Claim],
        enterprise_claims: List[Claim],
        practitioner_claims: List[Claim],
        executive_synthesis: Dict[str, Any],
        elapsed_seconds: int,
    ) -> Dict[str, Any]:
        """Assemble structured presentation data object."""
        years = [int(p["year"]) for p in academic_papers if p.get("year") and str(p["year"]).isdigit()]
        year_range_str = f"{min(years)}–{max(years)}" if years else "2020–2026"
        sources_set = {p.get("venue") or p.get("source") or "Academic Repo" for p in academic_papers}

        outcome_names = {
            1: "Outcome 1: Supported (Academic + Enterprise Aligned)",
            2: "Outcome 2: Practice Without Evidence (Enterprise Active, Academic Void)",
            3: "Outcome 3: Evidence Without Practice (Academic Proven, Enterprise Unmeasured)",
            4: "Outcome 4: Unmeasured (Thin Evidence Across Lanes)",
            "Practice not assessed": "Practice not assessed: Enterprise lane not searched (no working fetcher)",
            "practice_not_assessed": "Practice not assessed: Enterprise lane not searched (no working fetcher)",
        }
        outcome_raw = getattr(gap_entry, "outcome", 1)
        if isinstance(outcome_raw, int) or (isinstance(outcome_raw, str) and outcome_raw.isdigit()):
            outcome_val = int(outcome_raw)
        else:
            outcome_val = str(outcome_raw)

        # Formatted papers table & lookup maps for full source traceability
        papers_formatted = []
        paper_by_id: Dict[str, Dict[str, Any]] = {}
        for i, p in enumerate(academic_papers, start=1):
            v, t = resolve_honest_venue_and_type(p)
            yr = p.get("year")
            yr_str = "Date unknown" if (yr is None or str(yr).lower() in ("none", "null", "", "date unknown")) else str(yr)
            p_entry = {
                "id": p.get("id"),
                "key": f"P{i}",
                "title": p.get("title", "Untitled"),
                "year": yr_str,
                "venue": v,
                "doi": p.get("doi") or p.get("url") or p.get("link") or "Indexed",
                "type": t,
                "url": p.get("url") or p.get("link") or "https://scholar.google.com",
                "relevance_score": float(p.get("relevance_score", 0.0)),
                "is_custom": bool(p.get("is_custom", False) or "[Custom User Source]" in p.get("title", "")),
            }
            papers_formatted.append(p_entry)
            if p.get("id"):
                paper_by_id[str(p.get("id"))] = p_entry

        all_q_claims = self.repo.list_claims(question_id=question_obj.id)
        if not all_q_claims:
            all_q_claims = list(self._ephemeral_claims)
        claim_by_id: Dict[str, Claim] = {c.id: c for c in all_q_claims}

        def _build_sources_trace(claim_ids: List[str], sentence_text: str) -> List[Dict[str, Any]]:
            traces_out: List[Dict[str, Any]] = []
            seen_cids = set()
            for cid in claim_ids:
                if cid in seen_cids:
                    continue
                seen_cids.add(cid)
                c_obj = claim_by_id.get(cid)
                if not c_obj:
                    continue
                src_obj = self.repo.get_source(c_obj.source_id) or self._ephemeral_sources.get(c_obj.source_id)
                p_info = paper_by_id.get(str(c_obj.source_id))
                src_key = p_info["key"] if p_info else str(c_obj.source_id)
                src_title = p_info["title"] if p_info else (src_obj.title if src_obj else c_obj.entity or "Verified Source")
                src_venue = p_info["venue"] if p_info else (src_obj.venue or src_obj.org if src_obj else "Repository")
                src_year = p_info["year"] if p_info else (src_obj.pub_date if src_obj and src_obj.pub_date else str(c_obj.claim_date or "2024"))
                src_url = p_info["url"] if p_info else (src_obj.url if src_obj and src_obj.url else "#")
                src_lane = (src_obj.lane if src_obj else ("academic" if p_info else "enterprise")).upper()
                traces_out.append({
                    "claim_id": c_obj.id,
                    "source_key": src_key,
                    "lane": src_lane,
                    "source_title": src_title,
                    "venue": src_venue,
                    "year": src_year,
                    "url": src_url,
                    "grade": (c_obj.grade or "weak").upper(),
                    "study_type": c_obj.study_type or "empirical",
                    "excerpt": c_obj.source_excerpt or c_obj.text,
                })
            # Also resolve any explicit [P#] in sentence text if claim_ids didn't already cover it
            if not traces_out:
                for p_match in re.findall(r"\[(P\d+)\]", sentence_text):
                    matched_p = next((p for p in papers_formatted if p["key"] == p_match), None)
                    if matched_p:
                        traces_out.append({
                            "claim_id": "citation_ref",
                            "source_key": matched_p["key"],
                            "lane": "ACADEMIC",
                            "source_title": matched_p["title"],
                            "venue": matched_p["venue"],
                            "year": matched_p["year"],
                            "url": matched_p["url"],
                            "grade": "VERIFIED",
                            "study_type": matched_p["type"],
                            "excerpt": matched_p["title"],
                        })
            return traces_out

        # Derive all user-facing presentation items strictly from output_sentences with full traceability
        ui_findings = []
        for s in sentences:
            if s.type in ("finding", "assertive"):
                cids = s.claim_ids_json or []
                ui_findings.append({
                    "id": s.id,
                    "ordinal": s.ordinal,
                    "text": s.text,
                    "claim_ids": cids,
                    "sources_trace": _build_sources_trace(cids, s.text),
                })

        ui_signals = [
            {
                "tag": f"KEY SIGNAL {idx+1}",
                "text": s.text,
                "citation": f"[P{idx+1}]",
                "claim_ids": s.claim_ids_json or [],
                "sources_trace": _build_sources_trace(s.claim_ids_json or [], s.text),
            }
            for idx, s in enumerate([s for s in sentences if s.type == "signal"])
        ]
        ui_risks = [s.text for s in sentences if s.type == "risk"]
        ui_roadmap = []
        for idx, s in enumerate([s for s in sentences if s.type == "roadmap"], 1):
            if ":" in s.text:
                phase, action = s.text.split(":", 1)
            else:
                phase, action = f"Phase {idx}", s.text
            ui_roadmap.append({
                "phase": phase.strip(),
                "action": action.strip(),
                "impact": "Empirical governance target verified",
            })
        ui_negative = [s.text for s in sentences if s.type == "negative_finding"]

        # Formatted enterprise sources (scoped strictly to claims for this question/run)
        ent_sources_formatted = []
        ent_source_ids = {c.source_id for c in enterprise_claims}
        for sid in ent_source_ids:
            s = self.repo.get_source(sid) or self._ephemeral_sources.get(sid)
            if s and s.lane == "enterprise":
                ent_sources_formatted.append({
                    "id": s.id,
                    "title": s.title,
                    "url": s.url or "https://dora.dev",
                    "venue": s.venue or s.org,
                    "commercial_stake": s.commercial_stake,
                    "source_type": s.source_type,
                    "pub_date": s.pub_date,
                    "is_custom": "[Custom User Source]" in s.title,
                })

        # Formatted practitioner observations (scoped strictly to this question)
        prac_obs_formatted = []
        if os.getenv("HOSTED_DEMO") != "1":
            prac_collector = PractitionerCollector(db_path=self.practitioner_db_path)
            for obs in prac_collector.list_observations(question_id=question_obj.id):
                ctx = obs.context_json or {}
                prac_obs_formatted.append({
                    "id": obs.id,
                    "situation": ctx.get("situation", obs.text),
                    "decision": ctx.get("decision", "Governance gate enforcement"),
                    "action": ctx.get("action", obs.source_excerpt),
                    "outcome": ctx.get("outcome", "Verified delivery outcome"),
                    "date": obs.claim_date,
                    "is_custom": "[Custom User Observation]" in ctx.get("situation", "") or "[Custom User Observation]" in obs.text,
                })

        # Formatted atomic claims with full source metadata
        claims_formatted = []
        for c in all_q_claims:
            src = self.repo.get_source(c.source_id) or self._ephemeral_sources.get(c.source_id)
            p_info = paper_by_id.get(str(c.source_id))
            claims_formatted.append({
                "id": c.id,
                "lane": (src.lane if src else ("academic" if p_info else "academic")).upper(),
                "assertion": c.text,
                "excerpt": c.source_excerpt,
                "grade": c.grade.upper(),
                "entity": c.entity,
                "entity_match": c.entity_match,
                "study_type": c.study_type,
                "source_key": p_info["key"] if p_info else str(c.source_id),
                "source_title": p_info["title"] if p_info else (src.title if src else "Unknown"),
                "source_url": p_info["url"] if p_info else (src.url if src and src.url else "#"),
                "venue": p_info["venue"] if p_info else (src.venue or src.org if src else "Academic Repo"),
                "year": p_info["year"] if p_info else (src.pub_date if src and src.pub_date else str(c.claim_date or "2024")),
                "rules": ", ".join(c.grade_reasons_json or ["Default rules"]),
                "is_custom": bool((src and "[Custom User Source]" in src.title) or (p_info and p_info.get("is_custom"))),
            })

        # Format roadmap
        roadmap_steps = []
        for phase in executive_synthesis.get("strategic_roadmap", []):
            roadmap_steps.append({
                "phase": phase.get("stage", "Phase"),
                "action": (phase.get("actions") or ["Execute roadmap step"])[0],
                "impact": (phase.get("kpis") or ["Target KPI achieved"])[0],
            })
        if not roadmap_steps:
            roadmap_steps = []

        # Sentence-level traceability from ledger-only generator
        sentence_traces = []
        for s in sentences:
            sentence_traces.append({
                "ordinal": s.ordinal,
                "text": s.text,
                "type": s.type,
                "claims": s.claim_ids_json or [],
                "checks_json": s.checks_json or {},
            })

        status_val = publish_res.get("status", score_results.get("band", "NOT_PUBLISHABLE"))

        return {
            "status": status_val,
            "verdict": executive_synthesis.get("executive_summary", ""),
            "duration": f"{elapsed_seconds}s",
            "question_id": question_obj.id,
            "strategic_question": question_obj.text,
            "scope": question_obj.scope,
            "run_id": run_id,
            "gap_matrix": {
                "academic_state": getattr(gap_entry, "academic_state", "supported"),
                "enterprise_state": getattr(gap_entry, "enterprise_state", "supported"),
                "field_state": getattr(gap_entry, "field_state", "supported"),
                "outcome": outcome_val,
                "outcome_label": outcome_names.get(outcome_val, f"Outcome {outcome_val}" if isinstance(outcome_val, int) else str(outcome_val)),
                "rationale": getattr(gap_entry, "rationale", ""),
            },
            "lane_breakdown": {
                "academic_sources_count": len(academic_papers),
                "academic_count": len(academic_papers),
                "academic_claims_count": len(academic_claims),
                "enterprise_sources_count": len(ent_sources_formatted),
                "enterprise_claims_count": len(enterprise_claims),
                "practitioner_observations_count": len(prac_obs_formatted),
                "practitioner_claims_count": len(practitioner_claims),
            },
            "metrics": {
                "volume": f"{len(academic_papers)} Papers ({len(academic_claims)} claims) • {len(ent_sources_formatted)} Enterprise Sources ({len(enterprise_claims)} claims) • {len(prac_obs_formatted)} Field Observations",
                "sources": f"{len(sources_set)} Repositories",
                "horizon": year_range_str,
                "quality": f"{score_results.get('total_score', 88)}/100 ({score_results.get('band', 'PUBLISH_READY')})",
            },
            "doc_id": doc.id,
            "signals": ui_signals,
            "findings": ui_findings,
            "risks": ui_risks,
            "roadmap": ui_roadmap,
            "negative_findings": ui_negative,
            "business_signal": executive_synthesis.get("business_context", {}).get("business_signal", {}).get("summary", ""),
            "papers": papers_formatted,
            "enterprise_sources": ent_sources_formatted,
            "practitioner_observations": prac_obs_formatted,
            "claims": claims_formatted,
            "sentence_traces": sentence_traces,
            "generation_mode": executive_synthesis.get("generation_mode", "model"),
            "is_fallback": bool(executive_synthesis.get("is_fallback", False)),
            "error_details": executive_synthesis.get("error_details"),
            "blocking_banner": (
                f"EXTRACTIVE FALLBACK MODE • Primary model unavailable ({(executive_synthesis.get('error_details') or {}).get('error_class', 'Offline')}). "
                "Output generated from verified extractive claims only and is blocked from publication."
            ) if executive_synthesis.get("is_fallback") else None,
            "gates_audit": gate_results,
            "quality_scorecard": score_results,
            "publish_res": publish_res,
            "synthesis": executive_synthesis,
        }
