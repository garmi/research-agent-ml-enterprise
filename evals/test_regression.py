"""Regression and Adversarial Test Suite for Research Engine v2 (R1 to R7).

Tests planted failure modes and verifies gate enforcement:
- R1: Kiro misattribution (general AI assistant claim used for Kiro) -> G3 fail
- R2: Fabricated figure not in ledger (e.g. 67%, 20x) -> G2 fail
- R3: Vendor claim written as proven fact -> G4 fail
- R4: Source from unverified venue -> grade capped at weak
- R5: Denylist confidential client/person name in text -> G5 fail
- R6: Long verbatim copy (>= 8 words outside quotes) -> G6 fail
- R7: Uncited assertive sentence -> G1 fail
"""

import os
import tempfile
import pytest

from src.grade.grader import Grader
from src.ledger.models import Claim, OutputSentence, Source
from src.score.checker import GateChecker


@pytest.fixture
def test_env():
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create test denylist
        denylist_path = os.path.join(tmp_dir, "denylist.txt")
        with open(denylist_path, "w", encoding="utf-8") as f:
            f.write("Acme Corp\nProject Titan\nJane Doe\n")

        checker = GateChecker(
            verbs_path="synth/strength_verbs.yaml",
            denylist_path=denylist_path,
        )
        grader = Grader(
            rules_path="grade/rules.yaml",
            venue_tiers_path="grade/venue_tiers.yaml",
        )
        yield checker, grader


def test_r1_kiro_misattribution(test_env):
    """R1: A 2023 general assistant claim cited in a Kiro-specific sentence must fail G3."""
    checker, _ = test_env

    # Paper 4 claim: general AI assistants (topic_level), not Kiro
    claim = Claim(
        id="c_wjarr_1",
        source_id="src_wjarr_2023",
        text="AI assistants can enhance developer productivity by 25-35%.",
        source_excerpt="AI can enhance developer productivity by 25-35% in routine coding.",
        value_json={"value": "25-35%", "unit": "%"},
        entity="AI Coding Assistants",
        entity_match="topic_level",  # NOT exact
        study_type="survey_with_method",
        grade="weak",
    )

    sentence = OutputSentence(
        id="s1",
        output_id="out1",
        ordinal=1,
        text="Amazon Kiro enhances developer productivity by 25-35% across engineering teams.",
        type="assertive",
        claim_ids_json=["c_wjarr_1"],
    )

    result = checker.check_output([sentence], {"c_wjarr_1": claim})
    assert not result.g3_pass, "Expected G3 Entity Fidelity failure when citing general paper for Kiro"
    assert not result.passed
    assert any("Kiro" in v for v in result.violations["G3"])


def test_r2_fabricated_figure(test_env):
    """R2: Fabricated figures (e.g. 67%, 20x) not grounded in ledger claims must fail G2."""
    checker, _ = test_env

    claim = Claim(
        id="c_valid_1",
        source_id="src_paper_1",
        text="The study noted minor improvements in routine software generation.",
        source_excerpt="The study noted minor improvements in routine tasks.",
        entity_match="exact",
        grade="moderate",
    )

    sentence = OutputSentence(
        id="s2",
        output_id="out1",
        ordinal=1,
        text="Deploying the framework achieved a 67% reduction in bugs and 20x speedup.",
        type="assertive",
        claim_ids_json=["c_valid_1"],
    )

    result = checker.check_output([sentence], {"c_valid_1": claim})
    assert not result.g2_pass, "Expected G2 Numeric Fidelity failure for fabricated numbers 67% and 20x"
    assert not result.passed
    assert any("67%" in v for v in result.violations["G2"])


def test_r3_vendor_claim_written_as_fact(test_env):
    """R3: A vendor claim expressed with strong fact verbs (e.g. 'demonstrates') must fail G4."""
    checker, _ = test_env

    claim = Claim(
        id="c_vendor_1",
        source_id="src_aws_blog",
        text="The tool automatically optimizes code generation across cloud repositories.",
        source_excerpt="The tool optimizes generation across repositories.",
        entity_match="exact",
        grade="vendor_claim",  # max allowed verb rank is 2 ("states", "claims")
    )

    sentence = OutputSentence(
        id="s3",
        output_id="out1",
        ordinal=1,
        text="Enterprise deployment demonstrates that the assistant eliminates manual integration.",
        type="assertive",
        claim_ids_json=["c_vendor_1"],
    )

    result = checker.check_output([sentence], {"c_vendor_1": claim})
    assert not result.g4_pass, "Expected G4 Language Honesty failure when using 'demonstrates' for vendor_claim"
    assert not result.passed
    assert any("demonstrates" in v for v in result.violations["G4"])


