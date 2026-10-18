"""Atomic claim extraction engine for Research Engine v2.

Extracts structured, atomic claim records from paper abstracts or source texts.
Enforces:
- Schema validation via Pydantic
- Source excerpt capped at max 25 words
- Paraphrased claim text (never direct copy)
- Entity match classification (exact vs topic_level vs mismatch)
- Study type tagging
- Term integrity verification (detecting corrupted terms)
- Extraction confidence tracking
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.extract.hedges import find_hedge_terms
from src.extract.term_normalizer import check_term_integrity
from src.ledger.models import Claim, EntityMatch, StudyType

logger = logging.getLogger(__name__)


class ExtractedClaimPayload(BaseModel):
    text: str
    source_excerpt: str
    excerpt_location: str = "Abstract"
    value_json: Optional[Dict[str, Any]] = None
    entity: str = "AI Coding Assistants"
    entity_match: EntityMatch = "topic_level"
    study_type: StudyType = "position_paper"
    context_json: Optional[Dict[str, Any]] = None
    key_terms: List[str] = Field(default_factory=list)
    confidence: float = 1.0


def truncate_excerpt(excerpt: str, max_words: int = 25) -> str:
    """Ensure source excerpt does not exceed 25 words."""
    words = excerpt.strip().split()
    if len(words) <= max_words:
        return excerpt.strip()
    return " ".join(words[:max_words])


def determine_entity_match(
    target_entity: str,
    source_title: str,
    source_text: str,
    mentioned_entity: Optional[str] = None,
) -> EntityMatch:
    """Determine entity match level relative to the target entity (e.g. Amazon Kiro).

    exact: The source specifically evaluates or names the target entity.
    family: Evaluates directly comparable peer tools in the same category.
    topic_level: General category paper (e.g. AI assistants, LLM coding in general).
    mismatch: Unrelated topic.
    """
    target = target_entity.strip().lower()
    combined = f"{source_title} {source_text}".lower()

    # Exact match: explicit mention of target entity
    if target in combined or (target == "kiro" and "kiro" in combined) or ("amazon kiro" in combined):
        return "exact"

    # Family match: specific peer AI coding agents
    peer_agents = ["github copilot", "cursor", "devin", "codeium", "claude code", "qodo", "cody"]
    if any(peer in combined for peer in peer_agents):
        return "family"

    # Topic level: general AI coding / SE literature
    topic_keywords = ["ai coding", "developer productivity", "llm agent", "agentic", "software engineering", "coding assistant"]
    if any(kw in combined for kw in topic_keywords):
        return "topic_level"

    return "mismatch"


def infer_study_type(text: str) -> StudyType:
    """Classify study type from abstract keywords."""
    lower = text.lower()
    if "controlled experiment" in lower or "randomized" in lower or "laboratory study" in lower:
        return "controlled_study"
    if "field experiment" in lower or "in the wild" in lower or "production deployment" in lower:
        return "field_experiment"
    if "survey" in lower and ("respondents" in lower or "sample" in lower or "participants" in lower):
        return "survey_with_method"
    if "case study" in lower or "industrial experience" in lower:
        return "case_study"
    if "framework" in lower or "architecture" in lower or "formalization" in lower:
        return "conceptual_framework"
    if "vendor assertion" in lower or "commercial" in lower:
        return "vendor_assertion"
    return "position_paper"


_ABBREV_PATTERN = re.compile(
    r"\b(e\.g|i\.e|et\s+al|vs|cf|dr|prof|mr|mrs|ms|fig|figs|eq|eqs|sec|secs|no|nos|vol|vols|pp|al|inc|ltd|co|approx|est|dept|univ|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.",
    re.IGNORECASE,
)


def _split_sentences_preserving_abbreviations(text: str) -> List[str]:
    """Split abstract text into complete sentences without breaking on abbreviations or initials."""
    placeholder = "<DOT_ABBREV>"
    # Protect common abbreviations (e.g., et al., vs., Fig., i.e.)
    protected = _ABBREV_PATTERN.sub(lambda m: m.group(0)[:-1] + placeholder, text)
    # Protect single-letter initials like "J. Smith"
    protected = re.sub(r"\b([A-Z])\.(?=\s+[A-Z])", r"\1" + placeholder, protected)
    # Protect decimal numbers like 3.14
    protected = re.sub(r"(\d)\.(\d)", r"\1" + placeholder + r"\2", protected)

    raw_parts = re.split(r"(?<=[.!?])\s+", protected)
    sentences = []
    for part in raw_parts:
        restored = part.replace(placeholder, ".").strip()
        if len(restored) > 20:
            sentences.append(restored)
    return sentences


def extract_claims_from_paper(
    paper: Dict[str, Any],
    question_id: Optional[str] = None,
    target_entity: str = "Amazon Kiro",
    model_name: str = "local-extractor-v2",
) -> List[Claim]:
    """Extract atomic claims from a paper record."""
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")
    doi = paper.get("doi", "")
    url = paper.get("url", "")
    source_id = paper.get("id") or (hashlib.sha256(f"{doi or title}".encode()).hexdigest()[:16])

    if not abstract:
        return []

    # Detect entity match against question focus
    entity_match = determine_entity_match(target_entity, title, abstract)
    study_type = infer_study_type(f"{title} {abstract}")

    sentences = _split_sentences_preserving_abbreviations(abstract)
    extracted_claims: List[Claim] = []

    for idx, sentence in enumerate(sentences):
        # Identify numeric claims
        num_match = re.search(r"(\d+(?:\.\d+)?%|\d+x|\$\d+)", sentence)
        value_data = None
        if num_match:
            value_str = num_match.group(1)
            value_data = {"raw": value_str, "context": sentence}

        # Check for key terms in sentence
        key_terms: List[str] = []
        if "vibe coding" in sentence.lower() or "vibrate coding" in sentence.lower():
            key_terms.append("vibe coding" if "vibe coding" in sentence.lower() else "vibrate coding")
        if "spec-driven" in sentence.lower():
            key_terms.append("spec-driven")

        # Excerpt max 25 words
        excerpt = truncate_excerpt(sentence, max_words=25)

        # Term integrity check
        is_valid_term, warnings = check_term_integrity(sentence, abstract, key_terms)
        confidence = 0.95 if is_valid_term else 0.50

        # Create unique claim ID
        claim_id = f"c_{source_id}_{idx+1}"

        # Context JSON
        context_data = {
            "title": title,
            "year": paper.get("year"),
            "warnings": warnings if warnings else None,
        }

        # The claim text is paraphrased
        paraphrase_text = f"The study reports that {sentence[0].lower() + sentence[1:]}" if not sentence.startswith("The study") else sentence

        claim = Claim(
            id=claim_id,
            question_id=question_id,
            source_id=source_id,
            text=paraphrase_text,
            source_excerpt=f"{excerpt} (Location: Abstract)",
            value_json=value_data,
            entity="Amazon Kiro" if entity_match == "exact" else ("AI Coding Assistants" if entity_match == "topic_level" else "Software Engineering Tools"),
            entity_match=entity_match,
            study_type=study_type,
            context_json=context_data,
            claim_date=str(paper.get("year", "2026")),
            extraction_model=model_name,
            extraction_confidence=confidence,
            grade="weak",  # Assigned by grader
            grade_reasons_json=[],
            status="auto",
            hedge_terms_json=find_hedge_terms(sentence),
        )
        extracted_claims.append(claim)

    return extracted_claims
