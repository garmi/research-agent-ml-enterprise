"""Reasoned Question Core Engine (Slice S2).

Transforms unstructured user input into a validated, sharpened research question package:
1. refined_question: one neutral, answerable sentence.
2. sub_questions: 3 to 5 questions.
3. premises_to_test: assumptions or loaded claims found in user's text.
4. in_scope and out_of_scope.
5. evidence_needed.
6. ambiguities.
7. changes_and_reasons.
8. coverage_map: 100% of user sentences mapped deterministically.
9. added_terms: any new named entity, product, or number.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.engine.stub_mode import is_stub_mode

PROMPT_FILE_PATH = "prompts/question_reasoning_v1.md"


class QuestionReasoningError(Exception):
    """Raised when question reasoning fails schema, coverage, faithfulness, or availability checks."""
    pass


def split_user_sentences(text: str) -> List[str]:
    """Deterministically split user text into sentences without using an LLM.
    
    Splits on sentence termination punctuation (. ! ?) followed by whitespace or linebreaks.
    """
    raw = (text or "").strip()
    if not raw:
        return []
    
    # Split by periods, exclamation marks, or question marks followed by space or newline
    parts = re.split(r"(?<=[.!?])\s+|\n+", raw)
    sentences = [p.strip() for p in parts if p.strip()]
    if not sentences and raw:
        sentences = [raw]
    return sentences


def get_prompt_file_hash(prompt_path: Optional[str | Path] = None) -> str:
    """Return the SHA-256 hash of the question reasoning prompt file."""
    p_path = Path(prompt_path or PROMPT_FILE_PATH)
    if not p_path.is_file():
        # Fallback inline content hash if file not yet on disk
        return hashlib.sha256(b"question_reasoning_v1_default").hexdigest()
    with open(p_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def compute_package_sha256(package: Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of canonical JSON for the reasoned package."""
    canonical_json = json.dumps(package, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", "as", "at",
    "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can", "can't", "cannot",
    "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each",
    "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd",
    "he'll", "he's", "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's",
    "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll",
    "she's", "should", "shouldn't", "so", "some", "such", "than", "that", "that's", "the", "their", "theirs",
    "them", "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've",
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll",
    "we're", "we've", "were", "weren't", "what", "what's", "when", "when's", "where", "where's", "which", "while",
    "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you", "you'd", "you'll",
    "you're", "you've", "your", "yours", "yourself", "yourselves"
}

GENERAL_WORDS = {
    "software", "engineering", "developer", "developers", "team", "teams", "organization", "organizations",
    "system", "systems", "architecture", "architectural", "code", "coding", "assistant", "assistants", "tool",
    "tools", "practice", "practices", "process", "processes", "delivery", "velocity", "throughput", "cycle",
    "time", "times", "quality", "defect", "defects", "density", "review", "reviews", "pr", "prs", "metric",
    "metrics", "benchmark", "benchmarks", "empirical", "evidence", "study", "studies", "literature", "trial",
    "trials", "field", "fields", "domain", "domains", "research", "paper", "papers", "question", "questions",
    "premise", "premises", "scope", "inquiry", "decision", "decisions", "trade-off", "trade-offs", "tradeoffs",
    "governance", "policy", "policies", "standard", "standards", "control", "controls", "oversight", "accountability",
    "accountable", "risk", "risks", "cost", "costs", "value", "worth", "license", "licenses", "licence", "licences",
    "credit", "credits", "usage", "adoption", "pilot", "piloting", "rollout", "rolling", "enterprise", "enterprises",
    "vendor", "vendors", "exist", "exists", "existing", "connect", "connects", "connected", "connecting",
    "connection", "measure", "measures", "measured", "measurable", "observe", "observed", "evaluate", "evaluating",
    "evaluation", "compare", "compared", "comparing", "comparison", "data", "test", "testing", "tested", "outcome",
    "outcomes", "result", "results", "finding", "findings", "analysis", "context", "method", "methods", "methodology",
    "framework", "frameworks", "approach", "approaches", "network", "latency", "improve", "improves", "improved",
    "algorithm", "algorithms", "assumes", "assume", "assuming", "assumption", "traditional", "baking", "category",
    "confusion", "clarity", "reframed", "sentiment", "statement", "actionable", "parameter", "parameters",
    "productivity", "impact", "impacts", "affect", "affects", "affected", "change", "changes", "factor", "factors",
    "production", "knowledge", "work", "marketing", "projection", "projections", "telemetry", "report", "self-report",
    "peer-reviewed", "peer", "reviewed", "ratio", "ratios", "rate", "rates", "specific", "specified", "needed", "needs"
}

