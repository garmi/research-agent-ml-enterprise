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


def test_r12_practitioner_claim_unabstracted_blocked(test_env):
    """R12: A practitioner claim exported without confirmed abstraction must fail Gate G5 and block publishing."""
    checker, _ = test_env

    # 1. Check GateChecker blocks un-abstracted practitioner claim
    unabstracted_claim = Claim(
        id="c_prac_unabstracted",
        source_id="src_prac_1",
        text="Practitioner observation shows 40% defect spike during pilot.",
        source_excerpt="Observation shows defect spike during pilot.",
        study_type="practitioner_observation",
        context_json={
            "situation": "Pilot at client Bank of America",
            "lane": "practitioner",
            "abstraction_confirmed": False,  # Not abstracted!
        },
        grade="anecdote",
    )

    sentence = OutputSentence(
        id="s12",
        output_id="out1",
        ordinal=1,
        text="Practitioner reports suggest defect spikes occur during early un-governed pilots.",
        type="assertive",
        claim_ids_json=["c_prac_unabstracted"],
    )

    res = checker.check_output([sentence], {"c_prac_unabstracted": unabstracted_claim})
    assert not res.g5_pass, "Expected G5 failure for unabstracted practitioner claim"
    assert not res.passed
    assert any("without confirmed abstraction" in v for v in res.violations["G5"])

    # 2. Check PractitionerCollector raises PermissionError when exporting unabstracted claim
    from src.collectors.practitioner.collector import PractitionerCollector
    from src.ledger.repository import LedgerRepository

    with tempfile.TemporaryDirectory() as tmpdir:
        prac_db = os.path.join(tmpdir, "test_prac.db")
        ledger_db = os.path.join(tmpdir, "test_ledger.db")
        collector = PractitionerCollector(db_path=prac_db)
        ledger_repo = LedgerRepository(db_path=ledger_db)

        # Record observation without abstraction
        _, unabs_claim = collector.add_observation(
            question_id="q1",
            situation="Confidential project Titan rollout",
            decision="Mandated spec",
            action="Deployed gate",
            outcome="Success",
            sector="financial_services",
            abstraction_confirmed=False,
        )

        with pytest.raises(PermissionError) as exc_info:
            collector.export_abstracted_claim_to_ledger(unabs_claim.id, ledger_repo)

        assert "Gate 6 Abstraction Violation" in str(exc_info.value)


def test_r15_d1_canned_findings_rejected(test_env):
    """R15: Output sentences must never contain the D1 hardcoded canned strings."""
    sentence = OutputSentence(
        id="s_canned",
        output_id="out1",
        ordinal=1,
        text="Empirical velocity increases by 32% across standard delivery tasks [P1].",
        type="assertive",
        claim_ids_json=[],
    )
    checker, _ = test_env
    res = checker.check_output([sentence], {})
    assert not res.g1_pass
    assert not res.passed


def test_r16_d2_silent_fallback_prevented_and_sanitized():
    """R16: Runtime errors during synthesis must be captured with sanitized details, blocking publication."""
    import tempfile
    from pathlib import Path
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.ledger.migrations import apply_migrations

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.db")
        prac_db_path = str(Path(tmpdir) / "test_prac.db")
        apply_migrations(db_path=db_path)
        apply_migrations(db_path=prac_db_path)
        questions_yaml = str(Path(tmpdir) / "register.yaml")
        runner = MultiLaneResearchRunner(
            db_path=db_path,
            practitioner_db_path=prac_db_path,
            questions_yaml_path=questions_yaml,
        )
        res = runner.run_workflow(
            topic="Test topic for fallback verification",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=[],
        )
        # With zero evidence Check A stops before any generation (DEC-016); otherwise fallback is labelled.
        assert res.get("generation_mode") == "extractive_fallback" or res.get("stopped_at") == "check_a"
        assert res["publish_res"]["allowed"] is False
        assert res["publish_res"]["status"] in ("NOT_PUBLISHABLE", "BLOCKED")


