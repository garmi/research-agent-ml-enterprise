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
from src.ledger.db import default_ledger_path
from src.ledger.models import Claim, OutputDoc, OutputSentence, Question, Run, Source
from src.ledger.repository import LedgerRepository
from src.analysis.relevance import support_terms
from src.extract.claim_extractor import strip_claim_prefix
from src.score.checker import GateChecker, claim_has_numeral, claim_support_terms, extract_numerals
from src.score.scorer import QualityScorer

logger = logging.getLogger(__name__)


MAX_CLAIMS_PER_TAG = 3
MIN_SUPPORT_TERMS = 2  # the same overlap G2 requires between a sentence and each claim it cites


def best_supporting_claims(text: str, candidates: List[Claim]) -> List[str]:
    """The claims of one paper that support this sentence (S10, S17). A claim qualifies when it shares at
    least MIN_SUPPORT_TERMS content terms with the sentence (quote plus full source sentence), or holds
    one of the sentence's own figures. Figure-holding claims rank first, then by overlap, at most
    MAX_CLAIMS_PER_TAG. With none qualifying, the single closest claim is kept, so G2 reports the weak
    support rather than the sentence going unbound."""
    if not candidates:
        return []
    s_terms = support_terms(text)
    numerals = extract_numerals(text)
    scored = []
    for order, c in enumerate(candidates):
        overlap = len(s_terms & claim_support_terms(c))
        figures = sum(1 for n in numerals if claim_has_numeral(c, n))
        scored.append((figures, overlap, -order, c.id))
    scored.sort(reverse=True)
    qualified = [cid for figures, overlap, _, cid in scored if overlap >= MIN_SUPPORT_TERMS or figures > 0]
    return qualified[:MAX_CLAIMS_PER_TAG] or [scored[0][3]]


