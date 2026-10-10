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


def render_gap_matrix_view(service: LedgerService) -> None:
    """Render View 4: Gap Matrix (Gate 4)."""
    st.header("🔍 Gate 4: Strategic Gap Matrix")
    st.markdown(
        "Cross-lane analysis per question across Academic, Enterprise, and Field evidence. "
        "Strategic value lies in surfacing gaps: **Outcome 2** (Practice w/o Evidence), **Outcome 3** (Evidence w/o Practice), and **Outcome 4** (Unmeasured)."
    )

    from src.gaps.matrix_builder import GapMatrixBuilder
    builder = GapMatrixBuilder(db_path=service.db_path)
    questions = service.repo.list_questions()

    if not questions:
        st.info("No questions in register.")
        return

    selected_q_id = st.selectbox("Select Question for Gap Evaluation", [q.id for q in questions])
    if st.button("Evaluate Lane Evidence & Generate Gap Matrix"):
        entry = builder.evaluate_question_lanes(selected_q_id)
        st.success(f"Evaluated lanes for {selected_q_id}: Assigned Outcome {entry.outcome}!")

    entries = builder.list_matrix_entries(question_id=selected_q_id)
    if entries:
        current = entries[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Academic Lane", current.academic_state.upper())
        c2.metric("Enterprise Lane", current.enterprise_state.upper())
        c3.metric("Field Lane", current.field_state.upper())
        c4.metric("Strategic Outcome", f"Outcome {current.outcome}")

        outcome_names = {
            1: "1: Supported (Academic + Enterprise Aligned)",
            2: "2: Practice Without Evidence (Enterprise Active, Academic Void)",
            3: "3: Evidence Without Practice (Academic Proven, Enterprise Unmeasured)",
            4: "4: Unmeasured (Thin/Zero Evidence Across All Lanes)",
        }
        st.info(f"**Classification:** {outcome_names.get(current.outcome, 'Unknown')}\n\n**Strategic Rationale:** {current.rationale}")
    else:
        st.info("Click 'Evaluate Lane Evidence' above to compute the current Gap Matrix.")


def render_draft_review_view(service: LedgerService) -> None:
    """Render View 5: Draft Review (Gate 5)."""
    st.header("📝 Gate 5: Evidence-Grounded Draft Review")
    st.markdown(
        "Sentence-level verification against Hard Gates G1 through G6. "
        "Engine drafts from approved claims only; human adds practitioner opinion/field notes."
    )

    from src.synth.generator import SynthesisEngine
    synth = SynthesisEngine(db_path=service.db_path)
    questions = service.repo.list_questions()

    col_q, col_gen = st.columns([3, 1])
    target_q_id = col_q.selectbox("Select Target Question", [q.id for q in questions], key="draft_q_sel")

    human_opinion = st.text_area(
        "Practitioner Field Perspective (Human-Only Stance)",
        placeholder="Enter your first-person perspective or operational delivery insights...",
    )

    if col_gen.button("Draft Field Note", type="primary"):
        doc, sentences, summary = synth.build_field_note(
            question_id=target_q_id,
            human_view=human_opinion,
        )
        st.session_state["active_draft_doc"] = doc
        st.session_state["active_draft_sentences"] = sentences
        st.session_state["active_draft_summary"] = summary
        st.success("Draft generated and checked against Hard Gates!")

    if "active_draft_summary" in st.session_state:
        summary = st.session_state["active_draft_summary"]
        doc = st.session_state["active_draft_doc"]
        sentences = st.session_state["active_draft_sentences"]

        st.markdown("---")
        st.subheader("Sentence-Level Gate Check")
        gates = summary["gate_results"]["gates"]

        badge_status = "🟢 PASS" if summary["gate_results"]["passed"] else "🔴 BLOCKED"
        st.markdown(f"**Gate Status:** {badge_status}")

        for s in sentences:
            if s.type == "heading":
                st.markdown(f"#### {s.text}")
            elif s.type == "opinion":
                st.markdown(f"👤 *[Human Opinion]* {s.text}")
            else:
                cid_str = f" `[{', '.join(s.claim_ids_json or [])}]`" if s.claim_ids_json else " :red[*(Uncited)*]"
                st.markdown(f"- {s.text}{cid_str}")


def render_publish_gate_view(service: LedgerService) -> None:
    """Render View 6: Publish Gate (Gate 6)."""
    st.header("🚀 Gate 6: Publish Gate & Scorecard")
    st.markdown(
        "Final publish verification. An output CANNOT reach `published` unless every gate is complete, "
        "denylist scan is clean, and quality score meets the publication band."
    )

    if "active_draft_summary" in st.session_state:
        summary = st.session_state["active_draft_summary"]
        score = summary["score_results"]
        gate_res = summary["gate_results"]

        col1, col2, col3 = st.columns(3)
        col1.metric("Composite Score", f"{score['total_score']} / 100")
        col2.metric("Publish Band", score["band"])
        col3.metric("Hard Gate Status", "PASS" if gate_res["passed"] else "BLOCKED")

        st.markdown("---")
        st.subheader("Component Breakdown (S1 - S7)")
        c_df = pd.DataFrame([
            {"Component": k, "Score": v} for k, v in score["components"].items()
        ])
        st.dataframe(c_df, use_container_width=True)

        st.subheader("Top Recommended Improvements")
        for imp in score.get("top_3_improvements", []):
            st.warning(f"💡 {imp}")

        st.markdown("---")
        if gate_res["passed"] and score["band"] == "PUBLISH_READY":
            if st.button("🌟 Final Sign-Off & Publish to Repository", type="primary"):
                st.balloons()
                st.success("Output published successfully! Audit record logged.")
        else:
            st.error("Publication is strictly BLOCKED until all hard gate violations are resolved and score meets band.")
    else:
        st.info("Draft a document in Gate 5 to review the Publish Scorecard.")


def render_runs_and_scores_view(service: LedgerService) -> None:
    """Render View 8: Runs and Scores History."""
    st.header("📊 View 8: Execution Runs, Audit Trail & Scores")
    st.markdown("Immutable record of system runs, gate audits, and quality score history.")

    with service.repo._conn() as conn:
        reviews_cursor = conn.execute("SELECT * FROM reviews ORDER BY ts DESC LIMIT 20;")
        reviews = [dict(row) for row in reviews_cursor.fetchall()]

    if reviews:
        st.subheader("Recent Human Gate Reviews")
        st.dataframe(pd.DataFrame(reviews), use_container_width=True)
    else:
        st.info("No reviews recorded yet.")