def test_r4_unverified_venue_cap(test_env):
    """R4: An empirical study published in an unverified venue must be capped at weak."""
    _, grader = test_env

    source = Source(
        id="src_wjarr_paper",
        lane="academic",
        source_type="peer_reviewed",
        title="Developer productivity in AI-driven engineering teams",
        venue="World Journal of Advanced Research and Reviews (WJARR)",
        venue_tier="unverified",
        extraction_depth="abstract_only",
    )

    claim = Claim(
        id="c_wjarr_emp",
        source_id="src_wjarr_paper",
        text="Developer productivity improved in controlled sample groups.",
        source_excerpt="Productivity improved in controlled sample groups.",
        study_type="controlled_study",  # Empirical study type
        entity_match="exact",
    )

    grade, reasons = grader.grade_claim(claim, source)
    assert grade == "weak", f"Expected unverified venue to cap grade at 'weak', got '{grade}'"
    assert any("CAP APPLIED: Unverified venue" in r for r in reasons)


def test_r5_denylist_confidential_name(test_env):
    """R5: Mentioning a confidential client or programme on the denylist must fail G5."""
    checker, _ = test_env

    claim = Claim(
        id="c_general_1",
        source_id="src_p1",
        text="General observations from software delivery pilots.",
        source_excerpt="Observations from software delivery pilots.",
        grade="moderate",
    )

    sentence = OutputSentence(
        id="s5",
        output_id="out1",
        ordinal=1,
        text="During the pilot at Acme Corp, delivery cycle times contracted.",
        type="assertive",
        claim_ids_json=["c_general_1"],
    )

    result = checker.check_output([sentence], {"c_general_1": claim})
    assert not result.g5_pass, "Expected G5 Confidentiality failure for denylist term 'Acme Corp'"
    assert not result.passed
    assert any("acme corp" in v for v in result.violations["G5"])


def test_r6_long_verbatim_copy(test_env):
    """R6: A verbatim run of 8+ consecutive words outside marked quotes must fail G6."""
    checker, _ = test_env

    full_source_text = (
        "Enterprise software teams report a frustrating inconsistency where "
        "the same AI coding assistants producing compelling results in controlled studies "
        "return uneven outcomes in production environments."
    )

    claim = Claim(
        id="c_src_1",
        source_id="src_full_1",
        text="Production outcomes for coding assistants remain uneven.",
        source_excerpt="Compelling results in controlled studies return uneven outcomes.",
        grade="moderate",
    )

    # Contains 10 consecutive verbatim words from source without quotes
    sentence = OutputSentence(
        id="s6",
        output_id="out1",
        ordinal=1,
        text="We observe that the same AI coding assistants producing compelling results in controlled studies show variation.",
        type="assertive",
        claim_ids_json=["c_src_1"],
    )

    result = checker.check_output(
        sentences=[sentence],
        ledger_claims={"c_src_1": claim},
        source_texts={"src_full_1": full_source_text},
    )
    assert not result.g6_pass, "Expected G6 Copyright failure for verbatim run >= 8 words outside quotes"
    assert not result.passed
    assert any("Verbatim run" in v for v in result.violations["G6"])


def test_r7_uncited_assertive_sentence(test_env):
    """R7: An assertive sentence without claim citation must fail G1."""
    checker, _ = test_env

    sentence = OutputSentence(
        id="s7",
        output_id="out1",
        ordinal=1,
        text="AI coding assistants inevitably cause cognitive fatigue across large delivery teams.",
        type="assertive",
        claim_ids_json=[],  # Uncited assertive sentence
    )

    result = checker.check_output([sentence], {})
    assert not result.g1_pass, "Expected G1 Traceability failure for uncited assertive sentence"
    assert not result.passed
    assert any("lacks citation" in v for v in result.violations["G1"])


