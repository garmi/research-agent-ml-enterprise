"""Test A4: Traceable citations and support checks.

Verifies:
1. Planted D1 defect (healthcare paper cited for software engineering metric 32%)
   FAILS with reason "Source topic mismatch", "Ungrounded numeral", or "Insufficient excerpt overlap".
2. Document status is BLOCKED.
3. Valid software citations matching numerals and sharing substantive terms PASS.
"""

from pathlib import Path
import tempfile
import pytest

from src.ledger.models import Claim, OutputDoc, OutputSentence, Question, Source
from src.score.checker import GateChecker


def test_d1_defect_blocked_source_topic_mismatch_and_ungrounded_numeral():
    """Plant the exact D1 defect and prove it is caught and BLOCKED."""
    checker = GateChecker()

    # Software engineering question
    question = Question(
        id="q-soft-01",
        text="How do automated verification gates affect software defects?",
        scope="architecture",
    )

    # Healthcare policy paper (D1 defect source)
    healthcare_source = Source(
        id="src-health-01",
        lane="academic",
        source_type="peer_reviewed",
        title="The EU AI Act: implications and compliance guidance for healthcare facilities",
        url="https://doi.org/10.1000/health-policy",
        venue="Health Policy and Clinical Law Journal",
    )

    # Healthcare claim without any software velocity metric
    healthcare_claim = Claim(
        id="c-health-01",
        question_id=question.id,
        source_id=healthcare_source.id,
        text="Hospital clinical triage algorithms must maintain compliance documentation.",
        source_excerpt="Hospitals must perform risk assessments for medical devices under EU standards.",
        grade="moderate",
        entity="Hospital Triage System",
        entity_match="topic_level",
        value_json={"compliance_rate": "required"},
    )

    # Planted D1 sentence: cites healthcare claim for software velocity metric 32%
    bad_sentence = OutputSentence(
        id="out-01_1",
        output_id="out-01",
        ordinal=1,
        text="Empirical velocity increases by 32% across standard delivery tasks.",
        type="assertive",
        claim_ids_json=[healthcare_claim.id],
    )

    ledger_claims = {healthcare_claim.id: healthcare_claim}
    sources = {healthcare_source.id: healthcare_source}
    source_texts = {healthcare_source.id: f"{healthcare_source.title} {healthcare_source.venue}"}

    result = checker.check_output(
        sentences=[bad_sentence],
        ledger_claims=ledger_claims,
        source_texts=source_texts,
        sources=sources,
        question=question,
    )

    # Must FAIL
    assert result.passed is False, "Planted D1 defect must fail gate check!"

    # Must report Source topic mismatch, Ungrounded numeral, or Insufficient excerpt overlap
    all_violations = []
    for g_list in result.violations.values():
        all_violations.extend(g_list)
    violations_text = " ".join(all_violations)

    assert (
        "Source topic mismatch" in violations_text
        or "Ungrounded numeral" in violations_text
        or "Insufficient excerpt overlap" in violations_text
    ), f"Expected explicit support check failure reasons, got: {violations_text}"


def test_valid_citation_matching_numeral_and_topic_passes():
    """Verify that a valid software engineering citation with grounded numerals and overlap passes."""
    checker = GateChecker()

    question = Question(
        id="q-soft-02",
        text="How do automated verification gates affect software defects?",
        scope="architecture",
    )

    valid_source = Source(
        id="src-soft-01",
        lane="academic",
        source_type="peer_reviewed",
        title="Automated Verification Gates in Continuous Delivery: An Empirical Study on Software Defects",
        url="https://doi.org/10.1145/icse.2024.12",
        venue="ACM/IEEE ICSE",
    )

    valid_claim = Claim(
        id="c-soft-01",
        question_id=question.id,
        source_id=valid_source.id,
        text="Automated verification gates reduce software defects by 30% in deployment pipelines.",
        source_excerpt="Our empirical study shows automated verification gates reduce software defects by 30% across repositories.",
        grade="strong",
        entity="Automated Verification Gates",
        entity_match="exact",
        value_json={"defect_reduction": "30%"},
    )

    valid_sentence = OutputSentence(
        id="out-02_1",
        output_id="out-02",
        ordinal=1,
        text="Empirical studies demonstrate that automated verification gates reduce software defects by 30%.",
        type="assertive",
        claim_ids_json=[valid_claim.id],
    )

    ledger_claims = {valid_claim.id: valid_claim}
    sources = {valid_source.id: valid_source}
    source_texts = {valid_source.id: f"{valid_source.title} {valid_source.venue}"}

    result = checker.check_output(
        sentences=[valid_sentence],
        ledger_claims=ledger_claims,
        source_texts=source_texts,
        sources=sources,
        question=question,
    )

    assert result.passed is True, f"Valid citation must pass, got violations: {result.violations}"
