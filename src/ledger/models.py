"""Pydantic data models for Research Engine v2 ledger schema."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

LaneType = Literal["academic", "enterprise", "practitioner"]
SourceType = Literal[
    "peer_reviewed", "preprint", "vendor_blog", "customer_case_study",
    "analyst_survey", "regulator_standard", "filing", "incident_report",
    "job_posting", "practitioner_note"
]
VenueTier = Literal["verified", "reputable_preprint", "unverified", "vendor", "n/a"]
ExtractionDepth = Literal["abstract_only", "full_text", "structured_data"]
CommercialStake = Literal["none", "vendor", "sponsored", "unknown"]
EntityMatch = Literal["exact", "family", "topic_level", "mismatch"]
StudyType = Literal[
    "field_experiment", "controlled_study", "survey_with_method",
    "case_study", "position_paper", "conceptual_framework",
    "vendor_assertion", "filing_disclosure", "practitioner_observation"
]
ClaimGrade = Literal["strong", "moderate", "weak", "vendor_claim", "anecdote"]
ClaimStatus = Literal["auto", "approved", "edited", "rejected"]
OutputKind = Literal["field_note", "strategy_doc", "json_export"]
OutputStatus = Literal["draft", "in_review", "published", "blocked", "legacy-ungraded"]
SentenceType = Literal["assertive", "opinion", "field", "heading"]


def now_utc_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Question(BaseModel):
    id: str
    text: str
    scope: Optional[str] = "enterprise"
    time_window_months: int = 36
    status: Literal["draft", "active", "retired"] = "active"
    version: int = 1
    created_at: str = Field(default_factory=now_utc_iso)


class Source(BaseModel):
    id: str
    lane: LaneType
    source_type: SourceType
    org: Optional[str] = None
    title: str
    url: Optional[str] = None
    doi: Optional[str] = None
    venue: Optional[str] = None
    venue_tier: VenueTier = "unverified"
    pub_date: Optional[str] = None
    retrieved_at: Optional[str] = None
    content_hash: Optional[str] = None
    extraction_depth: ExtractionDepth = "abstract_only"
    commercial_stake: CommercialStake = "unknown"
    status: str = "active"
    created_at: str = Field(default_factory=now_utc_iso)


class Claim(BaseModel):
    id: str
    question_id: Optional[str] = None
    source_id: str
    text: str  # Paraphrase, never a copy
    source_excerpt: str  # Max 25 words with location
    value_json: Optional[Dict[str, Any]] = None  # Numbers with units and basis
    entity: Optional[str] = None
    entity_match: EntityMatch = "topic_level"
    study_type: StudyType = "position_paper"
    context_json: Optional[Dict[str, Any]] = None
    claim_date: Optional[str] = None
    extraction_model: Optional[str] = None
    extraction_confidence: float = 1.0
    grade: ClaimGrade = "weak"
    grade_reasons_json: Optional[List[str]] = None
    status: ClaimStatus = "auto"
    observations_count: int = 1
    created_at: str = Field(default_factory=now_utc_iso)


class ClaimLink(BaseModel):
    claim_a: str
    claim_b: str
    relation: Literal["corroborates", "contradicts", "supersedes", "duplicate_source"]
    created_at: str = Field(default_factory=now_utc_iso)


class Run(BaseModel):
    id: str
    started_at: str = Field(default_factory=now_utc_iso)
    config_json: Optional[Dict[str, Any]] = None
    code_version: Optional[str] = None
    model_ids: Optional[Dict[str, str]] = None
    question_ids: Optional[List[str]] = None
    seed: Optional[int] = 42
    created_at: str = Field(default_factory=now_utc_iso)


class SearchLog(BaseModel):
    id: str
    run_id: Optional[str] = None
    question_id: Optional[str] = None
    lane: str
    query: str
    source_api: str
    result_count: int = 0
    executed_at: str = Field(default_factory=now_utc_iso)
    created_at: str = Field(default_factory=now_utc_iso)


class GapMatrixEntry(BaseModel):
    id: str
    run_id: Optional[str] = None
    question_id: str
    academic_state: Optional[str] = "none found"
    enterprise_state: Optional[str] = "none found"
    field_state: Optional[str] = "none found"
    outcome: Literal[1, 2, 3, 4]
    rationale: Optional[str] = None
    status: str = "active"
    created_at: str = Field(default_factory=now_utc_iso)


class Review(BaseModel):
    id: str
    gate: str
    object_type: str
    object_id: str
    action: str
    before_json: Optional[Dict[str, Any]] = None
    after_json: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    reviewer: str
    ts: str = Field(default_factory=now_utc_iso)
    created_at: str = Field(default_factory=now_utc_iso)


class OutputDoc(BaseModel):
    id: str
    run_id: Optional[str] = None
    kind: OutputKind
    version: int = 1
    path: Optional[str] = None
    status: OutputStatus = "draft"
    score_json: Optional[Dict[str, Any]] = None
    gates_json: Optional[Dict[str, Any]] = None
    created_at: str = Field(default_factory=now_utc_iso)


class OutputSentence(BaseModel):
    id: str
    output_id: str
    ordinal: int
    text: str
    type: SentenceType
    claim_ids_json: Optional[List[str]] = None
    strength_verb: Optional[str] = None
    checks_json: Optional[Dict[str, Any]] = None
    created_at: str = Field(default_factory=now_utc_iso)
