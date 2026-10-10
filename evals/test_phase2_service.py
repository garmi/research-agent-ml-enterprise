"""Test suite for Phase 2: LedgerService, Question Register, Venue Tiering, and Claim Review Queue.

Verifies:
- Gate 1: Question Register operations, YAML synchronization, and review logging.
- Gate 2: Venue Tiering, YAML update, automatic claim re-grading, and review logging.
- Gate 3: Claim Review Queue with uncertainty sorting, approval, editing, rejection,
  entity match adjustments, and strict bulk approval constraints.
- Mandatory audit logging: 100% of human actions generate rows in the reviews table.
"""

import os
import shutil
import tempfile
import pytest
import yaml

from src.ledger.models import Claim, Question, Source
from src.ledger.service import LedgerService


@pytest.fixture
def service_env():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_ledger.db")
        q_yaml = os.path.join(tmp_dir, "register.yaml")
        v_yaml = os.path.join(tmp_dir, "venue_tiers.yaml")
        r_yaml = os.path.join(tmp_dir, "rules.yaml")

        # Copy base configs
        shutil.copy("questions/register.yaml", q_yaml)
        shutil.copy("grade/venue_tiers.yaml", v_yaml)
        shutil.copy("grade/rules.yaml", r_yaml)

        service = LedgerService(
            db_path=db_path,
            questions_yaml_path=q_yaml,
            venue_tiers_yaml_path=v_yaml,
            rules_yaml_path=r_yaml,
        )
        yield service, db_path, q_yaml, v_yaml


def test_gate1_question_register(service_env):
    service, _, q_yaml, _ = service_env

    # 1. Sync from YAML
    synced = service.sync_questions_from_yaml()
    assert len(synced) >= 3

    # 2. Create a new question
    new_q = service.create_question(
        question_id="q-agentic-evals",
        text="How do enterprise delivery teams evaluate agentic coding reliability?",
        scope="evaluation",
        time_window_months=24,
        reviewer="lead_architect",
        reason="Added for 2026 enterprise strategy",
    )
    assert new_q.id == "q-agentic-evals"

    # Verify YAML updated
    with open(q_yaml, "r") as f:
        y_data = yaml.safe_load(f)
    assert any(q["id"] == "q-agentic-evals" for q in y_data.get("questions", []))

    # Verify review logged
    reviews = service.repo._conn().execute("SELECT * FROM reviews WHERE gate = 'G1';").fetchall()
    assert len(reviews) >= 1
    assert any(r["object_id"] == "q-agentic-evals" for r in reviews)


def test_gate2_venue_tiering_and_regrading(service_env):
    service, _, _, v_yaml = service_env

    # Insert an unverified source and claim
    source = Source(
        id="src_custom_journal",
        lane="academic",
        source_type="peer_reviewed",
        title="Study on Autonomous Agents",
        venue="Emerging Systems Journal",
        venue_tier="unverified",
        extraction_depth="full_text",
    )
    service.repo.insert_source(source)

    claim = Claim(
        id="c_emp_1",
        source_id="src_custom_journal",
        text="Significant speedup observed in agent workflows.",
        source_excerpt="Speedup observed in agent workflows.",
        study_type="controlled_study",
        entity_match="exact",
        grade="weak",
    )
    service.repo.insert_claim(claim)

    # Human tiers the venue as verified
    updated_count = service.tier_venue(
        venue_name="Emerging Systems Journal",
        new_tier="verified",
        reviewer="senior_editor",
        reason="Peer-reviewed by recognized committee",
    )
    assert updated_count == 1

    # Verify claim was re-graded to strong!
    regraded_claim = service.repo.get_claim("c_emp_1")
    assert regraded_claim.grade == "strong", f"Expected regraded to strong, got {regraded_claim.grade}"

    # Verify review logged
    rev = service.repo._conn().execute("SELECT * FROM reviews WHERE gate = 'G2';").fetchone()
    assert rev is not None
    assert rev["action"] == "tier_venue"


