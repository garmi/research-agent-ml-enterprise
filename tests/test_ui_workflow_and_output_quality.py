"""Regression tests for UI workflow phases, left sidebar feedback loop, and output quality/traceability."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

from src.extract.claim_extractor import extract_claims_from_paper
from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.ledger.migrations import apply_migrations


def test_claim_extractor_does_not_split_sentences_on_abbreviations():
    """Verify that extract_claims_from_paper never cuts sentences in the middle on e.g., i.e., et al., vs., Fig."""
    paper = {
        "id": "p-abbrev-01",
        "title": "Empirical Study of Spec-Driven AI Agents in Enterprise Systems",
        "abstract": (
            "Modern engineering teams adopt automated verification gates (e.g., static contract checks, "
            "schema validators, i.e., runtime guards) to prevent regressions. "
            "Smith et al. (2024) compared spec-driven workflows vs. unconstrained prompting across Fig. 2 benchmarks "
            "and found a 34.5% reduction in production defects."
        ),
        "year": 2024,
        "venue": "ICSE",
        "url": "https://doi.org/10.1145/abbrev.2024",
    }

    claims = extract_claims_from_paper(paper, question_id="q-test-abbrev")
    assert len(claims) == 2, f"Expected exactly 2 full sentences, got {len(claims)}: {[c.text for c in claims]}"

    # First claim must contain both e.g. and i.e. and end with 'prevent regressions.'
    assert "e.g." in claims[0].text
    assert "i.e." in claims[0].text
    assert claims[0].text.endswith("prevent regressions.")

    # Second claim must contain et al., vs., Fig. 2, and 34.5%
    assert "et al." in claims[1].text
    assert "vs." in claims[1].text
    assert "34.5% reduction in production defects." in claims[1].text


def test_offline_stub_synthesis_produces_detailed_verdict_and_traceable_findings():
    """Verify that running with map_provider='stub' produces a non-empty verdict and findings with full source traceability."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.db")
        prac_db_path = str(Path(tmpdir) / "test_prac.db")
        q_yaml_path = str(Path(tmpdir) / "register.yaml")
        apply_migrations(db_path=db_path)
        apply_migrations(db_path=prac_db_path)

        runner = MultiLaneResearchRunner(
            db_path=db_path,
            practitioner_db_path=prac_db_path,
            questions_yaml_path=q_yaml_path,
        )
        # Thin fixture: this test checks drafting, not evidence volume (Check B thresholds, DEC-016).
        runner.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1}

        papers = [
            {
                "id": "p-trace-01",
                "title": "Empirical Evaluation of Automated Verification Gates in Software Delivery",
                "abstract": (
                    "Controlled experiments across 40 enterprise repositories demonstrate that automated verification "
                    "gates reduce software defect escape rates by 28% (e.g., in microservice APIs)."
                ),
                "year": 2024,
                "venue": "IEEE TSE",
                "doi": "10.1109/tse.2024.99",
                "url": "https://doi.org/10.1109/tse.2024.99",
                "relevance_score": 0.95,
            }
        ]

        res = runner.run_workflow(
            topic="How do automated verification gates affect software defect escape rates?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=papers,
        )

        # 1. Verdict must NOT be empty!
        assert res.get("verdict"), "Expected non-empty executive verdict even in offline/stub mode!"
        assert len(res["verdict"]) > 40

        # 2. Findings must be populated, untruncated, and carry full traceability metadata
        findings = res.get("findings", [])
        assert len(findings) > 0, "Expected at least 1 finding"
        f0 = findings[0]
        assert "[P1]" in f0["text"] or "28%" in f0["text"]
        assert "e.g., in microservice APIs" in f0["text"], f"Sentence was cut off mid-sentence: {f0['text']}"

        # Traceability fields on finding item
        assert "claim_ids" in f0 and len(f0["claim_ids"]) > 0
        assert "sources_trace" in f0 and len(f0["sources_trace"]) > 0
        trace0 = f0["sources_trace"][0]
        assert trace0["source_title"] == "Empirical Evaluation of Automated Verification Gates in Software Delivery"
        assert trace0["venue"] == "IEEE TSE"
        assert str(trace0["year"]) == "2024"
        assert trace0["url"] == "https://doi.org/10.1109/tse.2024.99"
        assert trace0["grade"] in ("STRONG", "MODERATE", "WEAK")
        assert len(trace0["excerpt"]) > 10


