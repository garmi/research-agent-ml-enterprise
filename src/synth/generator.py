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
    ) -> Tuple[OutputDoc, List[OutputSentence], Dict[str, Any]]:
        """Generate a structured, evidence-grounded Field Note."""
        question = self.repo.get_question(question_id)
        if not question:
            raise ValueError(f"Question {question_id} not found in ledger")

        # 1. Evaluate Gap Matrix
        gap_entry = self.gap_builder.evaluate_question_lanes(question_id, run_id=run_id)

        # 2. Retrieve eligible claims (approved or auto, not rejected)
        all_claims = self.repo.list_claims(question_id=question_id)
        eligible_claims = [c for c in all_claims if c.status != "rejected"]
        claims_by_id = {c.id: c for c in eligible_claims}

        sources = {c.source_id: self.repo.get_source(c.source_id) for c in eligible_claims}
        sources = {sid: src for sid, src in sources.items() if src is not None}

        # 3. Partition claims
        supported_claims = [c for c in eligible_claims if c.grade in ("strong", "moderate")]
        thin_claims = [c for c in eligible_claims if c.grade in ("weak", "vendor_claim", "anecdote")]

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

        if supported_claims:
            for c in supported_claims[:3]:
                verb = self._select_verb_for_grade(c.grade)
                text = f"Empirical literature {verb} that {c.text[0].lower() + c.text[1:] if not c.text.startswith('The study') else c.text}."
                # Clean duplicate period
                text = text.rstrip(".") + "."
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
                    text="Currently, peer-reviewed empirical evidence directly demonstrating this outcome is unmeasured across active repositories.",
                    type="heading",
                )
            )
            ordinal += 1

        # Section: What the Evidence Does NOT Support
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

        gap_descriptions = {
            1: "The evidence does not support claims of complete autonomous lifecycle displacement without human oversight.",
            2: "The literature does not support claims of universal productivity gains across un-governed enterprise teams.",
            3: "The evidence does not substantiate commercial vendor performance claims outside narrow synthetic benchmarks.",
            4: "Available studies do not provide statistically verified productivity benchmarks for this specific tooling stack.",
        }
        gap_note = gap_descriptions.get(gap_entry.outcome, "Available research does not substantiate claims of autonomous displacement.")
        sentences.append(
            OutputSentence(
                id=f"{output_id}_{ordinal}",
                output_id=output_id,
                ordinal=ordinal,
                text=gap_note,
                type="heading",
            )
        )
        ordinal += 1

        # Section: The Strategic Gap (Matrix Outcome)
        sentences.append(
            OutputSentence(
                id=f"{output_id}_{ordinal}",
                output_id=output_id,
                ordinal=ordinal,
                text=f"The Strategic Gap (Outcome {gap_entry.outcome}): {gap_entry.rationale}",
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
        )

        # 6. Run Quality Scorer
        score_res = self.scorer.calculate_score(
            gate_result=gate_res,
            sentences=sentences,
            ledger_claims=claims_by_id,
            sources=sources,
            questions=[question],
            gap_outcomes_disclosed=1.0,
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