def resolve_citations(
    text: str,
    papers: List[Dict[str, Any]],
    eligible_claims: List[Claim],
    claims_by_id: Dict[str, Claim],
    enterprise: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """Claim ids a sentence cites through its own tags, in order: [P#] means the claims from that
    paper that support the sentence (best_supporting_claims), [c_...] means that claim. No tag, or
    only unknown tags, means no claims."""
    cited: List[str] = []
    # S17: each tag is linked using the sentence that contains it, not the whole paragraph (a bottom
    # line cites several papers, one sentence each). A bracket may hold one id or a group ("[P1, P3]",
    # "[c_a; c_b]"); other brackets are ignored.
    pairs = [(sentence, group) for sentence in re.split(r"(?<=[.!?])\s+", text or "")
             for group in re.findall(r"\[([^\[\]]+)\]", sentence)]
    for sentence, group in pairs:
        for token in re.split(r"[,;\s]+", group.strip()):
            p = re.fullmatch(r"P(\d+)", token)
            e = re.fullmatch(r"E\d+", token)
            if e:
                # S22: [E#] is an enterprise document, found by key among the enterprise entries (or the papers list).
                entry = next((d for d in list(enterprise or []) + list(papers) if d.get("key") == token), None)
                sid = entry.get("id") if entry else None
                ids = best_supporting_claims(sentence, [c for c in eligible_claims if sid is not None and c.source_id == sid])
            elif p:
                idx = int(p.group(1)) - 1
                pid = papers[idx].get("id") if 0 <= idx < len(papers) else None
                ids = best_supporting_claims(sentence, [c for c in eligible_claims if pid is not None and c.source_id == pid])
            elif token.startswith("c_") and token in claims_by_id:
                ids = [token]
            else:
                ids = []
            cited.extend(i for i in ids if i not in cited)
    return cited


def search_log_negative_findings(slogs: List[Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Rule-built 'searched, nothing found' / 'not searched' statements, each tied to its search_log row."""
    searched_zero = [s for s in slogs if getattr(s, "status", "searched_ok") == "searched_ok" and s.result_count == 0]
    unsearched = [s for s in slogs if getattr(s, "status", "searched_ok") in ("not_implemented", "not_searched", "skipped_by_scope")]
    out: List[Tuple[str, Dict[str, Any]]] = []
    seen: Set[str] = set()

    from src.analysis.queries import condense

    # Searches that returned nothing: one line per lane, naming each source and the question's key terms
    # (S17; the full question was repeated on every line).
    empty: Dict[str, List[Any]] = {}
    for slog in searched_zero:
        empty.setdefault(slog.lane, []).append(slog)
    for lane, rows in empty.items():
        names: List[str] = []
        for r in rows:
            if r.source_api not in names:
                names.append(r.source_api)
        text = f"{lane.capitalize()} searches that returned no records for '{condense(rows[0].query)}': {', '.join(names)}."
        if text not in seen:
            seen.add(text)
            out.append((text, {"search_log_id": rows[0].id, "search_log_ids": [r.id for r in rows]}))
    # Sources that were not searched: one line per lane and reason, naming the sources (S11). The
    # question appears as its key terms only (it differs per run, so two briefs never share the line);
    # each line keeps every search_log row it stands for.

    groups: Dict[Tuple[str, str], List[Any]] = {}
    for slog in unsearched:
        reason = "no fetcher yet" if getattr(slog, "status", "") == "not_implemented" else "no observations recorded"
        groups.setdefault((slog.lane, reason), []).append(slog)
    for (lane, reason), rows in groups.items():
        names: List[str] = []
        for r in rows:
            if r.source_api not in names:
                names.append(r.source_api)
        about = condense(rows[0].query)
        text = f"{lane.capitalize()} sources not searched for '{about}' ({reason}): {', '.join(names)}."
        if text not in seen:
            seen.add(text)
            out.append((text, {"search_log_id": rows[0].id, "search_log_ids": [r.id for r in rows]}))
    return out


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
        db_path: Optional[str] = None,
        verbs_path: str = "synth/strength_verbs.yaml",
        scoring_path: str = "score/scoring.yaml",
    ):
        self.db_path = db_path or default_ledger_path()
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
        # A run passes its own claims; only fall back to every ledger claim for the question without one.
        if claims_override is not None:
            all_claims = [c for c in claims_override if c.question_id == question_id or not c.question_id]
        else:
            all_claims = self.repo.list_claims(question_id=question_id)
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

        def bind(text: str) -> Tuple[List[str], Optional[Dict[str, Any]]]:
            cids = resolve_citations(text, papers or [], eligible_claims, claims_by_id,
                                     enterprise=(executive_synthesis or {}).get("enterprise_docs"))
            return cids, (None if cids else {"binding": "unbound"})

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

        # Bottom line (S10): a gated sentence like any finding. It cites only what its own tags point
        # to; an untagged bottom line stays unbound and fails G1 instead of passing as free prose.
        bottom_line = str((executive_synthesis or {}).get("executive_summary") or "").strip()
        if bottom_line:
            bl_cids, bl_checks = bind(bottom_line)
            sentences.append(
                OutputSentence(
                    id=f"{output_id}_{ordinal}",
                    output_id=output_id,
                    ordinal=ordinal,
                    text=bottom_line,
                    type="summary",
                    claim_ids_json=bl_cids,
                    checks_json=bl_checks,
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

        # S19: the question-shaped report. One heading per approved sub-question, then that section's
        # synthesis and evidence sentences, each tagged with its section number.
        report_sections = [s for s in ((executive_synthesis or {}).get("sections") or []) if isinstance(s, dict)]

        def add(text: str, type_: str, section: Optional[int] = None) -> None:
            nonlocal ordinal
            cids, checks = bind(text) if type_ != "heading" else ([], None)
            if section is not None:
                checks = {**(checks or {}), "section": section}
            sentences.append(OutputSentence(
                id=f"{output_id}_{ordinal}", output_id=output_id, ordinal=ordinal, text=text.strip(), type=type_,
                claim_ids_json=cids if type_ != "heading" else None, checks_json=checks,
            ))
            ordinal += 1

        if report_sections:
            for i, sec in enumerate(report_sections, 1):
                add(str(sec.get("sub_question") or f"Section {i}"), "heading", i)
                for t in sec.get("synthesis") or []:
                    add(str(t), "synthesis", i)
                for t in sec.get("evidence") or []:
                    add(str(t), "assertive", i)
            for t in (executive_synthesis or {}).get("tensions") or []:
                add(str(t), "tension")
            for t in (executive_synthesis or {}).get("gaps") or []:
                add(str(t), "gap")
            # An implication that names no section gets the section whose papers it shares most (a rule, not a guess
            # by the model); one sharing no paper with any section stays unassigned and fails G1.
            section_sources: Dict[int, Set[str]] = {}
            for s in sentences:
                sec_no = (s.checks_json or {}).get("section")
                if sec_no and s.type != "heading":
                    section_sources.setdefault(sec_no, set()).update(
                        claims_by_id[c].source_id for c in (s.claim_ids_json or []) if c in claims_by_id)
            for imp in (executive_synthesis or {}).get("implications") or []:
                if not (isinstance(imp, dict) and str(imp.get("text") or "").strip()):
                    continue
                section = imp.get("section")
                if not section:
                    own = {claims_by_id[c].source_id for c in bind(str(imp["text"]))[0] if c in claims_by_id}
                    best = max(section_sources.items(), key=lambda kv: (len(kv[1] & own), -kv[0]), default=(None, set()))
                    section = best[0] if best[0] and best[1] & own else None
                add(str(imp["text"]), "implication", section)
        elif executive_synthesis and executive_synthesis.get("key_findings"):
            for f_text in executive_synthesis["key_findings"]:
                # Only the claims the sentence's own tags point to; an untagged sentence stays unbound.
                cited_cids, checks = bind(f_text)
                sentences.append(
                    OutputSentence(
                        id=f"{output_id}_{ordinal}",
                        output_id=output_id,
                        ordinal=ordinal,
                        text=f_text.strip(),
                        type="assertive",
                        claim_ids_json=cited_cids,
                        checks_json=checks,
                    )
                )
                ordinal += 1
        elif supported_claims:
            paper_id_to_tag = {
                p.get("id"): f"P{idx}"
                for idx, p in enumerate(papers or [], 1)
                if p.get("id")
            }
            for c in supported_claims[:8]:
                verb = self._select_verb_for_grade(c.grade)
                c_text = strip_claim_prefix(c.text).rstrip(".")
                p_tag = paper_id_to_tag.get(c.source_id)
                prefix_tag = f"[{p_tag}] " if p_tag else ""
                # S16: each sentence rests on one claim, so a figure is attributed to one study.
                subject = "One study" if extract_numerals(c_text) else "Empirical literature"
                text = f"{prefix_tag}{subject} {verb} that {c_text[0].lower() + c_text[1:] if c_text else ''}."
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

        # Signals restate findings. Model findings carry their own tags; signals copied from the
        # drafted findings keep those findings' claims (their text has no tags to resolve).
        assertive_by_text = {x.text: (x.claim_ids_json or []) for x in sentences if x.type == "assertive"}
        # Signals restate findings; a sectioned report already presents its evidence, so it has none (S19).
        signals_candidates = [] if report_sections else (
            (executive_synthesis.get("key_findings") or [])[:3]
            if executive_synthesis
            else list(assertive_by_text)[:3]
        )
        if signals_candidates:
            for sig in signals_candidates:
                sig_cids, sig_checks = bind(sig)
                if not sig_cids and assertive_by_text.get(sig):
                    sig_cids, sig_checks = list(assertive_by_text[sig]), None
                sentences.append(
                    OutputSentence(
                        id=f"{output_id}_{ordinal}",
                        output_id=output_id,
                        ordinal=ordinal,
                        text=sig.strip(),
                        type="signal",
                        claim_ids_json=sig_cids,
                        checks_json=sig_checks,
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
                r_cids, r_checks = bind(r)
                sentences.append(
                    OutputSentence(
                        id=f"{output_id}_{ordinal}",
                        output_id=output_id,
                        ordinal=ordinal,
                        text=r.strip(),
                        type="risk",
                        claim_ids_json=r_cids,
                        checks_json=r_checks,
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
        search_negatives = search_log_negative_findings(slogs)

        if search_negatives:
            for text, checks in search_negatives:
                sentences.append(
                    OutputSentence(
                        id=f"{output_id}_{ordinal}",
                        output_id=output_id,
                        ordinal=ordinal,
                        text=text,
                        type="negative_finding",
                        checks_json=checks,
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
            # Roadmap steps are recommendations (not gated), but each one records what it rests on (S10):
            # the findings citing the same papers, the KPI proposed for its phase, and any figure that
            # is not in the evidence the step cites.
            finding_sources = [
                {claims_by_id[cid].source_id for cid in (s.claim_ids_json or []) if cid in claims_by_id}
                for s in sentences if s.type == "assertive"
            ]
            for phase in roadmap_candidates:
                phase_title = phase.get("stage", "Phase") if isinstance(phase, dict) else "Phase"
                actions = phase.get("actions", []) if isinstance(phase, dict) else [str(phase)]
                kpis = [str(k) for k in (phase.get("kpis") or [])] if isinstance(phase, dict) else []
                for act in actions:
                    act_cids, act_checks = bind(str(act))
                    act_claims = [claims_by_id[cid] for cid in act_cids if cid in claims_by_id]
                    act_sources = {c.source_id for c in act_claims}
                    act_checks = {
                        **(act_checks or {}),
                        "builds_on": [i for i, srcs in enumerate(finding_sources, 1) if srcs & act_sources],
                        "kpis": kpis,
                        "unsupported_numbers": [
                            n for n in extract_numerals(str(act)) if not any(claim_has_numeral(c, n) for c in act_claims)
                        ],
                    }
                    sentences.append(
                        OutputSentence(
                            id=f"{output_id}_{ordinal}",
                            output_id=output_id,
                            ordinal=ordinal,
                            text=f"{phase_title}: {act}",
                            type="roadmap",
                            claim_ids_json=act_cids,
                            checks_json=act_checks,
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