def test_r17_d3_uncited_assertive_sentence_fails_g1_unless_negative_finding(test_env):
    """R17: An assertive sentence without claims fails G1; negative_finding with search_log passes."""
    checker, _ = test_env

    # 1. Uncited assertive sentence
    s_uncited = OutputSentence(
        id="s_uncited",
        output_id="out1",
        ordinal=1,
        text="The evidence does not support claims of complete autonomous lifecycle displacement without human oversight.",
        type="assertive",
        claim_ids_json=[],
    )
    res1 = checker.check_output([s_uncited], {})
    assert not res1.g1_pass
    assert not res1.passed

    # 2. Negative finding with search_log_id
    s_neg = OutputSentence(
        id="s_neg",
        output_id="out1",
        ordinal=2,
        text="No empirical evidence identified across academic literature for this topic.",
        type="negative_finding",
        claim_ids_json=[],
        checks_json={"search_log_id": "slog_123"},
    )
    res2 = checker.check_output([s_neg], {})
    assert res2.g1_pass


def test_r18_d3_template_verb_stutter_detected():
    """R18: Sentences with doubled verb phrases ('suggests that The study reports that') must fail linting."""
    from src.synth.generator import lint_output_text

    stutter_sentences = [
        OutputSentence(
            id="s_stutter",
            output_id="out1",
            ordinal=1,
            text="Empirical literature suggests that The study reports that developer velocity improved.",
            type="assertive",
            claim_ids_json=["c1"],
        )
    ]
    is_clean, violations = lint_output_text(stutter_sentences)
    assert not is_clean, "Expected lint failure on template verb stutter"
    assert any("Template verb stutter detected" in v for v in violations)


def test_r19_d4_practitioner_observation_leakage_prevented():
    """R19: Practitioner observations entered for Question A must not leak into Question B."""
    import tempfile
    from pathlib import Path
    from src.collectors.practitioner.collector import PractitionerCollector
    from src.ledger.migrations import apply_migrations
    from src.ledger.models import Question

    with tempfile.TemporaryDirectory() as tmpdir:
        prac_db = str(Path(tmpdir) / "test_prac.db")
        apply_migrations(db_path=prac_db)
        col = PractitionerCollector(db_path=prac_db)

        q1 = Question(id="q1", text="Question One (Software)")
        q2 = Question(id="q2", text="Question Two (Healthcare)")
        col.repo.insert_question(q1)
        col.repo.insert_question(q2)

        col.add_observation(
            question_id="q1",
            situation="140 enterprise microservices migration",
            decision="Enforced gate",
            action="Executed deployment",
            outcome="No regressions",
            sector="software",
            abstraction_confirmed=True,
        )

        q2_obs = col.repo.list_claims(question_id="q2")
        assert len(q2_obs) == 0, f"Leaked observations into Q2: {q2_obs}"


def test_r20_d4_registry_counted_as_sources_not_claims():
    """R20: Enterprise feeds are counted as sources, not claims; vendor-only sources cap at Outcome 2."""
    import tempfile
    from pathlib import Path
    from src.gaps.matrix_builder import GapMatrixBuilder
    from src.ledger.migrations import apply_migrations
    from src.ledger.models import Claim, Question, Source
    from src.ledger.repository import LedgerRepository

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.db")
        apply_migrations(db_path=db_path)
        repo = LedgerRepository(db_path=db_path)
        builder = GapMatrixBuilder(db_path=db_path, rules_path="grade/rules.yaml")

        q = Question(id="q-reg", text="Enterprise feed test")
        repo.insert_question(q)

        # Peer-reviewed academic source
        acad_src = Source(
            id="src_acad", lane="academic", source_type="peer_reviewed",
            title="Academic Research", venue="ACM", venue_tier="verified",
            commercial_stake="none", status="active",
        )
        repo.insert_source(acad_src)
        repo.insert_claim(
            Claim(
                id="c_acad", question_id=q.id, source_id=acad_src.id,
                text="Academic claim", source_excerpt="Academic excerpt",
                grade="strong", status="approved",
            )
        )

        # Vendor-only enterprise sources
        for i in range(4):
            v_src = Source(
                id=f"src_v{i}", lane="enterprise", source_type="vendor_blog",
                title=f"Vendor Blog {i}", venue_tier="unverified", commercial_stake="vendor", status="active",
            )
            repo.insert_source(v_src)
            repo.insert_claim(
                Claim(
                    id=f"c_v{i}", question_id=q.id, source_id=v_src.id, text=f"Vendor claim {i}",
                    source_excerpt=f"Vendor claim excerpt {i}",
                    grade="vendor_claim", context_json={"source_stake": "vendor"}, status="approved",
                )
            )

        entry = builder.evaluate_question_lanes(question_id=q.id, run_id="run_reg")
        assert entry.outcome == 2, f"Expected Outcome 2 due to vendor capping, got {entry.outcome}"
        assert "vendor" in entry.rationale.lower()