def test_compliant_draft_passes_all_gates(test_env):
    """Verify that a compliant assertive sentence passing G1-G6 succeeds."""
    checker, _ = test_env

    claim = Claim(
        id="c_exact_kiro",
        source_id="src_kiro_paper",
        text="The study reports that Amazon Kiro adoption resulted in a 15% increase in developer throughput.",
        source_excerpt="Amazon Kiro adoption resulted in a 15% increase in throughput.",
        value_json={"value": "15%", "unit": "%"},
        entity="Amazon Kiro",
        entity_match="exact",
        study_type="case_study",
        grade="moderate",
    )

    sentence = OutputSentence(
        id="s_ok",
        output_id="out1",
        ordinal=1,
        text="Early enterprise analysis suggests that Amazon Kiro delivers a 15% increase in developer throughput.",
        type="assertive",
        claim_ids_json=["c_exact_kiro"],
    )

    result = checker.check_output(
        sentences=[sentence],
        ledger_claims={"c_exact_kiro": claim},
        source_texts={"src_kiro_paper": "Preliminary study on Amazon Kiro workflows in enterprise software engineering."},
    )

    assert result.passed, f"Expected all gates to pass, got violations: {result.violations}"
    assert result.g1_pass
    assert result.g2_pass
    assert result.g3_pass
    assert result.g4_pass
    assert result.g5_pass
    assert result.g6_pass


def test_r13_corrupted_term_of_art():
    """R13: Corrupted term of art ('vibrate coding' instead of 'vibe coding') must be flagged."""
    from src.extract.term_normalizer import check_term_integrity
    from src.extract.claim_extractor import extract_claims_from_paper

    source_abstract = (
        "Spec-Driven Development (SDD) reconstitutes the engineering contracts that "
        "vibe coding dissolves: accountability, verifiability, and transferability."
    )

    # 1. Direct term integrity test
    is_valid, warnings = check_term_integrity(
        claim_text="SDD reconstitutes the contracts that vibrate coding dissolves.",
        source_text=source_abstract,
        key_terms=["vibrate coding"],
    )

    assert not is_valid, "Expected term integrity to fail on corrupted term 'vibrate coding'"
    assert any("Corrupted term of art detected: 'vibrate coding'" in w for w in warnings)

    # 2. Extraction-level flag and confidence penalty
    paper = {
        "title": "Spec-Driven Development for Agentic Software Engineering",
        "abstract": "SDD reconstitutes the contracts that vibrate coding dissolves: accountability and verifiability.",
        "year": 2026,
        "source": "arXiv",
    }
    claims = extract_claims_from_paper(paper)
    assert len(claims) > 0
    flagged_claim = claims[0]
    assert flagged_claim.extraction_confidence <= 0.50, "Extraction confidence must be penalized on corrupted terms"
    assert flagged_claim.context_json is not None
    assert "warnings" in flagged_claim.context_json
    assert any("vibrate coding" in str(w) for w in flagged_claim.context_json["warnings"])


def test_r8_stale_source_outside_time_window():
    """R8: A stale source outside the question's time window drops component S5."""
    from src.score.checker import GateCheckResult
    from src.score.scorer import QualityScorer
    from src.ledger.models import Question

    scorer = QualityScorer()
    gate_ok = GateCheckResult()

    question = Question(
        id="q-freshness-test",
        text="What are current generative AI engineering practices?",
        time_window_months=24,  # Requires claims within past 2 years (>= 2024/2025)
    )

    # Fresh claim from 2026
    c_fresh = Claim(
        id="c_fresh_1",
        question_id=question.id,
        source_id="src_fresh",
        text="Recent empirical findings from 2026.",
        source_excerpt="Findings from 2026.",
        claim_date="2026",
        grade="moderate",
    )

    # Stale claim from 2018 (way outside time window)
    c_stale = Claim(
        id="c_stale_1",
        question_id=question.id,
        source_id="src_stale",
        text="Old findings from early machine learning studies.",
        source_excerpt="Findings from 2018.",
        claim_date="2018",
        grade="moderate",
    )

    src_fresh = Source(id="src_fresh", lane="academic", source_type="peer_reviewed", title="Fresh Paper", pub_date="2026")
    src_stale = Source(id="src_stale", lane="academic", source_type="peer_reviewed", title="Stale Paper", pub_date="2018")

    sent_fresh = OutputSentence(id="sf", output_id="o1", ordinal=1, text="Modern AI systems show stability.", type="assertive", claim_ids_json=["c_fresh_1"])
    sent_stale = OutputSentence(id="ss", output_id="o2", ordinal=1, text="Historic ML systems show stability.", type="assertive", claim_ids_json=["c_stale_1"])

    score_fresh = scorer.calculate_score(
        gate_result=gate_ok,
        sentences=[sent_fresh],
        ledger_claims={"c_fresh_1": c_fresh},
        sources={"src_fresh": src_fresh},
        questions=[question],
    )

    score_stale = scorer.calculate_score(
        gate_result=gate_ok,
        sentences=[sent_stale],
        ledger_claims={"c_stale_1": c_stale},
        sources={"src_stale": src_stale},
        questions=[question],
    )

    # Fresh output receives full S5 score (10.0), stale output drops to 0.0
    assert score_fresh["components"]["S5_freshness_scope"] == 10.0
    assert score_stale["components"]["S5_freshness_scope"] == 0.0
    assert score_fresh["total_score"] > score_stale["total_score"]


