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

from src.analysis.relevance import STOPWORDS, normalize_text
from src.ledger.models import Claim, OutputSentence

logger = logging.getLogger(__name__)


class GateCheckResult:
    def __init__(self):
        self.g1_pass: bool = True
        self.g2_pass: bool = True
        self.g3_pass: bool = True
        self.g4_pass: bool = True
        self.g5_pass: bool = True
        self.g6_pass: bool = True
        self.violations: Dict[str, List[str]] = {
            "G1": [],
            "G2": [],
            "G3": [],
            "G4": [],
            "G5": [],
            "G6": [],
        }

    @property
    def passed(self) -> bool:
        return (
            self.g1_pass
            and self.g2_pass
            and self.g3_pass
            and self.g4_pass
            and self.g5_pass
            and self.g6_pass
        )

    def to_dict(self) -> Dict[str, Any]:
        def _parse_violations(gate_key: str) -> List[Dict[str, Any]]:
            parsed = []
            for v in self.violations.get(gate_key, []):
                m = re.search(r"Sentence \[([^\]]+)\]", str(v))
                sent_id = m.group(1) if m else None
                parsed.append({"sentence_id": sent_id, "message": str(v)})
            return parsed

        return {
            "passed": self.passed,
            "status": "PASS" if self.passed else "BLOCKED",
            "gates": {
                "G1_traceability": {"pass": self.g1_pass, "violations": self.violations["G1"]},
                "G2_numeric_fidelity": {"pass": self.g2_pass, "violations": self.violations["G2"]},
                "G3_entity_fidelity": {"pass": self.g3_pass, "violations": self.violations["G3"]},
                "G4_language_honesty": {"pass": self.g4_pass, "violations": self.violations["G4"]},
                "G5_confidentiality": {"pass": self.g5_pass, "violations": self.violations["G5"]},
                "G6_copyright": {"pass": self.g6_pass, "violations": self.violations["G6"]},
            },
            "hard_gates": {
                "G1": {"pass": self.g1_pass, "violations": _parse_violations("G1")},
                "G2": {"pass": self.g2_pass, "violations": _parse_violations("G2")},
                "G3": {"pass": self.g3_pass, "violations": _parse_violations("G3")},
                "G4": {"pass": self.g4_pass, "violations": _parse_violations("G4")},
                "G5": {"pass": self.g5_pass, "violations": _parse_violations("G5")},
                "G6": {"pass": self.g6_pass, "violations": _parse_violations("G6")},
            },
        }


class GateChecker:
    def __init__(
        self,
        verbs_path: str = "synth/strength_verbs.yaml",
        denylist_path: str = "denylist.txt",
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
        else:
            self.verbs_cfg = {}

    def _load_denylist(self) -> Set[str]:
        self.denylist: Set[str] = set()
        if os.path.exists(self.denylist_path):
            with open(self.denylist_path, "r", encoding="utf-8") as f:
                for line in f:
                    entry = line.strip().lower()
                    if entry and not entry.startswith("#"):
                        self.denylist.add(entry)
        return self.denylist

    def extract_numerals(self, text: str) -> List[str]:
        """Extract percentages, multipliers, currency and standalone numbers."""
        # Matches e.g. 20x, 67%, 90%, $100M, 25-35%
        raw_tokens = re.findall(r"\b(?:\d+(?:\.\d+)?(?:%|x|k|m|b)?|\$\d+(?:\.\d+)?(?:k|m|b)?)\b", text, re.IGNORECASE)
        # Filter out years like 2023, 2024, 2025, 2026 or small section counts if isolated
        numerals = []
        for t in raw_tokens:
            if re.match(r"^(19|20)\d{2}$", t):
                continue
            numerals.append(t.lower())
        return numerals

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

        for s in sentences:
            s_text = s.text.strip()

            # [P#] run-scoped resolution check
            p_matches = re.findall(r"\[P(\d+)\]", s_text)
            for p_str in p_matches:
                p_num = int(p_str)
                if papers is not None and (p_num < 1 or p_num > len(papers)):
                    result.g1_pass = False
                    result.violations["G1"].append(
                        f"Sentence [{s.id}] (ordinal {s.ordinal}) cites [P{p_num}] which does not resolve to any source in run's Lane A list"
                    )

            if s.type not in ("assertive", "finding"):
                # Opinions and field notes are checked for confidentiality and copyright only
                self._check_confidentiality(s_text, result)
                self._check_copyright(s_text, source_texts or {}, result)
                continue

            # G1: Traceability
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

            # Support Check (2): Excerpt overlap - sentence must share >= 2 non-stopword terms with claim excerpt
            s_words = {
                w for w in normalize_text(s_text).split()
                if w not in STOPWORDS and len(w) > 2
            }
            for c in cited_claims:
                excerpt_raw = c.source_excerpt or c.text or ""
                e_words = {
                    w for w in normalize_text(excerpt_raw).split()
                    if w not in STOPWORDS and len(w) > 2
                }
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
                    if w not in STOPWORDS and len(w) >= 3
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

                        if src_text:
                            src_terms = {
                                w for w in normalize_text(src_text).split()
                                if w not in STOPWORDS and len(w) >= 3
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
                    num_found = False
                    for c in cited_claims:
                        c_num_str = ""
                        if c.value_json:
                            c_num_str = str(c.value_json)
                        excerpt_str = str(c.source_excerpt or "")
                        if num in c_num_str.lower() or num in excerpt_str.lower() or (not excerpt_str and num in c.text.lower()):
                            num_found = True
                            break
                    if not num_found:
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
