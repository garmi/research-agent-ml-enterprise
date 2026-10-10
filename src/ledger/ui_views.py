"""Streamlit UI views for Research Engine v2 human gates:
- View 1: Claim Review Queue (Gate 3)
- View 2: Venue and Source Tiering (Gate 2)
- View 3: Question Register (Gate 1)
All user actions write immutable audit logs to the SQLite reviews table.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from typing import Any, Dict, List, Optional

from src.ledger.service import LedgerService


def render_question_register(service: LedgerService) -> None:
    """Render View 3: Question Register (Gate 1)."""
    st.header("📋 Gate 1: Strategic Question Register")
    st.markdown(
        "Manage active research questions, evaluation scopes, and freshness time windows. "
        "All updates synchronize with `questions/register.yaml` and log to the append-only `reviews` audit trail."
    )

    questions = service.repo.list_questions()
    
    col1, col2, col3 = st.columns(3)
    active_count = sum(1 for q in questions if q.status == "active")
    retired_count = sum(1 for q in questions if q.status == "retired")
    col1.metric("Active Questions", active_count)
    col2.metric("Retired Questions", retired_count)
    col3.metric("Total Questions", len(questions))

    st.markdown("---")
    st.subheader("Active & Registered Questions")
    if questions:
        q_data = [
            {
                "ID": q.id,
                "Question": q.text,
                "Scope": q.scope,
                "Time Window (Months)": q.time_window_months,
                "Status": q.status.upper(),
                "Version": q.version,
            }
            for q in questions
        ]
        st.dataframe(pd.DataFrame(q_data), use_container_width=True)
    else:
        st.info("No questions in register. Syncing default questions from YAML...")
        service.sync_questions_from_yaml()
        st.rerun()

    # Form to add a new question
    with st.expander("➕ Register New Research Question", expanded=False):
        with st.form("new_question_form"):
            q_id = st.text_input("Question ID (e.g. q-agentic-sdlc-gov)", placeholder="q-governance-eval")
            q_text = st.text_area("Question Text", placeholder="How do multi-vendor teams govern autonomous AI code generators?")
            col_a, col_b = st.columns(2)
            q_scope = col_a.selectbox("Scope", ["enterprise", "governance", "kiro", "productivity", "security"])
            q_window = col_b.number_input("Time Window (Months)", min_value=6, max_value=60, value=36)
            q_reason = st.text_input("Rationale / Justification", value="Strategic thought-leadership priority")
            submitted = st.form_submit_button("Register Question")
            if submitted:
                if q_id.strip() and q_text.strip():
                    service.create_question(
                        question_id=q_id.strip(),
                        text=q_text.strip(),
                        scope=q_scope,
                        time_window_months=int(q_window),
                        reviewer="human_operator",
                        reason=q_reason,
                    )
                    st.success(f"Question '{q_id}' registered successfully!")
                    st.rerun()
                else:
                    st.error("Please provide both an ID and Question text.")

    # Status update action
    if questions:
        with st.expander("🔄 Update Question Status", expanded=False):
            col_sel, col_stat = st.columns(2)
            target_q_id = col_sel.selectbox("Select Question", [q.id for q in questions])
            new_status = col_stat.selectbox("Set Status", ["active", "retired", "draft"])
            status_reason = st.text_input("Status Change Reason", value="Lifecycle status update")
            if st.button("Apply Status Change"):
                service.update_question_status(
                    question_id=target_q_id,
                    new_status=new_status,
                    reviewer="human_operator",
                    reason=status_reason,
                )
                st.success(f"Updated status of '{target_q_id}' to {new_status}!")
                st.rerun()


def render_venue_tiering(service: LedgerService) -> None:
    """Render View 2: Venue and Source Tiering (Gate 2)."""
    st.header("🏛️ Gate 2: Venue & Source Tiering")
    st.markdown(
        "Audit publication venues and tier them according to refereeing rigor. "
        "Decisions persist to `grade/venue_tiers.yaml` and trigger automatic deterministic re-grading across attached claims."
    )

    venues = service.list_venues()

    # Metrics
    tier_counts = {"verified": 0, "reputable_preprint": 0, "unverified": 0, "vendor": 0}
    for v in venues:
        tier = v.get("venue_tier", "unverified")
        tier_counts[tier] = tier_counts.get(tier, 0) + v.get("source_count", 0)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Verified Venues", tier_counts.get("verified", 0))
    m2.metric("Reputable Preprints", tier_counts.get("reputable_preprint", 0))
    m3.metric("Unverified Sources", tier_counts.get("unverified", 0))
    m4.metric("Vendor Sources", tier_counts.get("vendor", 0))

    st.markdown("---")
    st.subheader("Venues in Database")
    if venues:
        st.dataframe(pd.DataFrame(venues), use_container_width=True)
    else:
        st.info("No venues recorded yet in ledger. Ingest papers to view venue tiering.")

    # Tier update form
    with st.expander("⚖️ Override or Assign Venue Tier", expanded=True):
        distinct_venue_names = sorted(list({v["venue"] for v in venues if v.get("venue")}))
        if distinct_venue_names:
            with st.form("tier_venue_form"):
                target_venue = st.selectbox("Select Venue", distinct_venue_names)
                new_tier = st.selectbox("Target Tier", ["verified", "reputable_preprint", "unverified", "vendor"])
                reason = st.text_input("Reviewer Justification (Mandatory)", placeholder="e.g. Peer-reviewed journal indexed by ACM")
                update_btn = st.form_submit_button("Persist Tier & Re-grade Attached Claims")
                if update_btn:
                    if not reason.strip():
                        st.error("Justification is mandatory for venue tier changes.")
                    else:
                        updated = service.tier_venue(
                            venue_name=target_venue,
                            new_tier=new_tier,  # type: ignore
                            reviewer="human_operator",
                            reason=reason.strip(),
                        )
                        st.success(f"Updated venue '{target_venue}' to '{new_tier}'. {updated} sources and their claims were re-graded!")
                        st.rerun()
        else:
            st.info("No venues available to tier.")


def render_claim_review_queue(service: LedgerService) -> None:
    """Render View 1: Claim Review Queue (Gate 3)."""
    st.header("⚖️ Gate 3: Claim Review Queue")
    st.markdown(
        "Human-in-the-loop audit for extracted atomic claims. "
        "Claims are prioritised by **uncertainty** (low confidence, potential corrupted terms, boundary grades). "
        "Every approval, edit, rejection, or grade adjustment creates an append-only row in `reviews`."
    )

    questions = service.repo.list_questions()
    q_options = ["All Questions"] + [q.id for q in questions]

    col_q, col_stat, col_sort = st.columns(3)
    selected_q = col_q.selectbox("Filter Question", q_options)
    selected_status = col_stat.selectbox("Status Filter", ["All", "auto", "approved", "edited", "rejected"])
    selected_sort = col_sort.selectbox("Sort Priority", ["uncertainty", "grade"])

    q_filter = None if selected_q == "All Questions" else selected_q
    s_filter = None if selected_status == "All" else selected_status

    queue = service.get_claim_review_queue(
        question_id=q_filter,
        sort_by=selected_sort,
        status_filter=s_filter,
    )

    st.markdown(f"**Found {len(queue)} claims matching filters.**")

    # Display claims
    for idx, item in enumerate(queue, start=1):
        claim = item["claim"]
        source = item["source"]
        has_warnings = item["has_warnings"]

        status_color = "gray"
        if claim.status == "approved":
            status_color = "green"
        elif claim.status == "rejected":
            status_color = "red"
        elif claim.status == "edited":
            status_color = "blue"

        with st.container():
            st.markdown(f"### Claim #{idx}: `{claim.id}` | Status: :{status_color}[{claim.status.upper()}]")
            if has_warnings:
                st.warning(f"⚠️ **Term Warning / Uncertainty Flag:** {claim.context_json.get('warnings')}")

            col_claim, col_evidence = st.columns([1, 1])

            with col_claim:
                st.markdown("**Paraphrased Atomic Assertion:**")
                st.info(claim.text)
                st.markdown(f"**Target Entity:** `{claim.entity}` (Match: `{claim.entity_match}`)")
                st.markdown(f"**Study Type:** `{claim.study_type}`")
                st.markdown(f"**Extraction Confidence:** `{claim.extraction_confidence:.2f}`")
                if claim.value_json:
                    st.markdown(f"**Extracted Numerals:** `{claim.value_json}`")

            with col_evidence:
                st.markdown("**Verbatim Source Excerpt (Max 25 Words):**")
                st.success(f'"{claim.source_excerpt}"')
                if source:
                    st.markdown(f"**Source:** *{source.title}* ({source.pub_date or 'N/A'})")
                    st.markdown(f"**Venue:** `{source.venue or 'N/A'}` (Tier: `{source.venue_tier}`)")
                st.markdown(f"**Assigned Grade:** `{claim.grade.upper()}`")
                if claim.grade_reasons_json:
                    with st.expander("Grading Rules Triggered", expanded=False):
                        for r in claim.grade_reasons_json:
                            st.write(f"- {r}")

            # Review Actions
            act_col1, act_col2, act_col3 = st.columns([1, 1, 2])

            with act_col1:
                if claim.status != "approved":
                    if st.button(f"✅ Approve", key=f"app_{claim.id}"):
                        service.approve_claim(claim.id, reviewer="human_operator")
                        st.success(f"Claim {claim.id} approved!")
                        st.rerun()

            with act_col2:
                if claim.status != "rejected":
                    with st.expander("❌ Reject Claim"):
                        rej_reason = st.text_input("Rejection Reason", key=f"rej_r_{claim.id}", placeholder="e.g. Hallucinated number")
                        if st.button("Confirm Reject", key=f"rej_btn_{claim.id}"):
                            if rej_reason.strip():
                                service.reject_claim(claim.id, reviewer="human_operator", reason=rej_reason.strip())
                                st.warning(f"Claim {claim.id} rejected.")
                                st.rerun()
                            else:
                                st.error("Reason is mandatory to reject.")

            with act_col3:
                with st.expander("✏️ Override Grade / Entity Match / Edit"):
                    # Edit text
                    new_text = st.text_area("Edit Assertion Text", value=claim.text, key=f"edit_txt_{claim.id}")
                    col_g, col_em = st.columns(2)
                    new_grade = col_g.selectbox("Override Grade", ["strong", "moderate", "weak", "vendor_claim", "anecdote"], index=["strong", "moderate", "weak", "vendor_claim", "anecdote"].index(claim.grade), key=f"og_{claim.id}")
                    new_em = col_em.selectbox("Entity Match", ["exact", "family", "topic_level", "mismatch"], index=["exact", "family", "topic_level", "mismatch"].index(claim.entity_match), key=f"oem_{claim.id}")
                    edit_reason = st.text_input("Reason for Override", key=f"ed_r_{claim.id}", placeholder="Required for grade/match change")
                    if st.button("Save Changes", key=f"save_btn_{claim.id}"):
                        if new_text != claim.text:
                            service.edit_claim(claim.id, new_text=new_text, new_excerpt=None, reviewer="human_operator", reason=edit_reason or "Edited assertion text")
                        if new_grade != claim.grade:
                            if not edit_reason.strip():
                                st.error("Reason is required when overriding grade.")
                                st.stop()
                            service.change_claim_grade(claim.id, new_grade=new_grade, reason=edit_reason.strip(), reviewer="human_operator")
                        if new_em != claim.entity_match:
                            if not edit_reason.strip():
                                st.error("Reason is required when overriding entity match.")
                                st.stop()
                            service.change_claim_entity_match(claim.id, new_entity_match=new_em, reason=edit_reason.strip(), reviewer="human_operator")
                        st.success("Claim updated!")
                        st.rerun()

            st.markdown("---")