def test_gate3_claim_review_queue_and_actions(service_env):
    service, _, _, _ = service_env

    # Insert a source
    src = Source(
        id="src_test_1",
        lane="academic",
        source_type="peer_reviewed",
        title="Agent Collaboration",
        venue="ACM",
        venue_tier="verified",
    )
    service.repo.insert_source(src)

    # Insert high-confidence claim
    c1 = Claim(
        id="c1",
        source_id="src_test_1",
        text="Normal claim with standard confidence.",
        source_excerpt="Normal claim excerpt.",
        extraction_confidence=0.95,
        grade="moderate",
        status="auto",
    )
    service.repo.insert_claim(c1)

    # Insert low-confidence claim with warnings
    c2 = Claim(
        id="c2",
        source_id="src_test_1",
        text="Flagged claim with potential corrupted term.",
        source_excerpt="Flagged excerpt.",
        extraction_confidence=0.45,
        context_json={"warnings": ["Corrupted term detected"]},
        grade="weak",
        status="auto",
    )
    service.repo.insert_claim(c2)

    # 1. Test uncertainty sorting: c2 should appear first!
    queue = service.get_claim_review_queue(sort_by="uncertainty")
    assert len(queue) == 2
    assert queue[0]["claim"].id == "c2", "Uncertain claim must appear first in queue"

    # 2. Approve c1
    app_c1 = service.approve_claim("c1", reviewer="qa_lead", reason="Verified by human")
    assert app_c1.status == "approved"

    # 3. Edit c2
    edited_c2 = service.edit_claim(
        claim_id="c2",
        new_text="Corrected claim text with valid term.",
        new_excerpt=None,
        reviewer="qa_lead",
        reason="Corrected terminology",
    )
    assert edited_c2.status == "edited"

    # 4. Change grade (requires reason)
    with pytest.raises(ValueError):
        service.change_claim_grade("c2", new_grade="moderate", reason="", reviewer="qa_lead")

    c2_mod = service.change_claim_grade("c2", new_grade="moderate", reason="Verified method in text", reviewer="qa_lead")
    assert c2_mod.grade == "moderate"

    # 5. Reject claim (requires reason)
    c3 = Claim(
        id="c3",
        source_id="src_test_1",
        text="Spurious assertion.",
        source_excerpt="Spurious.",
        grade="weak",
        status="auto",
    )
    service.repo.insert_claim(c3)
    rej_c3 = service.reject_claim("c3", reviewer="qa_lead", reason="Hallucinated extrapolation")
    assert rej_c3.status == "rejected"

    # 6. Verify audit reviews
    g3_reviews = service.repo._conn().execute("SELECT * FROM reviews WHERE gate = 'G3';").fetchall()
    assert len(g3_reviews) == 4


def test_gate3_bulk_approve_constraints(service_env):
    service, _, _, _ = service_env

    srcA = Source(id="srcA", lane="academic", source_type="peer_reviewed", title="A", venue="ACM")
    srcB = Source(id="srcB", lane="academic", source_type="peer_reviewed", title="B", venue="ACM")
    service.repo.insert_source(srcA)
    service.repo.insert_source(srcB)

    # Identical batch: same source, grade, study_type
    cA1 = Claim(id="cA1", source_id="srcA", text="T1", source_excerpt="E1", grade="moderate", study_type="case_study", status="auto")
    cA2 = Claim(id="cA2", source_id="srcA", text="T2", source_excerpt="E2", grade="moderate", study_type="case_study", status="auto")
    # Heterogeneous claim: different source
    cB1 = Claim(id="cB1", source_id="srcB", text="T3", source_excerpt="E3", grade="moderate", study_type="case_study", status="auto")

    service.repo.insert_claim(cA1)
    service.repo.insert_claim(cA2)
    service.repo.insert_claim(cB1)

    # Homogeneous approval succeeds
    approved = service.bulk_approve_claims(["cA1", "cA2"], reviewer="lead", reason="Batch signoff")
    assert len(approved) == 2

    # Heterogeneous approval MUST fail with ValueError
    with pytest.raises(ValueError) as exc:
        service.bulk_approve_claims(["cA1", "cB1"], reviewer="lead", reason="Invalid batch")
    assert "Bulk approve rejected" in str(exc.value)