def test_r21_d5_stale_year_rejected_at_retrieval():
    """R21: Papers published before min_year (2020) must be rejected with year_below_minimum."""
    import tempfile
    from pathlib import Path
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.ledger.migrations import apply_migrations
    from src.ledger.models import Question, Run
    from src.ledger.repository import LedgerRepository

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.db")
        prac_db = str(Path(tmpdir) / "test_prac.db")
        apply_migrations(db_path=db_path)
        apply_migrations(db_path=prac_db)
        questions_yaml = str(Path(tmpdir) / "register.yaml")
        runner = MultiLaneResearchRunner(db_path=db_path, practitioner_db_path=prac_db, questions_yaml_path=questions_yaml)
        repo = LedgerRepository(db_path=db_path)

        q = Question(id="q-stale", text="Modern AI adoption in teams")
        repo.insert_question(q)
        run = Run(id="run-stale", question_id=q.id, engine="stub", status="completed")
        repo.insert_run(run)

        stale_paper = {
            "id": "paper-stale-2008",
            "title": "A Technology Acceptance Study in Legacy Systems",
            "abstract": "We explore user acceptance of automation frameworks in corporate settings.",
            "year": 2008,
            "venue": "Legacy Journal",
            "url": "https://doi.org/10.1000/2008.01",
        }

        harvested = runner._harvest_academic_lane(
            topic="Modern AI adoption in teams",
            query_limit=1,
            max_per_query=5,
            max_papers=5,
            override=[stale_paper],
            question_id=q.id,
            run_id=run.id,
        )
        assert len(harvested) == 0, "Stale paper from 2008 should have been rejected"

        logs = repo.list_search_logs(question_id="q-stale")
        rejected_logs = [l for l in logs if l.rejected_reason and "year_below_minimum" in l.rejected_reason]
        assert len(rejected_logs) > 0, "Expected search_log with year_below_minimum rejection"


def test_r22_d5_venue_never_equals_api_provider_name():
    """R22: Resolved venue must never display API provider names like 'Crossref' or 'Semantic Scholar'."""
    from src.analysis.multilane_runner import resolve_honest_venue_and_type

    raw_paper = {
        "title": "Study on Software Systems",
        "venue": "Crossref",
        "container_title": "IEEE Transactions on Software Engineering",
        "publisher": "IEEE",
    }
    venue, stype = resolve_honest_venue_and_type(raw_paper)
    assert venue != "Crossref", f"Venue should not be 'Crossref', got '{venue}'"
    assert "IEEE" in venue
    assert stype in ("Peer-Reviewed Journal", "Conference", "Preprint")


def test_r23_d6_contradictory_status_banner_blocked():
    """R23: QualityScorer with failing gates must yield BLOCKED, not publishable, and never DO_NOT_PUBLISH."""
    from src.score.checker import GateCheckResult
    from src.score.scorer import QualityScorer

    scorer = QualityScorer()
    gate_fail = GateCheckResult()
    gate_fail.g1_pass = False
    gate_fail.violations["G1"].append("Uncited assertive sentence")
    score_res = scorer.calculate_score(gate_result=gate_fail, sentences=[], ledger_claims={}, sources={}, questions=[])

    assert score_res["band"] in ("BLOCKED", "NOT_PUBLISHABLE")
    assert score_res["band"] != "DO_NOT_PUBLISH"
    assert score_res["is_blocked"] is True