def test_web_app_sidebar_phase_tracker_and_feedback_loop_and_no_truncation():
    """Verify web_app.py renders the phase workflow tracker with feedback loops in the left sidebar and does not truncate claims at 90/70 chars."""
    web_app_code = Path("web_app.py").read_text(encoding="utf-8")

    # 1. No 90-char or 70-char hard truncation of assertions/excerpts in web_app.py
    assert 'c["assertion"][:90]' not in web_app_code, "Assertions must not be truncated at 90 characters"
    assert 'c["excerpt"][:70]' not in web_app_code, "Excerpts must not be truncated at 70 characters"
    assert "traces[:8]" not in web_app_code, "Sentence traces must not be truncated at 8 items"

    # 2. AppTest verification of sidebar workflow & feedback loop and rich output traceability
    at = AppTest.from_file("web_app.py")
    long_assertion = (
        "Controlled experiments across 120 enterprise software repositories demonstrate that "
        "spec-driven verification gates (e.g., contract tests and static type checks) reduce production "
        "incidents by 41% over a 12-month horizon without slowing deployment frequency."
    )
    at.session_state["research_results"] = {
        "topic": "How do verification gates affect software incidents?",
        "strategic_question": "How do verification gates affect software incidents?",
        "question_id": "q-verif-gates",
        "run_id": "run-test-123",
        "doc_id": "out-test-123",
        "is_fallback": False,
        "generation_mode": "model",
        "duration": "12s",
        "verdict": "Empirical evidence across 120 repositories confirms a 41% reduction in production incidents when automated verification gates are enforced [P1].",
        "gap_matrix": {
            "academic_state": "supported",
            "enterprise_state": "supported",
            "field_state": "not_searched",
            "outcome": 1,
            "outcome_label": "Outcome 1: Supported (Academic + Enterprise Aligned)",
            "rationale": "Academic empirical studies and enterprise surveys align on defect reduction.",
        },
        "lane_breakdown": {
            "academic_sources_count": 1,
            "academic_count": 1,
            "academic_claims_count": 1,
            "enterprise_sources_count": 1,
            "enterprise_claims_count": 1,
            "practitioner_observations_count": 0,
            "practitioner_claims_count": 0,
        },
        "papers": [
            {
                "id": "p-01",
                "key": "P1",
                "title": "Spec-Driven Verification Gates at Scale",
                "year": "2025",
                "venue": "ACM FSE",
                "doi": "10.1145/fse.2025.01",
                "type": "Peer-Reviewed",
                "url": "https://doi.org/10.1145/fse.2025.01",
                "relevance_score": 0.96,
                "is_custom": False,
            }
        ],
        "enterprise_sources": [],
        "practitioner_observations": [],
        "claims": [
            {
                "id": "c_p01_1",
                "lane": "ACADEMIC",
                "assertion": long_assertion,
                "excerpt": "spec-driven verification gates reduce production incidents by 41% over a 12-month horizon (Location: Abstract)",
                "grade": "STRONG",
                "entity": "Verification Gates",
                "entity_match": "exact",
                "study_type": "controlled_study",
                "source_title": "Spec-Driven Verification Gates at Scale",
                "source_url": "https://doi.org/10.1145/fse.2025.01",
                "venue": "ACM FSE",
                "year": "2025",
                "source_key": "P1",
                "rules": "Peer-reviewed controlled study",
                "is_custom": False,
            }
        ],
        "signals": [
            {"tag": "KEY SIGNAL 1", "text": "Automated verification gates reduce production incidents by 41% [P1].", "citation": "[P1]"},
        ],
        "findings": [
            {
                "id": "out_1_3",
                "ordinal": 3,
                "text": f"[P1] {long_assertion}",
                "claim_ids": ["c_p01_1"],
                "sources_trace": [
                    {
                        "claim_id": "c_p01_1",
                        "source_key": "P1",
                        "lane": "ACADEMIC",
                        "source_title": "Spec-Driven Verification Gates at Scale",
                        "venue": "ACM FSE",
                        "year": "2025",
                        "url": "https://doi.org/10.1145/fse.2025.01",
                        "grade": "STRONG",
                        "study_type": "controlled_study",
                        "excerpt": "spec-driven verification gates reduce production incidents by 41% over a 12-month horizon (Location: Abstract)",
                    }
                ],
            }
        ],
        "risks": ["Unverified third-party dependencies can bypass static checks if runtime schemas are omitted."],
        "roadmap": [{"phase": "Phase 1 (Days 1-30)", "action": "Deploy schema contract gates in CI", "impact": "41% fewer regressions"}],
        "negative_findings": [],
        "sentence_traces": [
            {"ordinal": 3, "text": f"[P1] {long_assertion}", "type": "assertive", "claims": ["c_p01_1"], "checks_json": {}}
        ],
        "metrics": {
            "volume": "1 Papers (1 claims) • 1 Enterprise Sources (1 claims) • 0 Field Observations",
            "sources": "2 Repositories",
            "horizon": "2025",
            "quality": "90/100 (PUBLISH_READY)",
        },
        "quality_scorecard": {"band": "PUBLISH_READY", "total_score": 90, "components": {"S1_evidence_strength": 28}},
        "gates_audit": {"passed": True, "reasons": []},
        "publish_res": {"status": "PUBLISH_READY", "allowed": True, "reasons": []},
    }
    at.run(timeout=15)
    assert not at.exception, f"AppTest raised exception: {at.exception}"

    sidebar_md = " ".join(m.value for m in at.sidebar.markdown)
    assert "Phase 1" in sidebar_md
    assert "Phase 2" in sidebar_md
    assert "Phase 3" in sidebar_md
    assert "Phase 4" in sidebar_md
    assert "Feedback Loop" in sidebar_md

    main_md = " ".join(m.value for m in at.markdown)
    # Full untruncated finding text and source traceability must be rendered
    assert "without slowing deployment frequency." in main_md
    assert "Spec-Driven Verification Gates at Scale" in main_md
    assert "ACM FSE" in main_md
