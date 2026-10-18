"""Three-step intake view for Research Engine (Slice S2 Reasoned Question).

Replaces fixed static framings with a model-guided reasoning step:
  Step 1: Ask (user enters rough text + optional angle hint, button "Reason about my question")
  Step 2: Propose & Refine (editable fields, changes & reasons, coverage map, re-reason with feedback, approve)
  Step 3: Run (locked until approved; changes after approval clear approval and lock Run)
"""

from __future__ import annotations

import streamlit as st
from typing import Any, Dict, List, Optional

from src.engine.ids import (
    resolve_question_id,
    compute_question_sha256,
)
from src.engine.approvals import (
    get_latest_gate1_approval,
    save_gate1_approval,
    is_package_approved,
)
from src.engine.reasoner import (
    QuestionReasoningError,
    compute_package_sha256,
    find_unlisted_terms,
    get_prompt_file_hash,
    reason_question,
    split_user_sentences,
)
from src.ui.theme import (
    COLOR_BG_CARD,
    COLOR_BG_SURFACE,
    COLOR_BORDER,
    COLOR_BORDER_STRONG,
    COLOR_PRIMARY,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_FAMILY,
    FONT_SIZE_BASE,
    FONT_SIZE_LG,
    FONT_SIZE_SM,
    FONT_SIZE_XS,
)
from src.ui.components import disabled_reason, info_box


def render_s2_proposal_card_text(pkg: Dict[str, Any]) -> str:
    """Render a clean text view of the proposal for display and test inspection without leaking paths."""
    refined = pkg.get("refined_question", "")
    sub_qs = "\n".join(f"- {sq}" for sq in pkg.get("sub_questions", []))
    premises = "\n".join(f"- {p}" for p in pkg.get("premises_to_test", []))
    scope = ", ".join(pkg.get("in_scope", []))
    return f"Refined Question:\n{refined}\n\nSub-Questions:\n{sub_qs}\n\nPremises:\n{premises}\n\nScope:\n{scope}"


