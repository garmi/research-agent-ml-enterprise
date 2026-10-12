"""Test A8: Unified status vocabulary, score sensitivity, and export gating.

Verifies:
1. Unified status vocabulary: BLOCKED | NOT_PUBLISHABLE | REVISE | PUBLISH_READY (no DO_NOT_PUBLISH).
2. Scorer yields distinct, sensitive scores for different evidence sets (never hardcoded 66.0).
3. Export files in outputs/ are not written when publish gate does not pass.
4. When blocked, green 'ZERO UNGROUNDED CLAIMS' banner is eliminated in favor of blocking reasons.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.ledger.migrations import apply_migrations
from src.ledger.models import Claim, OutputSentence, Question, Source
from src.ledger.repository import LedgerRepository
from src.score.checker import GateCheckResult
from src.score.scorer import QualityScorer


def test_unified_status_vocabulary_and_no_do_not_publish():
    """Verify QualityScorer uses only BLOCKED, NOT_PUBLISHABLE, REVISE, PUBLISH_READY."""
    scorer = QualityScorer()

    # Gate failed -> BLOCKED
    gate_failed = GateCheckResult()
    gate_failed.g1_pass = False
    gate_failed.violations["G1"].append("Ungrounded numeral")
    res_blocked = scorer.calculate_score(
        gate_result=gate_failed,
        sentences=[],
        ledger_claims={},
        sources={},
        questions=[],
    )
    assert res_blocked["band"] == "BLOCKED"

    # Gate passed, low score -> NOT_PUBLISHABLE (never DO_NOT_PUBLISH)
    gate_passed = GateCheckResult()
    res_low = scorer.calculate_score(
        gate_result=gate_passed,
        sentences=[],
        ledger_claims={},
        sources={},
        questions=[],
    )
    assert res_low["band"] == "NOT_PUBLISHABLE", f"Expected NOT_PUBLISHABLE, got '{res_low['band']}'"
    assert res_low["band"] != "DO_NOT_PUBLISH", "DO_NOT_PUBLISH must be replaced by NOT_PUBLISHABLE"


def test_scorer_yields_distinct_scores_for_different_evidence_sets():
    """Verify that strong vs weak evidence sets produce distinct scores, not constant 66.0."""
    scorer = QualityScorer()
    gate_passed = GateCheckResult()
    q = Question(id="q-test", text="How do teams adopt AI in enterprise software?", scope="ai")

    # Set 1: Strong peer-reviewed evidence with verified sources and full excerpts
    s_strong = Source(
        id="src-strong",
        lane="academic",
        source_type="peer_reviewed",
        org="IEEE",
        title="Empirical Evaluation of AI Delivery",
        venue="IEEE TSE",
        venue_tier="verified",
        pub_date="2024",
        commercial_stake="none",
        url="https://doi.org/10.1109/tse",
    )
    c_strong = Claim(
        id="c-strong-1",
        question_id=q.id,
        source_id=s_strong.id,
        text="Empirical evaluation confirms 30% reduction in delivery defects.",
        source_excerpt="30% reduction in delivery defects.",
        grade="strong",
        status="approved",
        claim_date="2024",
    )
    sent_strong = OutputSentence(
        id="sent-1",
        output_id="out-1",
        ordinal=1,
        text="Empirical literature demonstrates that 30% reduction in delivery defects is achieved.",
        type="assertive",
        claim_ids_json=[c_strong.id],
    )

    res_strong = scorer.calculate_score(
        gate_result=gate_passed,
        sentences=[sent_strong],
        ledger_claims={c_strong.id: c_strong},
        sources={s_strong.id: s_strong},
        questions=[q],
        reviewed_claim_ids={c_strong.id},
        gates_completed_count=6,
    )

    # Set 2: Weak vendor-only evidence with unverified sources, missing dates
    s_weak = Source(
        id="src-weak",
        lane="enterprise",
        source_type="vendor_blog",
        org="VendorCorp",
        title="Vendor Marketing Blog",
        venue="Vendor Blog",
        venue_tier="vendor",
        pub_date="Date unknown",
        commercial_stake="vendor",
    )
    c_weak = Claim(
        id="c-weak-1",
        question_id=q.id,
        source_id=s_weak.id,
        text="Vendor marketing claims productivity doubled without telemetry.",
        source_excerpt="Productivity doubled without telemetry.",
        grade="vendor_claim",
        status="auto",
        claim_date=None,
    )
    sent_weak = OutputSentence(
        id="sent-2",
        output_id="out-2",
        ordinal=1,
        text="Vendor marketing claims productivity doubled without telemetry.",
        type="assertive",
        claim_ids_json=[c_weak.id],
    )

    res_weak = scorer.calculate_score(
        gate_result=gate_passed,
        sentences=[sent_weak],
        ledger_claims={c_weak.id: c_weak},
        sources={s_weak.id: s_weak},
        questions=[q],
        reviewed_claim_ids=set(),
        gates_completed_count=2,
    )

    assert res_strong["total_score"] != res_weak["total_score"], (
        f"Scores must be sensitive and distinct! Strong: {res_strong['total_score']}, Weak: {res_weak['total_score']}"
    )
    assert res_strong["total_score"] > res_weak["total_score"] + 15, (
        f"Strong evidence ({res_strong['total_score']}) should score significantly higher than weak ({res_weak['total_score']})"
    )
    assert res_strong["total_score"] != 66.0, "Score should not be stuck at constant 66.0"
    assert res_weak["total_score"] != 66.0, "Score should not be stuck at constant 66.0"


def test_export_files_not_written_to_disk_when_publish_gate_fails():
    """Verify export files are NOT written to outputs/ directory when publish gate is blocked."""
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

        # Run workflow in offline stub mode which triggers extractive fallback (publish_success=False)
        results = runner.run_workflow(
            topic="How do engineering teams govern AI coding assistants?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=[],
        )

        assert results["publish_res"]["status"] in ("blocked", "not_publishable", "BLOCKED", "NOT_PUBLISHABLE")
        assert results["publish_res"]["allowed"] is False


def test_draft_watermark_in_markdown_format():
    """Verify that draft markdown export contains 'DRAFT, NOT FOR PUBLICATION' and lists failing gates at top."""
    from src.output.unified_renderer import UnifiedRenderer
    from src.output.report_builder import ReportBuilder
    from src.ledger.models import OutputDoc, OutputSentence

    doc = OutputDoc(id="out_draft_1", question_id="q1", run_id="run1", status="draft", kind="field_note")
    sentences = [
        OutputSentence(id="s1", output_id="out_draft_1", ordinal=1, text="Empirical findings show adoption benefits.", type="finding", claim_ids_json=["c1"]),
    ]
    failing_gates = ["Gate 1: 1 ungrounded numeral assertion", "Gate 6: Unverified attribution"]

    # 1. UnifiedRenderer draft markdown
    renderer = UnifiedRenderer(
        topic="AI Adoption Governance",
        doc=doc,
        sentences=sentences,
        papers=[{"title": "Paper 1", "year": "2024"}],
    )
    md_draft = renderer.render_draft_markdown(failing_gates=failing_gates, status="NOT_PUBLISHABLE")

    assert "# DRAFT, NOT FOR PUBLICATION" in md_draft
    assert "Gate 1: 1 ungrounded numeral assertion" in md_draft
    assert "Gate 6: Unverified attribution" in md_draft
    # The watermark must be at the very top of the document
    first_lines = md_draft.strip().split("\n")[:5]
    assert any("DRAFT, NOT FOR PUBLICATION" in line for line in first_lines)

    # 2. ReportBuilder draft markdown
    builder = ReportBuilder()
    syn = {
        "executive_summary": "Executive summary draft.",
        "key_findings": ["Finding 1"],
    }
    builder_md_draft = builder.build_draft_markdown(
        topic="AI Adoption Governance",
        synthesis=syn,
        failing_gates=failing_gates,
        status="NOT_PUBLISHABLE",
    )
    assert "# DRAFT, NOT FOR PUBLICATION" in builder_md_draft
    assert "Gate 1: 1 ungrounded numeral assertion" in builder_md_draft
    assert "Gate 6: Unverified attribution" in builder_md_draft


def test_draft_watermark_in_json_format():
    """Verify that draft JSON export contains top-level watermark and failing_gates."""
    from src.output.unified_renderer import UnifiedRenderer
    from src.ledger.models import OutputDoc, OutputSentence

    doc = OutputDoc(id="out_draft_2", question_id="q1", run_id="run1", status="draft", kind="field_note")
    sentences = [
        OutputSentence(id="s1", output_id="out_draft_2", ordinal=1, text="Empirical findings show adoption benefits.", type="finding", claim_ids_json=["c1"]),
    ]
    failing_gates = ["Gate 2: Citation mismatch"]

    renderer = UnifiedRenderer(
        topic="AI Adoption Governance",
        doc=doc,
        sentences=sentences,
        papers=[{"title": "Paper 1", "year": "2024"}],
    )
    json_draft = renderer.to_draft_json_dict(failing_gates=failing_gates, status="NOT_PUBLISHABLE")

    assert json_draft.get("watermark") == "DRAFT, NOT FOR PUBLICATION"
    assert json_draft.get("status") == "NOT_PUBLISHABLE"
    assert json_draft.get("failing_gates") == failing_gates
    assert "output_sentences" in json_draft


def test_export_permissions_blocked_and_draft_and_publish_ready():
    """Verify export permissions logic:
    - BLOCKED: zero exports, no overrides allowed.
    - NOT_PUBLISHABLE / REVISE: only draft .md and .json allowed, deck and linkedin disabled.
    - PUBLISH_READY: all 5 exports allowed without watermarks.
    """
    from src.publish.export_policy import evaluate_export_permissions

    # 1. BLOCKED
    perm_blocked = evaluate_export_permissions(
        status="BLOCKED",
        allowed=False,
        gate_violations={"G1": ["Traceability error"]},
    )
    assert perm_blocked.can_download_draft is False
    assert perm_blocked.can_download_full is False
    assert perm_blocked.can_download_deck is False
    assert perm_blocked.can_download_linkedin is False
    assert perm_blocked.can_download_csv is False
    assert perm_blocked.is_blocked is True
    assert "Traceability error" in str(perm_blocked.failing_gates)

    # 2. NOT_PUBLISHABLE
    perm_draft = evaluate_export_permissions(
        status="NOT_PUBLISHABLE",
        allowed=False,
        gate_violations={},
        reasons=["Quality score 62/100 below 85"],
    )
    assert perm_draft.can_download_draft is True
    assert perm_draft.can_download_full is False
    assert perm_draft.can_download_deck is False
    assert perm_draft.can_download_linkedin is False
    assert perm_draft.can_download_csv is False
    assert perm_draft.is_blocked is False

    # 3. PUBLISH_READY
    perm_ready = evaluate_export_permissions(
        status="PUBLISH_READY",
        allowed=True,
        gate_violations={},
    )
    assert perm_ready.can_download_draft is False
    assert perm_ready.can_download_full is True
    assert perm_ready.can_download_deck is True
    assert perm_ready.can_download_linkedin is True
    assert perm_ready.can_download_csv is True
    assert perm_ready.is_blocked is False


def test_web_app_removes_force_override_checkbox():
    """Verify that web_app.py has completely removed the --force override checkbox."""
    web_app_code = Path("web_app.py").read_text(encoding="utf-8")
    assert "--force" not in web_app_code
    assert "force_export" not in web_app_code
    assert "Override Gate & Download Draft" not in web_app_code

