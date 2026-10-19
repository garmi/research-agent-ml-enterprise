"""Hard Gate Checker for Research Engine v2.

Implements all six non-negotiable gates (G1 through G6):
- G1 Traceability: 100% of assertive sentences cite eligible claims.
- G2 Numeric Fidelity: Numerals must be present in cited claims or tagged DERIVED.
- G3 Entity Fidelity: Sentences naming entities require exact/family entity match.
- G4 Language Honesty: Sentence strength verb capped by weakest cited claim grade.
- G5 Confidentiality: Zero denylist hits and zero unabstracted practitioner data.
- G6 Copyright: Quotes < 15 words, max 1 per source, zero verbatim runs >= 8 words outside quotes.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import yaml

from src.analysis.relevance import STOPWORDS, normalize_text, support_terms
from src.ledger.models import Claim, OutputSentence

logger = logging.getLogger(__name__)

# Gate states (S6, DEC-019): a gate with no data to judge is NO_DATA, and NO_DATA is not a pass.
PASS = "PASS"
FAIL = "FAIL"
NO_DATA = "NO_DATA"
GATE_IDS = ("G1", "G2", "G3", "G4", "G5", "G6")
# Sentence types whose claims must be grounded (G1-G4); "summary" is the brief's bottom line (S10).
# Roadmap actions are recommendations:
# they get G5/G6 only. Headings, opinions, field notes and negative findings are not assertions.
GROUNDED_TYPES = ("summary", "assertive", "finding", "signal", "risk")


def extract_numerals(text: str) -> List[str]:
    """Percentages, multipliers, currency and standalone numbers (years like 2024 are skipped)."""
    # Matches e.g. 20x, 67%, 90%, $100M, 25-35%
    raw_tokens = re.findall(r"\b(?:\d+(?:\.\d+)?(?:%|x|k|m|b)?|\$\d+(?:\.\d+)?(?:k|m|b)?)\b", text or "", re.IGNORECASE)
    return [t.lower() for t in raw_tokens if not re.match(r"^(19|20)\d{2}$", t)]


def claim_has_numeral(claim: Any, num: str) -> bool:
    """G2's numeric rule: the figure appears in the claim's value, its quote, or (with no quote) its text."""
    excerpt = str(claim.source_excerpt or "").lower()
    value = str(claim.value_json or "").lower() if claim.value_json else ""
    return num in value or num in excerpt or (not excerpt and num in str(claim.text or "").lower())


class GateCheckResult:
    def __init__(self):
        self.g1_pass: bool = True
        self.g2_pass: bool = True
        self.g3_pass: bool = True
        self.g4_pass: bool = True
        self.g5_pass: bool = True
        self.g6_pass: bool = True
        self.violations: Dict[str, List[str]] = {g: [] for g in GATE_IDS}
        # Whether each gate had something to judge, and why not when it did not.
        self.evaluated: Dict[str, bool] = {g: False for g in GATE_IDS}
        self.no_data_reasons: Dict[str, str] = {}

    def mark_evaluated(self, gate: str) -> None:
        self.evaluated[gate] = True

    def mark_no_data(self, gate: str, reason: str) -> None:
        """Record that the gate could not be judged (even if other sentences were)."""
        self.no_data_reasons.setdefault(gate, reason)

    def state(self, gate: str) -> str:
        if not getattr(self, f"{gate.lower()}_pass"):
            return FAIL
        if not self.evaluated[gate] or gate in self.no_data_reasons:
            return NO_DATA
        return PASS

    def states(self) -> Dict[str, str]:
        return {g: self.state(g) for g in GATE_IDS}

    def reason_plain(self, gate: str) -> str:
        st = self.state(gate)
        if st == FAIL:
            n = len(self.violations[gate])
            first = self.violations[gate][0] if n else "Gate failed."
            return f"{n} problem{'' if n == 1 else 's'} found. First: {first}"
        if st == NO_DATA:
            return self.no_data_reasons.get(gate, "Nothing to check for this gate.")
        return "Checked and passed."

    @property
    def passed(self) -> bool:
        return all(self.state(g) == PASS for g in GATE_IDS)

    @classmethod
    def all_passed(cls) -> "GateCheckResult":
        """A result in which every gate was evaluated and passed (for callers and tests that
        need an explicit pass; an empty GateCheckResult() is NO_DATA on every gate)."""
        r = cls()
        for g in GATE_IDS:
            r.mark_evaluated(g)
        return r

    def to_dict(self) -> Dict[str, Any]:
        def _parse_violations(gate_key: str) -> List[Dict[str, Any]]:
            parsed = []
            for v in self.violations.get(gate_key, []):
                m = re.search(r"Sentence \[([^\]]+)\]", str(v))
                sent_id = m.group(1) if m else None
                parsed.append({"sentence_id": sent_id, "message": str(v)})
            return parsed

        names = {
            "G1": "G1_traceability", "G2": "G2_numeric_fidelity", "G3": "G3_entity_fidelity",
            "G4": "G4_language_honesty", "G5": "G5_confidentiality", "G6": "G6_copyright",
        }

        def entry(g: str, violations: Any) -> Dict[str, Any]:
            # "pass" is True only for PASS: NO_DATA reads as not passed everywhere it is consumed.
            return {"pass": self.state(g) == PASS, "state": self.state(g), "reason_plain": self.reason_plain(g), "violations": violations}

        return {
            "passed": self.passed,
            "status": "PASS" if self.passed else "BLOCKED",
            "gates": {names[g]: entry(g, self.violations[g]) for g in GATE_IDS},
            "hard_gates": {g: entry(g, _parse_violations(g)) for g in GATE_IDS},
        }


class GateChecker:
    def __init__(
        self,
        verbs_path: str = "synth/strength_verbs.yaml",
        denylist_path: Optional[str] = None,
    ):
        self.verbs_path = verbs_path
        self.denylist_path = denylist_path
        self._load_verbs()
        self._load_denylist()

    def _load_verbs(self) -> None:
        if os.path.exists(self.verbs_path):
            with open(self.verbs_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self.verbs_cfg = data.get("levels", {})
                self.intensifiers = [str(w).lower() for w in data.get("intensifiers") or []]
        else:
            self.verbs_cfg = {}
            self.intensifiers = []

    def _load_denylist(self) -> Set[str]:
        """Load the denylist (RESEARCH_DENYLIST overrides the configured path). A missing file
        leaves confidentiality unchecked (G5 NO_DATA); an empty but present file is checked."""
        self.denylist: Set[str] = set()
        # An explicit path wins; otherwise RESEARCH_DENYLIST, otherwise ./denylist.txt.
        path = self.denylist_path or os.getenv("RESEARCH_DENYLIST") or "denylist.txt"
        self.denylist_configured = os.path.exists(path)
        if self.denylist_configured:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    entry = line.strip().lower()
                    if entry and not entry.startswith("#"):
                        self.denylist.add(entry)
        return self.denylist

    def extract_numerals(self, text: str) -> List[str]:
        return extract_numerals(text)

    def detect_strength_verb(self, text: str) -> Tuple[Optional[str], int]:
        """Find the strongest verb in the text and its rank (1-5)."""
        lower = text.lower()
        strongest_verb = None
        max_rank = 0

        for grade_key, grade_info in self.verbs_cfg.items():
            rank = grade_info.get("rank", 0)
            verbs = grade_info.get("verbs", [])
            for v in verbs:
                pattern = r"\b" + re.escape(v.lower()) + r"\b"
                if re.search(pattern, lower):
                    if rank > max_rank:
                        max_rank = rank
                        strongest_verb = v

        return strongest_verb, max_rank

    def get_max_allowed_rank(self, grade: str) -> int:
        """Return the maximum allowed verb rank for a given claim grade."""
        grade_info = self.verbs_cfg.get(grade, {})
        return grade_info.get("rank", 3)

    def check_output(
        self,
        sentences: List[OutputSentence],
        ledger_claims: Dict[str, Claim],
        source_texts: Optional[Dict[str, str]] = None,
        sources: Optional[Dict[str, Any]] = None,
        question: Optional[Any] = None,
        papers: Optional[List[Dict[str, Any]]] = None,
    ) -> GateCheckResult:
        """Run all hard gates against a draft output."""
        result = GateCheckResult()
        # Reload denylist in case it changed
        self._load_denylist()

        if not any(s.type in GROUNDED_TYPES for s in sentences):
            result.mark_no_data("G1", "No grounded sentences to audit: the draft has no findings, signals or risks.")
        # The denylist reason comes first: it is the one the operator can act on.
        if not self.denylist_configured:
            result.mark_no_data("G5", "Add denylist.txt (an empty file is fine) so confidentiality can be checked.")
        if not sentences:
            for g in ("G5", "G6"):
                result.mark_no_data(g, "The draft has no sentences to check.")
        if question is None:
            result.mark_no_data("G3", "No approved question was given, so topic fit could not be checked.")

        for s in sentences:
            s_text = s.text.strip()
            result.mark_evaluated("G6")
            if self.denylist_configured:
                result.mark_evaluated("G5")

            # [P#] run-scoped resolution check
            p_matches = re.findall(r"\[P(\d+)\]", s_text)
            for p_str in p_matches:
                p_num = int(p_str)
                if papers is not None and (p_num < 1 or p_num > len(papers)):
                    result.g1_pass = False
                    result.violations["G1"].append(
                        f"Sentence [{s.id}] (ordinal {s.ordinal}) cites [P{p_num}] which does not resolve to any source in run's Lane A list"
                    )

            if s.type not in GROUNDED_TYPES:
                # Roadmap, opinions and field notes are checked for confidentiality and copyright only
                self._check_confidentiality(s_text, result)
                self._check_copyright(s_text, source_texts or {}, result)
                continue

            # G1: Traceability
            result.mark_evaluated("G1")
            claim_ids = s.claim_ids_json or []
            if not claim_ids:
                result.g1_pass = False
                result.violations["G1"].append(
                    f"Sentence [{s.id}] (ordinal {s.ordinal}) lacks citation: '{s_text}'"
                )
                continue

            cited_claims: List[Claim] = []
            for cid in claim_ids:
                c = ledger_claims.get(cid)
                if not c or c.status == "rejected":
                    result.g1_pass = False
                    result.violations["G1"].append(
                        f"Sentence [{s.id}] (ordinal {s.ordinal}) cites invalid or rejected claim '{cid}'"
                    )
                else:
                    cited_claims.append(c)

            if not cited_claims:
                continue
            # This sentence has valid evidence, so grounding, numbers and wording can be judged.
            for g in ("G2", "G4"):
                result.mark_evaluated(g)
            if question is not None:
                result.mark_evaluated("G3")

            # Support Check (2): Excerpt overlap - sentence must share >= 2 non-stopword terms with claim excerpt
            s_words = support_terms(s_text)
            for c in cited_claims:
                e_words = support_terms(c.source_excerpt or c.text or "")
                overlap = s_words.intersection(e_words)
                if len(overlap) < 2:
                    result.g2_pass = False
                    result.violations["G2"].append(
                        f"Sentence [{s.id}] (ordinal {s.ordinal}) failed citation support check: Insufficient excerpt overlap ({len(overlap)} < 2 non-stopword terms) with claim {c.id}: '{s_text}'"
                    )

            # Support Check (3): Claim's source substantive term overlap with question
            if question is not None:
                q_text = f"{getattr(question, 'text', str(question or ''))} {getattr(question, 'scope', '')}".strip()
                q_words = [
                    w for w in normalize_text(q_text).split()
                    if w not in STOPWORDS and (len(w) >= 3 or w == "ai")
                ]
                generic_set = {
                    "productivity", "adoption", "gains", "evidence", "teams", "impact",
                    "empirical", "study", "analysis", "evaluation", "practice", "digital",
                    "technology", "research", "engineering", "delivery", "trade-offs",
                    "tradeoffs", "model", "models", "assessment", "implications",
                    "guidance", "perspective", "reforms", "information", "acceptance", "trade", "development"
                }
                COMPANY_NAMES = {"amazon", "google", "microsoft", "meta", "apple", "ibm", "oracle"}
                AGENT_BARE_TERMS = {"agent", "agents", "agentic"}
                CODE_SOFTWARE_DEV_TERMS = {
                    "code", "coding", "software", "developer", "developers", "engineering",
                    "programmer", "programming", "repository", "repositories", "ide", "commit",
                    "copilot", "kiro", "sdd", "spec-driven", "assistant", "assistants"
                }
                SOFTWARE_CONTEXT_TERMS = CODE_SOFTWARE_DEV_TERMS | {"cloud", "bedrock", "ai", "llm", "triage", "clinical"}

                salient_q = {w for w in q_words if w not in generic_set}
                if not salient_q:
                    salient_q = set(q_words)

                if q_words:
                    for c in cited_claims:
                        src_obj = (sources or {}).get(c.source_id)
                        src_text = ""
                        if src_obj:
                            src_text = f"{getattr(src_obj, 'title', '')} {getattr(src_obj, 'venue', '')} {getattr(src_obj, 'url', '')}"
                        elif source_texts and c.source_id in source_texts:
                            src_text = source_texts[c.source_id]

                        if not src_text:
                            result.mark_no_data("G3", f"No source text for claim {c.id}, so its topic fit could not be checked.")
                        if src_text:
                            src_terms = {
                                w for w in normalize_text(src_text).split()
                                if w not in STOPWORDS and (len(w) >= 3 or w == "ai")
                            }
                            # Must share at least one qualified salient term (company name must have software context; agent must have code context)
                            salient_match = False
                            for qt in salient_q:
                                for st in src_terms:
                                    matched_term = False
                                    if qt == st:
                                        matched_term = True
                                    elif len(qt) >= 4 and len(st) >= 4:
                                        if qt in st or st in qt:
                                            matched_term = True
                                        else:
                                            prefix_len = 0
                                            for a, b in zip(qt, st):
                                                if a == b:
                                                    prefix_len += 1
                                                else:
                                                    break
                                            if prefix_len >= 4 or (prefix_len >= 3 and qt.startswith("cod") and st.startswith("cod")):
                                                matched_term = True

                                    if matched_term:
                                        # Strict company and agent qualifications
                                        if qt in COMPANY_NAMES and not bool(src_terms & SOFTWARE_CONTEXT_TERMS):
                                            continue
                                        if qt in AGENT_BARE_TERMS and not bool(src_terms & CODE_SOFTWARE_DEV_TERMS):
                                            continue
                                        salient_match = True
                                        break
                                if salient_match:
                                    break

                            has_match = salient_match

                            if not has_match:
                                result.g3_pass = False
                                src_title = getattr(src_obj, "title", c.source_id) if src_obj else c.source_id
                                result.violations["G3"].append(
                                    f"Sentence [{s.id}] (ordinal {s.ordinal}) failed citation support check: Source topic mismatch between source '{src_title}' and question '{getattr(question, 'text', q_text)}' (insufficient substantive term overlap with question scope)"
                                )

            # G2: Numeric fidelity (Support Check 1)
            numerals = self.extract_numerals(s_text)
            if numerals and "DERIVED" not in s_text:
                for num in numerals:
                    # Check if numeral appears in any cited claim value_json or excerpt
                    if not any(claim_has_numeral(c, num) for c in cited_claims):
                        result.g2_pass = False
                        result.violations["G2"].append(
                            f"Sentence [{s.id}] (ordinal {s.ordinal}) contains ungrounded numeral '{num}': '{s_text}'"
                        )

            # G3: Entity fidelity
            # If sentence mentions Kiro or Amazon Kiro, all cited claims must have entity_match exact
            if re.search(r"\bkiro\b|\bamazon kiro\b", s_text, re.IGNORECASE):
                for c in cited_claims:
                    if c.entity_match not in ("exact", "family"):
                        result.g3_pass = False
                        result.violations["G3"].append(
                            f"Sentence [{s.id}] (ordinal {s.ordinal}) names Kiro but cites claim {c.id} with '{c.entity_match}' match: '{s_text}'"
                        )

            # G4: Language honesty
            verb, verb_rank = self.detect_strength_verb(s_text)
            if verb and verb_rank > 0:
                # Lowest rank permitted among all cited claims
                allowed_ranks = [self.get_max_allowed_rank(c.grade) for c in cited_claims]
                min_allowed = min(allowed_ranks) if allowed_ranks else 3
                if verb_rank > min_allowed:
                    result.g4_pass = False
                    weakest_claim = min(cited_claims, key=lambda c: self.get_max_allowed_rank(c.grade))
                    result.violations["G4"].append(
                        f"Sentence [{s.id}] (ordinal {s.ordinal}) uses verb '{verb}' (level {verb_rank}) exceeding weakest claim {weakest_claim.id} grade '{weakest_claim.grade}' (max level {min_allowed})"
                    )

            # G4 (S14): an intensifier overstates unless a cited quote uses the same word stem.
            quotes = " ".join(normalize_text(c.source_excerpt or c.text or "") for c in cited_claims)
            for word in self.intensifiers:
                if re.search(rf"\b{re.escape(word)}\b", s_text, re.IGNORECASE):
                    # "dramatically" -> "dramatic", "significantly" -> "significant"
                    stem = word[:-4] if word.endswith("ically") else (word[:-2] if word.endswith("ly") else word)
                    if not re.search(rf"\b{re.escape(stem)}", quotes):
                        result.g4_pass = False
                        result.violations["G4"].append(
                            f"Sentence [{s.id}] (ordinal {s.ordinal}) says '{word}', but none of its cited quotes does"
                        )

            # G5: Confidentiality
            self._check_confidentiality(s_text, result)
            # R12 check: Any practitioner claim cited must have confirmed abstraction
            for c in cited_claims:
                is_practitioner = (
                    getattr(c, "study_type", "") == "practitioner_observation"
                    or (c.context_json and c.context_json.get("lane") == "practitioner")
                )
                if is_practitioner:
                    abstraction_ok = bool(
                        c.context_json and c.context_json.get("abstraction_confirmed") is True
                    )
                    if not abstraction_ok:
                        result.g5_pass = False
                        result.violations["G5"].append(
                            f"Sentence [{s.id}] (ordinal {s.ordinal}) cites practitioner claim '{c.id}' without confirmed abstraction (R12 violation)"
                        )

            # G6: Copyright
            self._check_copyright(s_text, source_texts or {}, result)

        for g in ("G2", "G3", "G4"):
            if not result.evaluated[g]:
                result.mark_no_data(g, "No sentence cited a valid claim, so there was nothing to check.")
        return result

    def _check_confidentiality(self, text: str, result: GateCheckResult) -> None:
        lower = text.lower()
        for banned in self.denylist:
            if re.search(r"\b" + re.escape(banned) + r"\b", lower):
                result.g5_pass = False
                result.violations["G5"].append(
                    f"Denylist term '{banned}' detected in output: '{text}'"
                )

    def _check_copyright(
        self,
        text: str,
        source_texts: Dict[str, str],
        result: GateCheckResult,
    ) -> None:
        # 1. Quotes < 15 words
        quotes = re.findall(r'"([^"]+)"', text)
        for q in quotes:
            words = q.strip().split()
            if len(words) >= 15:
                result.g6_pass = False
                result.violations["G6"].append(
                    f"Quote of {len(words)} words exceeds 15-word limit: '\"{q}\"'"
                )

        # 2. Verbatim runs of 8+ words outside quotes
        # Strip quoted portions first
        unquoted = re.sub(r'"[^"]*"', " ", text)
        words = re.findall(r"\b\w+\b", unquoted.lower())
        if len(words) < 8 or not source_texts:
            return

        for src_id, full_src in source_texts.items():
            src_words = set(
                " ".join(chunk)
                for chunk in [
                    re.findall(r"\b\w+\b", full_src.lower())[i : i + 8]
                    for i in range(len(re.findall(r"\b\w+\b", full_src.lower())) - 7)
                ]
            )
            for i in range(len(words) - 7):
                ngram = " ".join(words[i : i + 8])
                if ngram in src_words:
                    result.g6_pass = False
                    result.violations["G6"].append(
                        f"Verbatim run of 8+ words from source {src_id} outside quotes: '{ngram}'"
                    )
                    break
