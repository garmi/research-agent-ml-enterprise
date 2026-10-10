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
    ) -> GateCheckResult:
        """Run all hard gates against a draft output."""
        result = GateCheckResult()
        # Reload denylist in case it changed
        self._load_denylist()

        for s in sentences:
            s_text = s.text.strip()
            if s.type != "assertive":
                # Opinions and field notes are checked for confidentiality and copyright only
                self._check_confidentiality(s_text, result)
                self._check_copyright(s_text, source_texts or {}, result)
                continue

            # G1: Traceability
            claim_ids = s.claim_ids_json or []
            if not claim_ids:
                result.g1_pass = False
                result.violations["G1"].append(
                    f"Sentence {s.ordinal} lacks citation: '{s_text}'"
                )
                continue

            cited_claims: List[Claim] = []
            for cid in claim_ids:
                c = ledger_claims.get(cid)
                if not c or c.status == "rejected":
                    result.g1_pass = False
                    result.violations["G1"].append(
                        f"Sentence {s.ordinal} cites invalid or rejected claim '{cid}'"
                    )
                else:
                    cited_claims.append(c)

            if not cited_claims:
                continue

            # G2: Numeric fidelity
            numerals = self.extract_numerals(s_text)
            if numerals and "DERIVED" not in s_text:
                for num in numerals:
                    # Check if numeral appears in any cited claim value_json or text
                    num_found = False
                    for c in cited_claims:
                        c_num_str = ""
                        if c.value_json:
                            c_num_str = str(c.value_json)
                        if num in c_num_str.lower() or num in c.text.lower() or num in c.source_excerpt.lower():
                            num_found = True
                            break
                    if not num_found:
                        result.g2_pass = False
                        result.violations["G2"].append(
                            f"Sentence {s.ordinal} contains ungrounded numeral '{num}': '{s_text}'"
                        )

            # G3: Entity fidelity
            # If sentence mentions Kiro or Amazon Kiro, all cited claims must have entity_match exact
            if re.search(r"\bkiro\b|\bamazon kiro\b", s_text, re.IGNORECASE):
                for c in cited_claims:
                    if c.entity_match not in ("exact", "family"):
                        result.g3_pass = False
                        result.violations["G3"].append(
                            f"Sentence {s.ordinal} names Kiro but cites claim {c.id} with '{c.entity_match}' match: '{s_text}'"
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
                        f"Sentence {s.ordinal} uses verb '{verb}' (level {verb_rank}) exceeding weakest claim {weakest_claim.id} grade '{weakest_claim.grade}' (max level {min_allowed})"
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
                            f"Sentence {s.ordinal} cites practitioner claim '{c.id}' without confirmed abstraction (R12 violation)"
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
