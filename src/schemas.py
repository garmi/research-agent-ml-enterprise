from __future__ import annotations

from typing import Any, Dict, List, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    return str(value)


class PaperSummary(BaseModel):
    """Structured per-paper extraction (map step). Lenient: small local models drift."""

    model_config = ConfigDict(extra="ignore")

    title: str = ""
    year: Union[int, str, None] = None
    source: str = ""
    problem_statement: str = ""
    key_findings: str = ""
    research_method: str = ""
    limitations: str = ""
    business_relevance: str = ""
    engineering_relevance: str = ""
    gap_identified: str = ""
    strategic_opportunity: str = ""
    adoption_barrier: str = ""
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator(
        "problem_statement", "key_findings", "research_method", "limitations",
        "business_relevance", "engineering_relevance", "gap_identified",
        "strategic_opportunity", "adoption_barrier", "title", "source",
        mode="before",
    )
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        return _to_text(value)

    @field_validator("confidence_score", mode="before")
    @classmethod
    def _coerce_conf(cls, value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.5
        if number > 1:
            number = number / 10 if number <= 10 else 1.0
        return max(0.0, min(1.0, number))


class Theme(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = ""
    description: str = ""


class RoadmapPhase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    stage: str = ""
    objective: str = ""
    actions: List[str] = Field(default_factory=list)
    kpis: List[str] = Field(default_factory=list)


class ResearchSynthesisModel(BaseModel):
    """Validated reduce-step output."""

    model_config = ConfigDict(extra="ignore")

    executive_summary: str = ""
    objective: str = ""
    research_questions: List[str] = Field(default_factory=list)
    key_findings: List[str] = Field(default_factory=list)
    themes: List[Theme] = Field(default_factory=list)
    market_trends: List[str] = Field(default_factory=list)
    business_problems: List[str] = Field(default_factory=list)
    research_gaps: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    strategic_roadmap: List[RoadmapPhase] = Field(default_factory=list)
    content_ideas: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)
    # S19: the question-shaped report
    answer: List[str] = Field(default_factory=list)
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    tensions: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    implications: List[Dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