def render_intake_view() -> Dict[str, Any]:
    """Render the polished 3-step numbered intake UI in Streamlit for Slice S2."""
    # Inject styling for disabled button state and clean layout
    st.markdown(
        f"""
        <style>
        button:disabled, button[disabled], button:disabled:hover, button:disabled:active {{
            background: #E2E8F0 !important;
            background-color: #E2E8F0 !important;
            background-image: none !important;
            color: #475569 !important;
            border: 1px solid #CBD5E1 !important;
            border-radius: 8px !important;
            cursor: not-allowed !important;
            opacity: 1 !important;
            box-shadow: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Header Banner: Calm, plain English, zero jargon
    st.markdown(
        f"""
        <div style="background: {COLOR_BG_CARD}; border: 1px solid {COLOR_BORDER}; border-radius: 12px; padding: 16px; margin-bottom: 1.25rem; font-family: {FONT_FAMILY}; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
            <div style="font-weight: 700; font-size: {FONT_SIZE_LG}; color: {COLOR_TEXT_PRIMARY}; margin-bottom: 0.25rem;">
                Frame your question
            </div>
            <div style="font-size: {FONT_SIZE_SM}; color: {COLOR_TEXT_SECONDARY}; line-height: 1.45;">
                Type your question, pick the angle you want researched, approve it, then run.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------------------------
    # Step 1: Ask
    # --------------------------------------------------------------------------
    st.markdown("### 1. Ask")
    initial_question = st.session_state.get("current_question", "")

    col_q, col_angle = st.columns([3.2, 1.8])
    with col_q:
        question_text = st.text_area(
            "Strategic Technology Question (Rough Input)",
            value=initial_question,
            placeholder="e.g. How does automated verification impact defect density and cycle time in distributed systems?",
            key="input_user_question",
            height=90,
            help="Type your question or rough thoughts. The reasoning step will structure it into a validated inquiry package.",
        )
    with col_angle:
        angle_options = [
            "Empirical effect (Measured outcomes & benchmarks)",
            "Adoption and practice (Workflows & change management)",
            "Risks and controls (Governance & vulnerabilities)",
            "Costs and trade-offs (ROI & technical debt)",
        ]
        angle_selected = st.selectbox(
            "Research Angle (Optional Hint)",
            options=angle_options,
            index=0,
            key="select_reasoning_angle",
            help="Provides an architectural angle hint to calibrate sub-questions.",
        )
        angle_hint = angle_selected.split(" (")[0]

    btn_col1, btn_col2 = st.columns([2.0, 3.0])
    with btn_col1:
        reason_clicked = st.button("🧠 Reason about my question", key="btn_reason_question", type="secondary", use_container_width=True)

    clean_text = (question_text or "").strip()
    st.session_state["current_question"] = clean_text

    # Resolve active model provider
    active_provider = st.session_state.get("selected_model_provider", "ollama")

    # Handle Reasoning Execution
    if reason_clicked:
        if not clean_text:
            st.warning("⚠️ Please type your question or notes above before reasoning.")
        else:
            try:
                with st.spinner("Analyzing and sharpening research inquiry..."):
                    pkg = reason_question(
                        user_text=clean_text,
                        angle_hint=angle_hint,
                        provider=active_provider,
                    )
                    st.session_state["s2_raw_text"] = clean_text
                    st.session_state["s2_proposals"] = [pkg]
                    st.session_state["s2_active_package"] = pkg
                    st.session_state["_last_approved_id"] = None
                    st.session_state["_last_approved_package_sha256"] = None
                    st.rerun()
            except QuestionReasoningError as q_err:
                st.error(f"**Reasoning Error:** {q_err}")
            except Exception as exc:
                st.error(f"**Unexpected Error:** {exc}")

    # --------------------------------------------------------------------------
    # Step 2: Review, Edit & Approve Reasoned Proposal
    # --------------------------------------------------------------------------
    st.markdown("### 2. Review and refine proposal")

    active_pkg = st.session_state.get("s2_active_package")
    proposals_history = st.session_state.get("s2_proposals", [])

    if active_pkg:
        from src.engine.stub_mode import is_stub_mode
        if is_stub_mode() or str(active_provider).lower() in ("stub", "mock", "fake"):
            st.warning("⚠️ Test mode - placeholder output, not real reasoning")

        version_num = len(proposals_history)
        st.caption(f"**Proposal Version {version_num}** • Review and adjust any field below prior to approval.")

        # Editable fields
        refined_input = st.text_input(
            "Refined Research Question (One neutral, answerable sentence):",
            value=active_pkg.get("refined_question", ""),
            key="input_s2_refined_question",
        )

        sub_qs_text = "\n".join(active_pkg.get("sub_questions", []))
        sub_qs_input = st.text_area(
            "Sub-Questions (3 to 5 questions, one per line):",
            value=sub_qs_text,
            key="input_s2_sub_questions",
            height=95,
        )

        premises_text = "\n".join(active_pkg.get("premises_to_test", []))
        premises_input = st.text_area(
            "Premises to Test (Assumptions in user text to evaluate, not assume true):",
            value=premises_text,
            key="input_s2_premises",
            height=70,
        )

        scope_col1, scope_col2 = st.columns(2)
        with scope_col1:
            in_scope_text = "\n".join(active_pkg.get("in_scope", [])) if isinstance(active_pkg.get("in_scope"), list) else str(active_pkg.get("in_scope", ""))
            in_scope_input = st.text_area("In Scope:", value=in_scope_text, key="input_s2_in_scope", height=65)
        with scope_col2:
            out_scope_text = "\n".join(active_pkg.get("out_of_scope", [])) if isinstance(active_pkg.get("out_of_scope"), list) else str(active_pkg.get("out_of_scope", ""))
            out_scope_input = st.text_area("Out of Scope:", value=out_scope_text, key="input_s2_out_scope", height=65)

        # Assemble current edited package
        edited_sub_qs = [q.strip() for q in sub_qs_input.splitlines() if q.strip()]
        edited_premises = [p.strip() for p in premises_input.splitlines() if p.strip()]
        edited_in_scope = [s.strip() for s in in_scope_input.splitlines() if s.strip()]
        edited_out_scope = [s.strip() for s in out_scope_input.splitlines() if s.strip()]

        current_package = dict(active_pkg)
        current_package["refined_question"] = refined_input.strip()
        current_package["sub_questions"] = edited_sub_qs
        current_package["premises_to_test"] = edited_premises
        current_package["in_scope"] = edited_in_scope
        current_package["out_of_scope"] = edited_out_scope

        # Added terms confirmation
        added_terms = active_pkg.get("added_terms", [])
        if added_terms:
            st.info(f"ℹ️ **Added Terms for Confirmation:** The model introduced new terms: **{', '.join(added_terms)}**. Please verify them above.")

        # Changes and Reasons & Coverage Map Expander
        with st.expander("🔍 View Changes, Reasons & 100% Sentence Coverage Map", expanded=False):
            st.markdown("##### Changes Made by Model & Rationale")
            changes = active_pkg.get("changes_and_reasons", [])
            for ch in changes:
                if isinstance(ch, dict):
                    st.markdown(f"- **{ch.get('change')}**: {ch.get('reason')}")
                else:
                    st.markdown(f"- {ch}")

            st.markdown("##### Sentence Coverage Map (100% accounted for)")
            cov_map = active_pkg.get("coverage_map", {})
            for s, target in cov_map.items():
                st.markdown(f"- `\"{s}\"` ➔ **{target}**")

        # Feedback & Re-reasoning
        st.markdown("---")
        feed_col1, feed_col2 = st.columns([3.5, 1.5])
        with feed_col1:
            user_feedback = st.text_input(
                "Feedback for Model (Optional adjustment):",
                placeholder="e.g. Focus more on code review bottlenecks and defect detection.",
                key="input_s2_user_feedback",
            )
        with feed_col2:
            st.markdown("<div style='height: 1.85rem;'></div>", unsafe_allow_html=True)
            rereason_clicked = st.button("🔄 Re-reason with feedback", key="btn_rereason_feedback", use_container_width=True)

        if rereason_clicked:
            if not user_feedback.strip():
                st.warning("Please enter your adjustment feedback above.")
            else:
                try:
                    with st.spinner("Re-reasoning with your feedback..."):
                        v2_pkg = reason_question(
                            user_text=st.session_state.get("s2_raw_text", clean_text),
                            angle_hint=angle_hint,
                            provider=active_provider,
                            feedback=user_feedback.strip(),
                            previous_package=current_package,
                        )
                        proposals_history.append(v2_pkg)
                        st.session_state["s2_proposals"] = proposals_history
                        st.session_state["s2_active_package"] = v2_pkg
                        st.session_state["_last_approved_id"] = None
                        st.session_state["_last_approved_package_sha256"] = None
                        st.rerun()
                except Exception as exc:
                    st.error(f"Re-reasoning error: {exc}")

        # Unlisted terms confirmation check
        raw_user_input = st.session_state.get("s2_raw_text", clean_text)
        unlisted_terms = find_unlisted_terms(current_package, raw_user_input)
        terms_confirmed = True
        if unlisted_terms:
            terms_str = ", ".join(f"'{t}'" for t in unlisted_terms)
            st.warning(f"⚠️ **Model-introduced terms:** The proposal introduces terms not present in your input: {terms_str}")
            terms_confirmed = st.checkbox(
                f"I acknowledge and confirm these terms introduced by the model: {terms_str}",
                key="chk_confirm_unlisted_terms",
            )

        # Approval button
        q_id = resolve_question_id(current_package["refined_question"])
        curr_pkg_hash = compute_package_sha256(current_package)
        last_approved_hash = st.session_state.get("_last_approved_package_sha256")

        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
        approve_disabled = not terms_confirmed
        if st.button("✅ Approve this reasoned question", key="btn_approve_reasoned_package", type="primary", disabled=approve_disabled):
            prompt_hash = get_prompt_file_hash()
            save_gate1_approval(
                question_id=q_id,
                raw_user_text=st.session_state.get("s2_raw_text", clean_text),
                proposals=proposals_history,
                final_package=current_package,
                provider=active_provider,
                model_name=active_provider,
                prompt_file_hash=prompt_hash,
            )
            st.session_state["_last_approved_id"] = q_id
            st.session_state["_last_approved_package_sha256"] = curr_pkg_hash
            st.session_state["s2_active_package"] = current_package

        if not terms_confirmed:
            st.caption("ℹ️ Please tick the confirmation checkbox above to acknowledge terms introduced by the model and unlock approval.")

        if st.session_state.get("_last_approved_package_sha256") == curr_pkg_hash:
            st.success("Reasoned question approved. You can now run the research.")

    else:
        st.markdown(info_box("Type your question in Step 1 and click Reason about my question to inspect proposals."), unsafe_allow_html=True)
        current_package = None

    # --------------------------------------------------------------------------
    # Step 3: Run
    # --------------------------------------------------------------------------
    st.markdown("### 3. Run")

    run_disabled = True
    disabled_msg = ""

    if not clean_text:
        disabled_msg = "Type a question in Step 1."
    elif not active_pkg:
        disabled_msg = "Click Reason about my question and approve a proposal in Step 2 to unlock Run."
    else:
        q_id = resolve_question_id(current_package["refined_question"])
        curr_pkg_hash = compute_package_sha256(current_package)
        last_approved_hash = st.session_state.get("_last_approved_package_sha256")
        latest_approval = get_latest_gate1_approval(q_id)

        if not last_approved_hash:
            disabled_msg = "Approve the reasoned proposal in Step 2 to unlock Run."
        elif curr_pkg_hash != last_approved_hash:
            disabled_msg = "You changed the proposal after approving. Approve again to unlock Run."
        elif latest_approval is None:
            disabled_msg = "Approve the reasoned proposal in Step 2 to unlock Run."
        else:
            run_disabled = False

    col_depth, col_tone = st.columns(2)
    with col_depth:
        depth_option = st.selectbox(
            "Research Depth",
            options=[
                "⚡ Fast (~45s • 2 rounds • up to 10 sources)",
                "🔬 Deep (~3-5m • 5 rounds • comprehensive synthesis)",
            ],
            index=0,
            key="select_research_depth",
            help="Fast provides an immediate executive brief; Deep executes multi-round citation graph queries.",
        )
    with col_tone:
        tone_option = st.selectbox(
            "Strategic Tone",
            options=[
                "Executive (ROI & Risk)",
                "Architectural (Technical Depth)",
                "Market & Industry (Macro Trends)",
            ],
            index=0,
            key="select_strategic_tone",
            help="Calibrates the framing, metric focus, and audience persona for executive deliverables.",
        )

    # Disabled reason sits directly above the Run button in one neutral info box
    if disabled_msg:
        st.markdown(disabled_reason(disabled_msg), unsafe_allow_html=True)

    run_submitted = st.button(
        "🚀 Run Research",
        key="btn_run_research",
        type="primary",
        disabled=run_disabled,
        use_container_width=True,
    )

    resolved_q_id = resolve_question_id(current_package["refined_question"]) if current_package else ""
    resolved_q_text = current_package["refined_question"] if current_package else clean_text

    return {
        "question_id": resolved_q_id,
        "question_text": resolved_q_text,
        "reasoned_package": current_package,
        "run_disabled": run_disabled,
        "run_submitted": run_submitted,
        "depth": depth_option,
        "tone": tone_option,
    }
