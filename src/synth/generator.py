"""Deterministic, claim-driven synthesis engine for Research Engine v2 (Phase 4).

Generates traceable Field Notes and Strategy Documents from approved ledger claims.
Enforces:
- Reads eligible claims only from the ledger.
- Every assertive sentence links to eligible claim IDs.
- Sentence verbs strictly bounded by strength_verbs.yaml caps.
- The engine NEVER generates first-person opinions or field experience.
- Lints against raw topic string interpolation and repeated boilerplate sentences (R14).
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple
import yaml

from src.gaps.matrix_builder import GapMatrixBuilder
from src.ledger.models import Claim, OutputDoc, OutputSentence, Question, Run, Source
from src.ledger.repository import LedgerRepository
from src.score.checker import GateChecker
from src.score.scorer import QualityScorer

logger = logging.getLogger(__name__)


def lint_output_text(
    sentences: List[OutputSentence],
    raw_topic: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    """Lint generated sentences for boilerplate repetition and raw topic interpolation (R14)."""
    violations: List[str] = []
    seen_texts: Set[str] = set()

    for s in sentences:
        text = s.text.strip()
        norm_text = re.sub(r"\s+", " ", text.lower())

        # Check for raw topic string interpolation
        if raw_topic and len(raw_topic) > 15:
            norm_topic = re.sub(r"\s+", " ", raw_topic.lower())
            if norm_topic in norm_text and s.type == "assertive":
                violations.append(
                    f"R14 Lint Violation: Raw topic string '{raw_topic}' interpolated directly into sentence: '{text}'"
                )

        # Check for repeated boilerplate sentences
        if s.type == "assertive":
            if norm_text in seen_texts:
                violations.append(
                    f"R14 Lint Violation: Repeated boilerplate sentence detected: '{text}'"
                )
            seen_texts.add(norm_text)

        # Check for template verb stutter (doubled verb phrases, D3 / R18)
        if s.type == "assertive":
            if re.search(r"\b(suggests|reports|finds|indicates|shows|states|demonstrates)\s+that\s+(the\s+(?:study|paper|author|literature)\s+)?(suggests|reports|finds|indicates|shows|states|demonstrates)\s+that", norm_text):
                violations.append(
                    f"R18 Lint Violation: Template verb stutter detected: '{text}'"
                )

    return len(violations) == 0, violations


class SynthesisEngine:
    def __init__(
        self,
        db_path: str = "ledger/ledger.db",
        verbs_path: str = "synth/strength_verbs.yaml",
        scoring_path: str = "score/scoring.yaml",
    ):
        self.db_path = db_path
        self.repo = LedgerRepository(db_path=self.db_path)
        self.gap_builder = GapMatrixBuilder(db_path=self.db_path)
        self.checker = GateChecker(verbs_path=verbs_path)
        self.scorer = QualityScorer(scoring_cfg_path=scoring_path)
        with open(verbs_path, "r", encoding="utf-8") as f:
            self.verbs_cfg = yaml.safe_load(f).get("levels", {})

    def _select_verb_for_grade(self, grade: str) -> str:
        """Select an honest verb corresponding to the claim grade."""
        verbs = self.verbs_cfg.get(grade, {}).get("verbs", [])
        if verbs:
            return verbs[0]
        if grade == "strong":
            return "demonstrates"
        elif grade == "moderate":
            return "suggests"
        elif grade == "vendor_claim":
            return "states"
        return "reports"

    def build_field_note(
        self,
        question_id: str,
        human_view: Optional[str] = None,
        run_id: Optional[str] = None,
        executive_synthesis: Optional[Dict[str, Any]] = None,
        papers: Optional[List[Dict[str, Any]]] = None,
        claims_override: Optional[List[Claim]] = None,
        sources_override: Optional[Dict[str, Source]] = None,
        search_logs_override: Optional[List[Any]] = None,
        gap_entry_override: Optional[Any] = None,
    ) -> Tuple[OutputDoc, List[OutputSentence], Dict[str, Any]]:
        """Generate a structured, evidence-grounded Field Note."""
        question = self.repo.get_question(question_id)
        if not question:
            if os.getenv("HOSTED_DEMO") == "1":
                question = Question(
                    id=question_id,
                    text=question_id,
                    scope="enterprise",
                    time_window_months=36,
                    status="active",
                    version=1,
                )
            else:
                raise ValueError(f"Question {question_id} not found in ledger")

        # 1. Evaluate Gap Matrix
        gap_entry = gap_entry_override or self.gap_builder.evaluate_question_lanes(
            question_id,
            run_id=run_id,
            claims_override=claims_override,
            sources_override=sources_override,
            search_logs_override=search_logs_override,
        )

        # 2. Retrieve eligible claims (approved or auto, not rejected)
        all_claims = self.repo.list_claims(question_id=question_id)
        if not all_claims and claims_override:
            all_claims = [c for c in claims_override if c.question_id == question_id or not c.question_id]
        eligible_claims = [c for c in all_claims if c.status != "rejected"]
        claims_by_id = {c.id: c for c in eligible_claims}

        sources = {
            c.source_id: ((sources_override or {}).get(c.source_id) or self.repo.get_source(c.source_id))
            for c in eligible_claims
        }
        sources = {sid: src for sid, src in sources.items() if src is not None}

        # 3. Partition claims
        supported_claims = [c for c in eligible_claims if c.grade in ("strong", "moderate")]
        thin_claims = [c for c in eligible_claims if c.grade in ("weak", "vendor_claim", "anecdote")]
        default_claim_ids = [c.id for c in (supported_claims or eligible_claims)[:1]]

        output_id = f"out_{uuid.uuid4().hex[:12]}"
        sentences: List[OutputSentence] = []
        ordinal = 1

        # Title & Question Heading
        sentences.append(
            OutputSentence(
                id=f"{output_id}_{ordinal}",
                output_id=output_id,
                ordinal=ordinal,
                text=f"Field Note: {question.text}",
                type="heading",
            )
        )
        ordinal += 1

        # Section: What the Evidence Supports
        sentences.append(
            OutputSentence(
                id=f"{output_id}_{ordinal}",
                output_id=output_id,
                ordinal=ordinal,
                text="What the Evidence Supports",
                type="heading",
            )
        )
        ordinal += 1

        if executive_synthesis and executive_synthesis.get("key_findings"):
            for f_text in executive_synthesis["key_findings"]:
                cited_cids = []
                p_match = re.search(r"\[P(\d+)\]", f_text)
                c_match = re.search(r"\[(c_[^\]]+)\]", f_text)
                if p_match and papers:
                    p_idx = int(p_match.group(1)) - 1
                    if 0 <= p_idx < len(papers):
                        target_paper_id = papers[p_idx].get("id")
                        cited_cids = [c.id for c in eligible_claims if c.source_id == target_paper_id]
                elif c_match:
                    target_cid = c_match.group(1)
                    if target_cid in claims_by_id:
                        cited_cids = [target_cid]
                if not cited_cids and not p_match and not c_match:
                    cited_cids = default_claim_ids

                sentences.append(
                    OutputSentence(
                        id=f"{output_id}_{ordinal}",
                        output_id=output_id,
                        ordinal=ordinal,
                        text=f_text.strip(),
                        type="assertive",
                        claim_ids_json=cited_cids,
                    )
                )
                ordinal += 1
        elif supported_claims:
            for c in supported_claims[:3]:
                verb = self._select_verb_for_grade(c.grade)
                c_text = c.text.strip().rstrip(".")
                for prefix in ("the study reports that ", "the study finds that ", "the authors find that ", "empirical analysis shows that ", "research indicates that "):
                    if c_text.lower().startswith(prefix):
                        c_text = c_text[len(prefix):]
                        break
                text = f"Empirical literature {verb} that {c_text[0].lower() + c_text[1:] if c_text else ''}."
                sentences.append(
                    OutputSentence(
                        id=f"{output_id}_{ordinal}",
                        output_id=output_id,
                        ordinal=ordinal,
                        text=text,
                        type="assertive",
                        claim_ids_json=[c.id],
                        strength_verb=verb,
                    )
                )
                ordinal += 1
        else:
            sentences.append(
                OutputSentence(
                    id=f"{output_id}_{ordinal}",
                    output_id=output_id,
                    ordinal=ordinal,
                    text="No peer-reviewed empirical claims meeting moderate or strong thresholds were retrieved for this question.",
                    type="heading",
                )
            )
            ordinal += 1

        # Section: Strategic Signals
        sentences.append(
            OutputSentence(
                id=f"{output_id}_{ordinal}",
                output_id=output_id,
                ordinal=ordinal,
                text="Strategic Signals",
                type="heading",
            )
        )
        ordinal += 1

        signals_candidates = (
            (executive_synthesis.get("key_findings") or [])[:3]
            if executive_synthesis
            else [s.text for s in sentences if s.type == "assertive"][:3]
        )
        if signals_candidates:
            for sig in signals_candidates:
                sentences.append(
                    OutputSentence(
                        id=f"{output_id}_{ordinal}",
                        output_id=output_id,
                        ordinal=ordinal,
                        text=sig.strip(),
                        type="signal",
                        claim_ids_json=default_claim_ids,
                    )
                )
                ordinal += 1
        else:
            sentences.append(
                OutputSentence(
                    id=f"{output_id}_{ordinal}",
                    output_id=output_id,
                    ordinal=ordinal,
                    text="No strategic signals in evidence ledger.",
                    type="heading",
                )
            )
            ordinal += 1

        # Section: Delivery & Business Risks
        sentences.append(
            OutputSentence(
                id=f"{output_id}_{ordinal}",
                output_id=output_id,
                ordinal=ordinal,
                text="Delivery & Business Risks",
                type="heading",
            )
        )
        ordinal += 1

        risks_candidates = executive_synthesis.get("business_problems", []) if executive_synthesis else []
        if risks_candidates:
            for r in risks_candidates:
                sentences.append(
                    OutputSentence(
                        id=f"{output_id}_{ordinal}",
                        output_id=output_id,
                        ordinal=ordinal,
                        text=r.strip(),
                        type="risk",
                        claim_ids_json=default_claim_ids,
                    )
                )
                ordinal += 1
        else:
            sentences.append(
                OutputSentence(
                    id=f"{output_id}_{ordinal}",
                    output_id=output_id,
                    ordinal=ordinal,
                    text="No verified risk assertions in evidence ledger.",
                    type="heading",
                )
            )
            ordinal += 1

        # Section: What the Evidence Does NOT Support (Negative Findings)
        sentences.append(
            OutputSentence(
                id=f"{output_id}_{ordinal}",
                output_id=output_id,
                ordinal=ordinal,
                text="What the Evidence Does Not Support",
                type="heading",
            )
        )
        ordinal += 1

        slogs = self.repo.list_search_logs(question_id=question_id)
        if not slogs and search_logs_override:
            slogs = [s for s in search_logs_override if s.question_id == question_id or not s.question_id]
        searched_zero = [s for s in slogs if getattr(s, "status", "searched_ok") == "searched_ok" and s.result_count == 0]
        unsearched = [s for s in slogs if getattr(s, "status", "searched_ok") in ("not_implemented", "not_searched", "skipped_by_scope")]

        if searched_zero or unsearched:
            for slog in searched_zero:
                sentences.append(
                    OutputSentence(
                        id=f"{output_id}_{ordinal}",
                        output_id=output_id,
                        ordinal=ordinal,
                        text=f"Literature search in {slog.lane} lane ({slog.source_api}) for '{slog.query}' returned 0 matching records in evidence ledger.",
                        type="negative_finding",
                        checks_json={"search_log_id": slog.id},
                    )
                )
                ordinal += 1
            for slog in unsearched:
                reason = "no fetcher" if getattr(slog, "status", "") == "not_implemented" else "no observations recorded"
                sentences.append(
                    OutputSentence(
                        id=f"{output_id}_{ordinal}",
                        output_id=output_id,
                        ordinal=ordinal,
                        text=f"{slog.lane.capitalize()} source '{slog.source_api}' not searched for '{slog.query}': {reason}.",
                        type="negative_finding",
                        checks_json={"search_log_id": slog.id},
                    )
                )
                ordinal += 1
        elif gap_entry and getattr(gap_entry, "outcome", 1) in (2, 3, 4, "Practice not assessed"):
            sentences.append(
                OutputSentence(
                    id=f"{output_id}_{ordinal}",
                    output_id=output_id,
                    ordinal=ordinal,
                    text=f"Evidence boundary: {gap_entry.rationale}",
                    type="negative_finding",
                    checks_json={"gap_matrix_outcome": gap_entry.outcome},
                )
            )
            ordinal += 1
        else:
            sentences.append(
                OutputSentence(
                    id=f"{output_id}_{ordinal}",
                    output_id=output_id,
                    ordinal=ordinal,
                    text="No negative findings in evidence ledger.",
                    type="negative_finding",
                )
            )
            ordinal += 1

        # Section: The Strategic Gap (Matrix Outcome)
        gap_outcome_str = f"Outcome {gap_entry.outcome}" if isinstance(gap_entry.outcome, int) else str(gap_entry.outcome)
        sentences.append(
            OutputSentence(
                id=f"{output_id}_{ordinal}",
                output_id=output_id,
                ordinal=ordinal,
                text=f"The Strategic Gap ({gap_outcome_str}): {gap_entry.rationale}",
                type="heading",
            )
        )
        ordinal += 1

        # Section: Strategic Roadmap & Recommendations
        sentences.append(
            OutputSentence(
                id=f"{output_id}_{ordinal}",
                output_id=output_id,
                ordinal=ordinal,
                text="Strategic Roadmap & Recommendations",
                type="heading",
            )
        )
        ordinal += 1

        roadmap_candidates = executive_synthesis.get("strategic_roadmap", []) if executive_synthesis else []
        is_fallback = bool(executive_synthesis.get("is_fallback")) if executive_synthesis else False
        if roadmap_candidates and not is_fallback:
            for phase in roadmap_candidates:
                phase_title = phase.get("stage", "Phase") if isinstance(phase, dict) else "Phase"
                actions = phase.get("actions", []) if isinstance(phase, dict) else [str(phase)]
                for act in actions:
                    sentences.append(
                        OutputSentence(
                            id=f"{output_id}_{ordinal}",
                            output_id=output_id,
                            ordinal=ordinal,
                            text=f"{phase_title}: {act}",
                            type="roadmap",
                            claim_ids_json=default_claim_ids,
                        )
                    )
                    ordinal += 1
        else:
            sentences.append(
                OutputSentence(
                    id=f"{output_id}_{ordinal}",
                    output_id=output_id,
                    ordinal=ordinal,
                    text="Recommendations require LLM synthesis; currently in offline extractive mode.",
                    type="heading",
                )
            )
            ordinal += 1

        # Section: Human Opinion & Field Stance (Gate 5 Human-only)
        if human_view and human_view.strip():
            sentences.append(
                OutputSentence(
                    id=f"{output_id}_{ordinal}",
                    output_id=output_id,
                    ordinal=ordinal,
                    text="Practitioner Field Perspective",
                    type="heading",
                )
            )
            ordinal += 1
            sentences.append(
                OutputSentence(
                    id=f"{output_id}_{ordinal}",
                    output_id=output_id,
                    ordinal=ordinal,
                    text=human_view.strip(),
                    type="opinion",
                )
            )
            ordinal += 1

        # 4. Lint sentences against boilerplate / raw topic string
        is_lint_clean, lint_issues = lint_output_text(sentences, raw_topic=question.text)

        # 5. Run Hard Gate Checker
        source_texts = {sid: f"{src.title} {src.url or ''}" for sid, src in sources.items()}
        gate_res = self.checker.check_output(
            sentences=sentences,
            ledger_claims=claims_by_id,
            source_texts=source_texts,
            sources=sources,
            question=question,
            papers=papers,
        )

        # 6. Run Quality Scorer (Evidence-based S4, S6, S7)
        reviewed_claims = {c.id for c in claims_by_id.values() if getattr(c, "status", "") in ("approved", "edited")}

        score_res = self.scorer.calculate_score(
            gate_result=gate_res,
            sentences=sentences,
            ledger_claims=claims_by_id,
            sources=sources,
            questions=[question],
            reviewed_claim_ids=reviewed_claims,
            human_gates_completed_count=0,
            cached_papers=papers,
        )

        # 7. Persist Output and Sentences
        output_status = "draft" if gate_res.passed else "blocked"
        doc = OutputDoc(
            id=output_id,
            run_id=run_id,
            kind="field_note",
            version=1,
            path=f"outputs/reports/field_note_{question.id}.md",
            status=output_status,
            score_json=score_res,
            gates_json=gate_res.to_dict(),
        )
        if os.getenv("HOSTED_DEMO") != "1":
            self.repo.insert_output(doc)
            for s in sentences:
                self.repo.insert_output_sentence(s)

        summary = {
            "output_id": output_id,
            "status": output_status,
            "gap_outcome": gap_entry.outcome,
            "sentences_count": len(sentences),
            "assertive_sentences_count": sum(1 for s in sentences if s.type == "assertive"),
            "gate_results": gate_res.to_dict(),
            "score_results": score_res,
            "lint_issues": lint_issues,
        }

        return doc, sentences, summary