def test_r9_known_contradiction_omitted():
    """R9: Omitting known contradictions from output drops component S4."""
    from src.score.checker import GateCheckResult
    from src.score.scorer import QualityScorer
    from src.ledger.models import Question

    scorer = QualityScorer()
    gate_ok = GateCheckResult()
    question = Question(id="q-test", text="Test Question")

    # Output with full gap disclosure and contradiction recall
    score_with_disclosure = scorer.calculate_score(
        gate_result=gate_ok,
        sentences=[],
        ledger_claims={},
        sources={},
        questions=[question],
        gap_outcomes_disclosed=1.0,
    )

    # Output where known contradictions/gaps were omitted (drop to 0.2)
    score_omitted = scorer.calculate_score(
        gate_result=gate_ok,
        sentences=[],
        ledger_claims={},
        sources={},
        questions=[question],
        gap_outcomes_disclosed=0.2,
    )

    assert score_with_disclosure["components"]["S4_gap_disclosure"] == 10.0
    assert score_omitted["components"]["S4_gap_disclosure"] == 2.0
    assert score_with_disclosure["total_score"] > score_omitted["total_score"]


def test_r11_rerun_reproducibility():
    """R11: Re-running extraction and deterministic grading on cached inputs must achieve >= 0.90 reproducibility."""
    from src.extract.claim_extractor import extract_claims_from_paper
    from src.grade.grader import Grader
    from src.score.scorer import QualityScorer
    from src.score.checker import GateCheckResult

    paper = {
        "title": "Amazon Kiro: Transforming Software Development",
        "abstract": "We evaluate Amazon Kiro across cloud engineering teams, measuring routine acceleration.",
        "year": 2025,
    }

    # Run 1
    claims_run1 = extract_claims_from_paper(paper)
    # Run 2 on same cached input
    claims_run2 = extract_claims_from_paper(paper)

    # Jaccard similarity of extracted texts
    set1 = {c.text for c in claims_run1}
    set2 = {c.text for c in claims_run2}
    jaccard = len(set1.intersection(set2)) / len(set1.union(set2)) if set1 else 1.0

    assert jaccard >= 0.90, f"Expected reproducibility >= 0.90, got {jaccard}"

    scorer = QualityScorer()
    score = scorer.calculate_score(
        gate_result=GateCheckResult(),
        sentences=[],
        ledger_claims={},
        sources={},
        questions=[],
        reproducibility_agreement=jaccard,
    )
    assert score["components"]["S7_reproducibility"] >= 9.0


def test_r14_raw_topic_boilerplate_lint():
    """R14: Raw topic string interpolated into boilerplate prose or repeated sentences must fail linting."""
    from src.synth.generator import lint_output_text

    raw_topic = "how Kiro is being used for development by engineering teams"

    # Bad sentence with raw topic string interpolated verbatim into boilerplate
    bad_sentences = [
        OutputSentence(
            id="s_bad1",
            output_id="out1",
            ordinal=1,
            text=f"In this strategy brief we explore how Kiro is being used for development by engineering teams across enterprises.",
            type="assertive",
            claim_ids_json=["c1"],
        ),
        # Repeated boilerplate sentence
        OutputSentence(
            id="s_bad2",
            output_id="out1",
            ordinal=2,
            text=f"In this strategy brief we explore how Kiro is being used for development by engineering teams across enterprises.",
            type="assertive",
            claim_ids_json=["c1"],
        ),
    ]

    is_clean, violations = lint_output_text(bad_sentences, raw_topic=raw_topic)
    assert not is_clean, "Expected R14 lint failure for raw topic interpolation and boilerplate repetition"
    assert any("R14 Lint Violation: Raw topic string" in v for v in violations)
    assert any("Repeated boilerplate sentence" in v for v in violations)




