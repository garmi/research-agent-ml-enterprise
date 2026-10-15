"""Three-step intake view for Research Engine (Slice S1 Task 5).

Renders:
  Step 1: Ask (user enters question / problem text under Strategic Technology Question)
  Step 2: Choose a framing (fixed lenses: Empirical effect, Adoption and practice, Risks and controls, Costs and trade-offs)
  Step 3: Run (Run button disabled until approved, disabled if text edited post-approval)
"""

from __future__ import annotations

import streamlit as st
from typing import Any, Dict

from src.engine.ids import (
    resolve_question_id,
    compute_question_sha256,
)
from src.engine.framings import generate_framings
from src.engine.approvals import (
    get_latest_gate1_approval,
    save_gate1_approval,
)


def render_intake_view() -> Dict[str, Any]:
    """Render the 3-step numbered intake UI in Streamlit."""
    st.markdown(
        """
        <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 1.15rem 1.4rem; margin-bottom: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                <div style="font-weight: 700; font-size: 1.05rem; color: #0F172A; display: flex; align-items: center; gap: 0.5rem;">
                    <span>🤖 Strategic Question Formulation Agent</span>
                </div>
                <span style="font-size: 0.74rem; background: #EEF2FF; color: #4338CA; padding: 0.2rem 0.65rem; border-radius: 9999px; font-weight: 700; letter-spacing: 0.03em;">
                    Gate 1 Intake & Framing
                </span>
            </div>
            <div style="font-size: 0.86rem; color: #64748B; margin-bottom: 0.2rem; line-height: 1.45;">
                State your enterprise dilemma. Follow the three steps below to ground your inquiry before synthesis.
                Execution requires explicit Gate 1 problem framing approval.
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

    col_q, col_formulate = st.columns([4.0, 1.0])
    with col_q:
        question_text = st.text_area(
            "Strategic Technology Question",
            value=initial_question,
            placeholder="e.g. What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?",
            key="input_user_question",
            height=85,
            help="Type any enterprise engineering, AI platform, or DevSecOps inquiry for multi-source peer-reviewed literature synthesis.",
        )
    with col_formulate:
        st.markdown("<div style='height: 1.85rem;'></div>", unsafe_allow_html=True)
        st.button("Formulate Question", key="btn_formulate_question", type="secondary", use_container_width=True)

    clean_text = (question_text or "").strip()
    question_id = resolve_question_id(clean_text) if clean_text else ""
    st.session_state["current_question"] = clean_text

    # --------------------------------------------------------------------------
    # Step 2: Choose a framing
    # --------------------------------------------------------------------------
    st.markdown("### 2. Choose a framing")

    if clean_text:
        st.markdown(f"**Verbatim Question:** {clean_text}")
        framings = generate_framings(clean_text)

        framing_titles = [f"{i+1}. {f.title}" for i, f in enumerate(framings)]
        selected_idx = st.radio(
            "Select proposed lens:",
            options=list(range(len(framings))),
            format_func=lambda idx: framing_titles[idx],
            key="radio_framing_select",
        )

        selected_framing = framings[selected_idx]

        # Display lens card with fixed template fields
        st.markdown(
            f"""
            <div style="background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px; padding: 0.85rem 1rem; margin: 0.5rem 0;">
                <div style="font-weight: 700; color: #1E3A8A; font-size: 0.9rem; margin-bottom: 0.35rem;">
                    Lens: {selected_framing.title}
                </div>
                <div style="font-size: 0.82rem; color: #334155; margin-bottom: 0.35rem;">
                    <strong>Focus:</strong> {selected_framing.focus}
                </div>
                <div style="font-size: 0.82rem; color: #334155; margin-bottom: 0.35rem;">
                    <strong>Counts as Evidence:</strong> {selected_framing.counts_as_evidence}
                </div>
                <div style="font-size: 0.82rem; color: #64748B;">
                    <strong>Out of Scope:</strong> {selected_framing.out_of_scope}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Approve this framing", key="btn_approve_framing", type="secondary"):
            save_gate1_approval(
                question_id=question_id,
                question_text=clean_text,
                framing_id=selected_framing.id,
                framing_title=selected_framing.title,
                framing_question=clean_text,
            )
            st.session_state["_last_approved_id"] = question_id
            st.session_state["_last_approved_sha256"] = compute_question_sha256(clean_text)
            st.success(f"✓ Approved Gate 1 problem framing for '{question_id}'! Step 3 is unlocked.")
    else:
        st.info("ℹ️ Enter your question in Step 1 to inspect candidate framings.")

    # --------------------------------------------------------------------------
    # Step 3: Run
    # --------------------------------------------------------------------------
    st.markdown("### 3. Run")

    run_disabled = True
    disabled_reason = ""

    if not clean_text:
        disabled_reason = "Please enter a research topic in Step 1."
    else:
        latest_approval = get_latest_gate1_approval(question_id)
        last_approved_sha256 = st.session_state.get("_last_approved_sha256")
        current_sha256 = compute_question_sha256(clean_text)

        if last_approved_sha256 and current_sha256 != last_approved_sha256:
            disabled_reason = "You changed the question after approving a framing. Approve a framing again to continue."
        elif latest_approval is None:
            disabled_reason = "You must choose and approve a problem framing in Step 2 before running."
        elif current_sha256 != latest_approval.question_sha256:
            disabled_reason = "You changed the question after approving a framing. Approve a framing again to continue."
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

    if disabled_reason:
        st.warning(f"⚠️ {disabled_reason}")

    run_submitted = st.button(
        "🚀 Run Research",
        key="btn_run_research",
        type="primary",
        disabled=run_disabled,
        use_container_width=True,
    )

    return {
        "question_id": question_id,
        "question_text": clean_text,
        "run_disabled": run_disabled,
        "run_submitted": run_submitted,
        "depth": depth_option,
        "tone": tone_option,
    }