def test_r24_d7_unconfirmed_practitioner_abstraction_blocks_gate_6():
    """R24: Custom practitioner observations without human sign-off must fail Gate 6 and block publication."""
    import tempfile
    from pathlib import Path
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.ledger.migrations import apply_migrations

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.db")
        prac_db = str(Path(tmpdir) / "test_prac.db")
        apply_migrations(db_path=db_path)
        apply_migrations(db_path=prac_db)
        questions_yaml = str(Path(tmpdir) / "register.yaml")
        runner = MultiLaneResearchRunner(db_path=db_path, practitioner_db_path=prac_db, questions_yaml_path=questions_yaml)

        res = runner.run_workflow(
            topic="How do engineering teams prevent latency regressions?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            custom_prac_urls=["Incident observation: unconfirmed private database dump"],
            practitioner_abstraction_confirmed=False,
            academic_papers_override=[],
        )
        assert res["publish_res"]["status"] == "BLOCKED"
        assert "Gate 6: Practitioner abstraction not confirmed by operator." in (
            res["publish_res"].get("reason", "") + " " + str(res["publish_res"].get("gate_results", {}).get("violations", {}))
        )


def test_r25_d8_unsourced_roadmap_numerals_fail_g2(test_env):
    """R25: Roadmap statements containing numbers (e.g. 20%, 80%) not grounded in claims fail Gate 2."""
    checker, _ = test_env

    claim = Claim(
        id="c_general",
        source_id="src_p1",
        text="Teams reported improvements in workflow efficiency.",
        source_excerpt="Improvements in efficiency.",
        grade="moderate",
    )
    roadmap_sentence = OutputSentence(
        id="s_road",
        output_id="out1",
        ordinal=1,
        text="Target milestone: achieve a Cycle time reduction of 20% and Developer adoption > 80%.",
        type="assertive",
        claim_ids_json=["c_general"],
    )
    res = checker.check_output([roadmap_sentence], {"c_general": claim})
    assert not res.g2_pass, "Expected G2 Numeric Fidelity failure for ungrounded numbers 20% and 80%"
    assert not res.passed
    assert any("20%" in v or "80%" in v for v in res.violations["G2"])


def test_r26_wrong_topic_paper_citation_blocked(test_env):
    """R26: Citing a healthcare paper for a software engineering question fails Gate 1 Support Check 3."""
    from src.ledger.models import Question
    checker, _ = test_env

    health_claim = Claim(
        id="c_health_1",
        source_id="src_health",
        text="The EU AI Act specifies implications and compliance guidance for healthcare facilities.",
        source_excerpt="The EU AI Act outlines compliance guidance for healthcare facilities.",
        value_json={"value": "32%", "unit": "%"},
        entity="EU AI Act Healthcare",
        grade="moderate",
    )
    soft_sentence = OutputSentence(
        id="s_mismatch",
        output_id="out1",
        ordinal=1,
        text="Empirical velocity increases by 32% across standard delivery tasks in engineering teams.",
        type="assertive",
        claim_ids_json=["c_health_1"],
    )
    source = Source(
        id="src_health",
        lane="academic",
        source_type="peer_reviewed",
        title="The EU AI Act: implications and compliance guidance for healthcare facilities",
    )
    question = Question(
        id="q_soft",
        text="What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?",
    )

    res = checker.check_output(
        sentences=[soft_sentence],
        ledger_claims={"c_health_1": health_claim},
        sources={"src_health": source},
        question=question,
    )
    assert not res.g3_pass or not res.passed, "Expected Gate failure due to source-to-question topic mismatch (D1 defect)"
    assert any("Source topic mismatch" in v or "citation support check" in v for v in res.violations["G3"])