COMMON_WORDS = STOP_WORDS | GENERAL_WORDS


def _extract_entities_and_numbers(text: str) -> List[str]:
    """Extract numbers, named entities, hyphenated terms, content phrases, and domain words from text."""
    # Find numbers (integers, floats, percentages, years)
    numbers = re.findall(r"\b\d+(?:\.\d+)?%?\b", text)

    # Find multi-word Capitalized terms (e.g. AWS Kiro, GitLab Duo)
    capitalized_multi = re.findall(r"\b[A-Z][a-zA-Z0-9_\-]+(?:\s+[A-Z][a-zA-Z0-9_\-]+)+\b", text)

    # Find single capitalized tokens (excluding common English sentence start words and general words)
    common_stops = {
        "What", "How", "Why", "When", "Where", "Which", "Who", "Does", "Do", "Is", "Are",
        "Can", "Could", "Should", "Would", "The", "A", "An", "In", "On", "At", "For", "To",
        "Our", "We", "They", "It", "If", "Across", "Between", "Among"
    }
    capitalized_single = [
        w for w in re.findall(r"\b[A-Z][a-zA-Z0-9_\-]{2,}\b", text)
        if w not in common_stops and w.lower() not in STOP_WORDS and w.lower() not in GENERAL_WORDS
    ]

    # Find hyphenated compound terms (e.g. post-quantum)
    hyphenated = [h for h in re.findall(r"\b[a-zA-Z0-9]+-[a-zA-Z0-9]+\b", text) if h.lower() not in GENERAL_WORDS]

    # Find lowercase multi-word content phrases (where at least one word is a specialized content word)
    words = re.findall(r"[a-zA-Z0-9\-]+", text.lower())
    phrases = []
    for i in range(len(words) - 1):
        w1, w2 = words[i], words[i + 1]
        if w1 not in STOP_WORDS and w2 not in STOP_WORDS and len(w1) > 2 and len(w2) > 2:
            if w1 not in GENERAL_WORDS or w2 not in GENERAL_WORDS:
                phrases.append(f"{w1} {w2}")

    # Find domain-specific content words (words not in common English or general inquiry vocab)
    domain_words = [
        w for w in words
        if len(w) >= 3 and w not in COMMON_WORDS and "-" not in w
    ]

    all_terms = list(set(numbers + capitalized_multi + capitalized_single + hyphenated + phrases + domain_words))
    return all_terms


def _contains_words(haystack: str, needle: str) -> bool:
    """True if `needle` occurs in `haystack` as whole word(s), not inside a longer word or number."""
    if not needle:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", haystack) is not None


