"""Strategic Question Formulation Agent for Research Engine v2.

Formulates well-rounded, rigorous Strategic Technology Questions from raw user
problem descriptions and business dilemmas. Automatically identifies evaluation scopes,
sub-questions, target entities, and registers questions into the YAML Question Register (Gate 1).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from src.ledger.models import Question
from src.ledger.service import LedgerService

logger = logging.getLogger(__name__)


@dataclass
class FormulatedQuestion:
    raw_input: str
    strategic_question: str
    suggested_id: str
    scope: str
    sub_questions: List[str]
    target_entities: List[str]
    time_window_months: int
    rationale: str
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_input": self.raw_input,
            "strategic_question": self.strategic_question,
            "suggested_id": self.suggested_id,
            "scope": self.scope,
            "sub_questions": self.sub_questions,
            "target_entities": self.target_entities,
            "time_window_months": self.time_window_months,
            "rationale": self.rationale,
            "keywords": self.keywords,
        }


class QuestionFormulationAgent:
    """Agent that formulates a balanced, multi-lane research question from raw problem statements."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def formulate(
        self,
        raw_problem: str,
        model_provider: Optional[str] = None,
        llm_instance: Optional[Any] = None,
    ) -> FormulatedQuestion:
        """Formulate a structured Strategic Technology Question from user problem text."""
        clean_input = (raw_problem or "").strip()
        if not clean_input:
            clean_input = "Evaluating AI coding assistant adoption and developer productivity in enterprise delivery"

        # Try LLM formulation if instance or provider is available
        if llm_instance is not None or (model_provider and model_provider not in ("stub", "mock")):
            try:
                llm = llm_instance
                if llm is None and model_provider:
                    from src.llm.factory import build_llm
                    llm = build_llm(model_provider, self.config)

                if llm and hasattr(llm, "generate"):
                    prompt = self._build_prompt(clean_input)
                    response = llm.generate(prompt)
                    parsed = self._parse_llm_json(response)
                    if parsed:
                        return self._build_formulated_object(clean_input, parsed)
            except Exception as e:
                logger.warning("LLM question formulation failed, falling back to heuristic engine: %s", e)

        # Fallback to high-signal deterministic heuristic formulator
        return self._heuristic_formulate(clean_input)

    def _build_prompt(self, problem_text: str) -> str:
        return f"""You are a Principal AI Systems Researcher and Senior Engineering Delivery Leader.
Your task is to take a raw business/technical problem description and formulate a well-rounded, rigorous Strategic Technology Question suitable for academic literature, enterprise reports, and practitioner delivery notes.

Problem text from user:
\"\"\"{problem_text}\"\"\"

Output strictly a JSON object with this exact schema:
{{
  "strategic_question": "A balanced, formal strategic research question (single sentence ending in a question mark)",
  "suggested_id": "q-<short-hyphenated-slug-max-25-chars>",
  "scope": "enterprise" | "governance" | "productivity" | "security" | "architecture",
  "sub_questions": [
    "Sub-question 1 focusing on empirical productivity or technical mechanisms",
    "Sub-question 2 focusing on architectural trade-offs, drift, or compliance risks",
    "Sub-question 3 focusing on practical enterprise adoption and operational metrics"
  ],
  "target_entities": ["Primary technology or framework names mentioned or implied"],
  "time_window_months": 36,
  "rationale": "2-3 sentences explaining why this strategic framing resolves the user dilemma across academic and enterprise evidence.",
  "keywords": ["5", "search", "keywords", "for", "literature"]
}}
"""

    def _parse_llm_json(self, raw_output: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON object from LLM response text."""
        if not raw_output:
            return None
        text = raw_output.strip()
        # Handle markdown code blocks
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        elif "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}")
            text = text[start : end + 1]

        try:
            return json.loads(text)
        except Exception:
            return None

    def _build_formulated_object(self, raw_input: str, data: Dict[str, Any]) -> FormulatedQuestion:
        q_text = str(data.get("strategic_question") or "").strip()
        if not q_text.endswith("?"):
            q_text += "?"

        slug = str(data.get("suggested_id") or "q-strategic-eval").strip().lower()
        if not slug.startswith("q-"):
            slug = f"q-{slug}"
        slug = re.sub(r"[^a-z0-9\-]", "", slug)[:30].rstrip("-")

        scope = str(data.get("scope") or "enterprise").lower()
        if scope not in ("enterprise", "governance", "productivity", "security", "architecture"):
            scope = "enterprise"

        sub_qs = data.get("sub_questions") or []
        if not isinstance(sub_qs, list) or len(sub_qs) < 3:
            sub_qs = [
                "What empirical productivity and velocity gains are documented in controlled studies?",
                "What architectural risks, hallucinated patterns, or compliance boundaries must be governed?",
                "How do engineering teams measure real cycle time impact versus vanity metrics in production?",
            ]

        entities = data.get("target_entities") or ["AI Coding Assistants", "Enterprise Delivery"]
        if isinstance(entities, str):
            entities = [entities]

        keywords = data.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = []

        return FormulatedQuestion(
            raw_input=raw_input,
            strategic_question=q_text,
            suggested_id=slug,
            scope=scope,
            sub_questions=[str(q).strip() for q in sub_qs[:3]],
            target_entities=[str(e).strip() for e in entities],
            time_window_months=int(data.get("time_window_months") or 36),
            rationale=str(data.get("rationale") or "Formulated to ground the business dilemma in traceable empirical literature and enterprise practice."),
            keywords=[str(k).strip() for k in keywords],
        )

    def _heuristic_formulate(self, clean_input: str) -> FormulatedQuestion:
        """Deterministic heuristic fallback when LLM is unavailable or offline."""
        lower = clean_input.lower()

        # Detect primary entities
        entities = []
        if "kiro" in lower:
            entities.append("Amazon Kiro")
        if "copilot" in lower:
            entities.append("GitHub Copilot")
        if "cursor" in lower:
            entities.append("Cursor")
        if "agent" in lower or "swarm" in lower:
            entities.append("Autonomous AI Agents")
        if not entities:
            entities.append("AI Coding Assistants")

        # Detect scope & strategic angle
        if any(w in lower for w in ("security", "vulnerabilit", "cve", "licens", "copyright", "leak")):
            scope = "security"
            slug_stem = "security-gov"
            strategic_q = f"How do enterprise engineering teams mitigate security vulnerabilities, IP risks, and licensing compliance when deploying {entities[0]}?"
            sub_qs = [
                f"What empirical vulnerability rates and hallucinated dependencies occur with {entities[0]}?",
                "What static analysis and policy guardrails effectively prevent IP leakage in regulated sectors?",
                "How do DevSecOps workflows adapt to autonomous agent code generation without increasing MTTR?",
            ]
            keywords = [entities[0].lower(), "vulnerability mitigation", "ip compliance", "devsecops", "code generation security"]
            rationale = "Frames the inquiry around verifiable security boundaries, vulnerability incidence rates, and regulatory compliance protocols."

        elif any(w in lower for w in ("govern", "spec", "drift", "audit", "contract", "evaluat")):
            scope = "governance"
            slug_stem = "agent-spec-gov"
            strategic_q = f"What governance and specification-driven development frameworks ensure reliable production delivery with {entities[0]}?"
            sub_qs = [
                f"How do specification-driven architectures prevent silent drift in {entities[0]} implementations?",
                "What deterministic evaluation gates separate verifiable code generation from ungrounded completions?",
                "How do engineering organizations maintain architectural consistency across multi-repo autonomous pull requests?",
            ]
            keywords = [entities[0].lower(), "specification-driven development", "architectural drift", "verification gates", "agent governance"]
            rationale = "Emphasizes architectural contract enforcement, specification grounding, and deterministic verification to prevent silent technical debt."

        elif any(w in lower for w in ("cost", "rout", "roi", "productiv", "metric", "speed", "velocity")):
            scope = "productivity"
            slug_stem = "roi-productivity"
            strategic_q = f"What empirical evidence measures the true developer productivity, cycle time, and ROI impact of {entities[0]} in enterprise delivery?"
            sub_qs = [
                f"What controlled studies contrast net cycle time improvement against code churn and review overhead for {entities[0]}?",
                "How do engineering leaders separate genuine throughput gains from localized vanity metrics?",
                "What total-cost-of-ownership (TCO) models account for inference costs versus defect remediation in large enterprises?",
            ]
            keywords = [entities[0].lower(), "developer productivity", "cycle time metrics", "code churn", "empirical roi"]
            rationale = "Grounds developer velocity claims in peer-reviewed empirical studies, separating localized typing speed from systemic delivery throughput."

        elif any(w in lower for w in ("platform", "devex", "infra", "internal developer platform", "idp")):
            scope = "architecture"
            slug_stem = "platform-devex"
            strategic_q = f"How does platform engineering and internal developer platform (IDP) integration impact developer experience and delivery reliability with {entities[0]}?"
            sub_qs = [
                f"What measurable Developer Experience (DevEx) metrics improve when integrating {entities[0]} into golden paths?",
                "How do platform teams enforce self-service guardrails without degrading developer autonomy?",
                "What cognitive load reductions are verified in enterprise multi-vendor environments?",
            ]
            keywords = ["platform engineering", "internal developer platform", "developer experience devex", entities[0].lower(), "delivery reliability"]
            rationale = "Focuses on platform engineering golden paths, developer experience (DevEx) telemetry, and cognitive load reduction in complex delivery environments."

        else:
            scope = "enterprise"
            slug_stem = "enterprise-adoption"
            # Format title-case topic
            words = [w for w in re.findall(r"[a-zA-Z0-9]+", clean_input) if len(w) > 2]
            topic_summary = " ".join(words[:5]) if words else "AI Systems Adoption"
            strategic_q = f"What empirical evidence governs the adoption, productivity impact, and architectural trade-offs of {topic_summary} in enterprise software delivery?"
            sub_qs = [
                f"What empirical evidence verifies the real-world performance and adoption trade-offs of {topic_summary}?",
                "What architectural risks and quality trade-offs emerge when scaling beyond proof-of-concept implementations?",
                "What organizational governance frameworks separate sustainable velocity gains from unverified vendor claims?",
            ]
            keywords = [topic_summary.lower(), "enterprise software delivery", "empirical evaluation", "architectural trade-offs", "engineering governance"]
            rationale = "Constructs a balanced tripartite inquiry covering empirical validation, systemic architectural risks, and operational governance."

        # Unique slug
        clean_slug = re.sub(r"[^a-z0-9\-]", "", slug_stem)[:20].strip("-")
        suggested_id = f"q-{clean_slug}-{uuid.uuid4().hex[:4]}"

        return FormulatedQuestion(
            raw_input=clean_input,
            strategic_question=strategic_q,
            suggested_id=suggested_id,
            scope=scope,
            sub_questions=sub_qs,
            target_entities=entities,
            time_window_months=36,
            rationale=rationale,
            keywords=keywords,
        )

    def register_question_in_register(
        self,
        formulated: FormulatedQuestion,
        service: LedgerService,
        yaml_path: str = "questions/register.yaml",
        reviewer: str = "question_formulation_agent",
    ) -> Question:
        """Register formulated question into YAML register and SQLite ledger (Gate 1)."""
        # 1. Update YAML register
        Path(yaml_path).parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {"questions": []}
        if Path(yaml_path).exists():
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {"questions": []}

        existing_questions = data.get("questions", [])
        # Check if ID already exists
        found = False
        for item in existing_questions:
            if item.get("id") == formulated.suggested_id:
                item["text"] = formulated.strategic_question
                item["scope"] = formulated.scope
                item["time_window_months"] = formulated.time_window_months
                item["status"] = "active"
                found = True
                break

        if not found:
            existing_questions.append({
                "id": formulated.suggested_id,
                "text": formulated.strategic_question,
                "scope": formulated.scope,
                "time_window_months": formulated.time_window_months,
                "status": "active",
                "version": 1,
            })

        data["questions"] = existing_questions
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)

        # 2. Insert into SQLite ledger via service
        q_obj = service.create_question(
            question_id=formulated.suggested_id,
            text=formulated.strategic_question,
            scope=formulated.scope,
            time_window_months=formulated.time_window_months,
            reviewer=reviewer,
            reason=f"Formulated by QuestionFormulationAgent: {formulated.rationale[:80]}",
        )
        return q_obj