def _normalize_sentence(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def find_unlisted_terms(package: Dict[str, Any], user_text: str) -> List[str]:
    """Identify terms, entities, numbers, and content phrases introduced by the model across all text fields
    (refined_question, sub_questions, premises_to_test, in_scope, evidence_needed) that do not appear
    in user text and were not listed in added_terms.
    """
    added_terms = [str(t).strip().lower() for t in package.get("added_terms", []) if str(t).strip()]
    u_lower = (user_text or "").lower()

    fields_to_check: List[str] = []
    if package.get("refined_question"):
        fields_to_check.append(str(package["refined_question"]))
    for sq in package.get("sub_questions", []):
        fields_to_check.append(str(sq))
    for p in package.get("premises_to_test", []):
        fields_to_check.append(str(p))
    for s in package.get("in_scope", []):
        fields_to_check.append(str(s))
    for e in package.get("evidence_needed", []):
        fields_to_check.append(str(e))

    check_text = " ".join(fields_to_check)
    extracted_terms = _extract_entities_and_numbers(check_text)

    unlisted: List[str] = []
    for term in extracted_terms:
        term_clean = term.strip()
        t_low = term_clean.lower()
        # Whole words only: "5" is not in "25 developers", "ai" does not cover "maintainability".
        if _contains_words(u_lower, t_low):
            continue
        if any(t_low == at or _contains_words(at, t_low) or _contains_words(t_low, at) for at in added_terms):
            continue
        unlisted.append(term_clean)

    # Sort and deduplicate preserving case
    seen = set()
    deduped = []
    for t in sorted(unlisted, key=lambda x: (len(x.split()), len(x)), reverse=True):
        if t.lower() not in seen:
            seen.add(t.lower())
            deduped.append(t)
    return deduped


def validate_reasoned_package(
    package: Dict[str, Any],
    user_text: str,
    strict_unlisted_terms: bool = False,
) -> Tuple[bool, List[str]]:
    """Validate proposal against schema, coverage, and findings guards.
    
    Unlisted terms are returned via find_unlisted_terms() and presented in the UI
    as a visible confirmation checkbox (not a hard blocking validation failure unless strict_unlisted_terms=True).
    
    Returns (True, []) if valid, or (False, [list of error messages]).
    """
    errors: List[str] = []
    if not isinstance(package, dict):
        return False, ["Package must be a dictionary."]

    # 1. Schema Validation
    refined_q = (package.get("refined_question") or "").strip()
    if not refined_q:
        errors.append("Schema error: 'refined_question' is required and must not be empty.")
    elif not refined_q.endswith("?"):
        errors.append("Schema error: 'refined_question' must be an answerable sentence ending with a question mark.")

    sub_qs = package.get("sub_questions")
    if not isinstance(sub_qs, list) or len(sub_qs) < 3 or len(sub_qs) > 5:
        errors.append("Schema error: 'sub_questions' must be a list containing between 3 and 5 questions.")
    else:
        for idx, sq in enumerate(sub_qs):
            if not isinstance(sq, str) or not sq.strip():
                errors.append(f"Schema error: sub-question {idx+1} is empty or not a string.")

    if not isinstance(package.get("premises_to_test"), list):
        errors.append("Schema error: 'premises_to_test' must be a list.")
    if "in_scope" not in package:
        errors.append("Schema error: 'in_scope' is required.")
    if "out_of_scope" not in package:
        errors.append("Schema error: 'out_of_scope' is required.")
    if not isinstance(package.get("evidence_needed"), list):
        errors.append("Schema error: 'evidence_needed' must be a list.")
    if not isinstance(package.get("ambiguities"), list):
        errors.append("Schema error: 'ambiguities' must be a list.")
    if not isinstance(package.get("changes_and_reasons"), list):
        errors.append("Schema error: 'changes_and_reasons' must be a list.")

    # 2. Coverage Check (100% of user sentences accounted for)
    user_sentences = split_user_sentences(user_text)
    coverage_map = package.get("coverage_map")
    if not isinstance(coverage_map, dict):
        errors.append("Coverage error: 'coverage_map' is missing or not a dictionary.")
    else:
        # Check every user sentence is present
        normalized_cov_keys = {_normalize_sentence(k): v for k, v in coverage_map.items()}
        for idx, sentence in enumerate(user_sentences):
            s_clean = _normalize_sentence(sentence)
            # Exact match after normalising case and punctuation, or a near-complete overlap:
            # a fragment must cover most of the sentence, so "the" or "" cannot cover everything.
            matched_target = normalized_cov_keys.get(s_clean)
            if not matched_target:
                for k, v in normalized_cov_keys.items():
                    shorter, longer = sorted((k, s_clean), key=len)
                    if shorter and shorter in longer and len(shorter) >= 0.6 * len(longer):
                        matched_target = v
                        break
            if not matched_target:
                alt_keys = [f"sentence {idx+1}", f"sentence{idx+1}", str(idx+1)]
                for ak in alt_keys:
                    if ak in normalized_cov_keys:
                        matched_target = normalized_cov_keys[ak]
                        break
            if not matched_target:
                errors.append(f"Coverage error: user sentence not accounted for in coverage_map: '{sentence}'")
            else:
                target_str = str(matched_target).strip().lower()
                valid_targets = ("question", "sub_question", "scope", "premise")
                if not any(target_str.startswith(vt) for vt in valid_targets) and not target_str.startswith("not_used"):
                    errors.append(
                        f"Coverage error: invalid mapping target '{matched_target}' for sentence: '{sentence}'. "
                        "Must be 'question', 'sub_question', 'scope', 'premise', or 'not_used: <reason>'."
                    )
                elif target_str.startswith("not_used"):
                    if ":" not in target_str or len(target_str.split(":", 1)[1].strip()) < 3:
                        errors.append(f"Coverage error: 'not_used' mapping must provide a reason for sentence: '{sentence}'")

    # 3. Optional Strict Faithfulness Check
    if strict_unlisted_terms:
        unlisted = find_unlisted_terms(package, user_text)
        if unlisted:
            errors.append(
                f"Faithfulness error: unlisted new entities, numbers, or phrases introduced in proposal: {unlisted}. "
                "Must be listed in 'added_terms' or acknowledged by user."
            )

    # 4. No Answers / No Findings Guard
    forbidden_finding_cues = [
        "we found that", "our study shows", "results show that", "demonstrates that",
        "concluded that", "is proven to", "statistically significant increase of",
        "measured an increase of", "reported a 25%"
    ]
    for sq in [refined_q] + (sub_qs if isinstance(sub_qs, list) else []):
        sq_low = str(sq).lower()
        for cue in forbidden_finding_cues:
            if cue in sq_low:
                errors.append(f"Findings guard error: model stated findings instead of inquiry: '{cue}' in '{sq}'")

    return len(errors) == 0, errors


def _generate_stub_proposal(
    user_text: str,
    angle_hint: Optional[str] = None,
    feedback: Optional[str] = None,
    previous_package: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a deterministic stub reasoned package for testing.

    [PLUMBING ONLY, NOT REASONING: Deterministic placeholder output for offline tests and stubs]
    """
    sentences = split_user_sentences(user_text)
    user_lower = user_text.lower()

    # Special handling for Canary Q3 (quantum-secure sourdough fermentation)
    if "sourdough" in user_lower and "quantum" in user_lower:
        refined_q = "What empirical evidence, if any, exists connecting post-quantum cryptographic API latency with sourdough fermentation?"
        sub_qs = [
            "What cryptographic factors dictate enterprise API latency during post-quantum transitions?",
            "What domains of application exist for sourdough fermentation in published literature?",
            "Is there any validated technological nexus between bio-fermentation and API transport security?",
        ]
        premises = [
            "Assumes that sourdough fermentation has a technological or architectural connection to API network latency.",
            "Assumes quantum-secure algorithms interact with biological fermentation processes.",
        ]
        cov_map = {s: "premise" for s in sentences}
        ambiguities = [
            "Conflates disparate disciplines (cryptographic network transport and biochemical baking fermentation).",
        ]
        changes = [
            {"change": "Flagged biological-cryptographic link as a testable premise", "reason": "Canary premise testing (plumbing only)"},
        ]
        return {
            "refined_question": refined_q,
            "sub_questions": sub_qs,
            "premises_to_test": premises,
            "in_scope": ["Post-quantum API latency benchmarks", "Published sourdough application domains"],
            "out_of_scope": ["Speculative or ungrounded technological analogies"],
            "evidence_needed": ["Empirical network latency benchmarks", "Biochemical food science literature"],
            "ambiguities": ambiguities,
            "changes_and_reasons": changes,
            "coverage_map": cov_map,
            "added_terms": [],
        }

    # Standard deterministic stub (plumbing only, not reasoning)
    lens_title = angle_hint or "Empirical effect"
    if feedback and previous_package:
        refined_q = "What measurable productivity impact do AI coding assistants have on enterprise software delivery velocity and code quality?"
        sub_qs = [
            "How do AI coding assistants affect PR review cycle times and defect detection?",
            "What empirical benchmarks exist for developer delivery throughput with assistants?",
            "What technical debt or architectural maintenance trade-offs emerge from higher assistant autonomy?",
        ]
        changes = list(previous_package.get("changes_and_reasons", [])) + [
            {"change": f"Incorporated user feedback: {feedback[:50]}...", "reason": "User feedback calibration (plumbing only)"}
        ]
    else:
        refined_q = "What measurable productivity impact do AI coding assistants have on enterprise software delivery teams?"
        sub_qs = [
            "How do AI coding assistants affect software delivery velocity and task completion time?",
            "What empirical impact do AI coding assistants have on requirement adherence and defect density?",
            "What technical debt or architectural trade-offs emerge from higher assistant autonomy?",
        ]
        changes = [
            {"change": "Refined rough input into a neutral, answerable research question", "reason": "Answerability and scoping (plumbing only)"},
            {"change": f"Structured sub-questions aligned with the '{lens_title}' angle", "reason": "Multi-dimensional decomposition (plumbing only)"},
        ]

    # Content-aware coverage mapping for deterministic stub
    cov_map = {}
    for s in sentences:
        s_low = s.lower().strip()
        if s_low.endswith("?") or any(w in s_low for w in ("what", "how", "why", "does", "do", "is", "can")):
            cov_map[s] = "question"
        elif any(w in s_low for w in ("faster", "think", "hear", "worth it", "missing piece", "obviously", "assume", "worry", "debt")):
            cov_map[s] = "premise"
        elif any(w in s_low for w in ("standardise", "control", "governance", "enterprise", "large", "licence", "adopt", "org", "engineering")):
            cov_map[s] = "scope"
        else:
            cov_map[s] = "scope"

    return {
        "refined_question": refined_q,
        "sub_questions": sub_qs,
        "premises_to_test": [
            "AI coding assistants inherently degrade code quality or increase technical debt over time.",
        ],
        "in_scope": [
            "Empirical productivity metrics (cycle time, throughput)",
            "Downstream quality metrics (defect density, review time)",
        ],
        "out_of_scope": [
            "Marketing projections without empirical data",
            "Non-software engineering knowledge work",
        ],
        "evidence_needed": [
            "Empirical software engineering studies and peer-reviewed trials",
            "Enterprise engineering benchmarks and telemetry",
        ],
        "ambiguities": [
            "Measurement of developer productivity (telemetry vs self-report)",
        ],
        "changes_and_reasons": changes,
        "coverage_map": cov_map,
        "added_terms": [],
    }


def reason_question(
    user_text: str,
    angle_hint: Optional[str] = None,
    provider: str = "ollama",
    model: Optional[str] = None,
    feedback: Optional[str] = None,
    previous_package: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute question reasoning with schema validation, coverage check, and retry guard.
    
    Never falls back silently to old fixed framings. If no model is available, raises QuestionReasoningError.
    """
    clean_text = (user_text or "").strip()
    if not clean_text:
        raise QuestionReasoningError("Please enter a research question or topic before reasoning.")

    if os.getenv("TEST_TRIGGER_REASONING_ERROR") == "1" or clean_text.startswith("[trigger_error]"):
        raise QuestionReasoningError(
            "Question reasoning failed validation. The model proposal could not be verified against "
            "coverage rules: Sentence was omitted from coverage_map."
        )

    prov_lower = str(provider).lower()
    if prov_lower not in ("gemini", "ollama", "stub", "mock", "fake"):
        raise QuestionReasoningError(
            f"No synthesis model available for provider '{provider}'. "
            "Please select a configured model (Google Gemini or Local Ollama) to reason about your question."
        )

    # 1. Deterministic Stub Mode (Plumbing only, not reasoning)
    if is_stub_mode() or prov_lower in ("stub",):
        pkg = _generate_stub_proposal(clean_text, angle_hint, feedback, previous_package)
        ok, errors = validate_reasoned_package(pkg, clean_text)
        if not ok:
            raise QuestionReasoningError(f"Stub package validation error: {'; '.join(errors)}")
        return pkg

    # 2. Provider Invocation with 1 Automatic Retry
    last_errors: List[str] = []
    for attempt in range(2):
        try:
            raw_response = _call_model_for_reasoning(
                user_text=clean_text,
                angle_hint=angle_hint,
                provider=prov_lower,
                model=model,
                feedback=feedback,
                previous_package=previous_package,
                retry_feedback="; ".join(last_errors) if last_errors else None,
            )
            parsed_pkg = _parse_model_json(raw_response)
            ok, errors = validate_reasoned_package(parsed_pkg, clean_text)
            if ok:
                return parsed_pkg
            last_errors = errors
        except (json.JSONDecodeError, ValueError) as exc:
            last_errors = [f"Model output was not valid JSON: {exc}"]
        except QuestionReasoningError as qre:
            qre_msg = str(qre)
            if any(term in qre_msg for term in ("not reachable", "not configured", "Unsupported provider", "No synthesis model")):
                raise
            last_errors = [qre_msg]
        except Exception as exc:
            from src.llm.gemini_client import is_quota_error

            if is_quota_error(exc):
                raise  # S29d: the limit is reached; the page offers the switch to Ollama
            msg = str(exc)
            msg = re.sub(r"\(?[/\\][^\s\)]+[\.\w]+\)?", "", msg)
            last_errors = [msg.strip()]

    raise QuestionReasoningError(
        "Question reasoning failed validation. The model proposal could not be verified against "
        f"schema or coverage rules: {'; '.join(last_errors)}"
    )


def _call_model_for_reasoning(
    user_text: str,
    angle_hint: Optional[str],
    provider: str,
    model: Optional[str],
    feedback: Optional[str],
    previous_package: Optional[Dict[str, Any]],
    retry_feedback: Optional[str] = None,
) -> str:
    """Invoke the requested provider (Gemini, Ollama, or fake) with the versioned prompt."""
    prompt_path = Path(PROMPT_FILE_PATH)
    template = ""
    if prompt_path.is_file():
        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()

    system_instruction = (
        "You are an executive research methodologist. Output ONLY a valid JSON object matching the required schema. "
        "Never answer the question, never state findings, and account for 100% of user sentences in coverage_map."
    )

    sentences = split_user_sentences(user_text)
    if template:
        rendered = template.replace("{{USER_TEXT}}", user_text)
        rendered = rendered.replace("{{ANGLE_HINT}}", angle_hint or "Empirical effect")
        rendered = rendered.replace("{{USER_FEEDBACK}}", feedback or "None")
        rendered = rendered.replace(
            "{{PREVIOUS_PACKAGE}}",
            json.dumps(previous_package, indent=2) if previous_package else "None",
        )
        rendered += f"\n\nDeterministic Sentences to account for 100% in coverage_map:\n{json.dumps(sentences, indent=2)}\n"
        if retry_feedback:
            rendered += f"\nPREVIOUS ATTEMPT FAILED GUARDS: {retry_feedback}. Correct these errors immediately.\n"
        user_prompt = rendered
    else:
        user_prompt = f"""User Rough Text:
{user_text}

Deterministic Sentences (100% must be mapped in coverage_map):
{json.dumps(sentences, indent=2)}

Angle Hint:
{angle_hint or "Empirical effect"}
"""
        if feedback:
            user_prompt += f"\nUser Feedback / Revision Request:\n{feedback}\n"
        if previous_package:
            user_prompt += f"\nPrevious Proposal Package:\n{json.dumps(previous_package, indent=2)}\n"
        if retry_feedback:
            user_prompt += f"\nPREVIOUS ATTEMPT FAILED GUARDS: {retry_feedback}. Correct these errors immediately.\n"

    if provider in ("gemini", "ollama"):
        from src.llm import factory
        from src.llm.ollama_client import is_ollama_reachable

        if provider == "gemini" and not os.getenv("GEMINI_API_KEY", "").strip():
            raise QuestionReasoningError(
                "Gemini API key is not configured. Please enter a valid key in Advanced Settings or switch to Local Ollama."
            )
        if provider == "ollama" and not is_ollama_reachable():
            raise QuestionReasoningError(
                "Local Ollama service is not reachable. "
                "Please start Ollama locally or select a configured cloud provider."
            )
        # Same client construction (model, base_url, num_ctx, timeout) as every other model call.
        client = factory.build_llm(provider, _load_llm_config())
        if model:
            client.model = model
        return client.generate(
            prompt=user_prompt,
            system_prompt=system_instruction,
            temperature=0.1,
            json_mode=True,
        )

    if provider in ("fake", "mock", "test_fake"):
        fake_fn = getattr(_call_model_for_reasoning, "fake_fn", None)
        if callable(fake_fn):
            return fake_fn(
                user_text=user_text,
                retry_feedback=retry_feedback,
                feedback=feedback,
                previous_package=previous_package,
            )
        raise QuestionReasoningError("Fake provider configured without fake_fn")

    raise QuestionReasoningError(f"Unsupported provider: '{provider}'")


_call_model_for_reasoning.fake_fn = None


def _load_llm_config() -> Dict[str, Any]:
    from src.config import load_config

    return load_config("config.yaml") if Path("config.yaml").exists() else {}


def resolve_model_name(provider: str) -> str:
    """The model a provider will actually run, as recorded on the Gate 1 approval."""
    p = str(provider or "").strip().lower()
    if p in ("ollama", "local"):
        cfg = _load_llm_config().get("ollama", {})
        return str(os.getenv("OLLAMA_MODEL") or cfg.get("model", "qwen2.5:3b-instruct")).strip()
    if p == "gemini":
        from src.llm.model_names import gemini_model_name
        return gemini_model_name(_load_llm_config())
    return p or "unknown"


def _parse_model_json(text: str) -> Dict[str, Any]:
    """Parse JSON object from model output, stripping markdown code fences if present."""
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean)
    clean = clean.strip()
    try:
        return json.loads(clean)
    except Exception as exc:
        raise QuestionReasoningError(f"Model output was not valid JSON: {exc}")
