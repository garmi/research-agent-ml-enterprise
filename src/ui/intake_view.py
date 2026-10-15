"""Three-step intake view for Research Engine (Slice S1 Round 3).

Renders:
  Banner: "Frame your question"
  Step 1: Ask (user enters question, button "Show framings")
  Step 2: Choose a framing (fixed lenses: Empirical effect, Adoption and practice, Risks and controls, Costs and trade-offs)
  Step 3: Run (disabled reason directly above Run button in neutral info box, Run button enabled once approved)
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
from src.ui.theme import (
    COLOR_BG_CARD,
    COLOR_BG_SURFACE,
    COLOR_BORDER,
    COLOR_BORDER_STRONG,
    COLOR_DISABLED_BTN_BG,
    COLOR_DISABLED_BTN_TEXT,
    COLOR_PRIMARY,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_FAMILY,
    FONT_SIZE_BASE,
    FONT_SIZE_LG,
    FONT_SIZE_SM,
    FONT_SIZE_XL,
    FONT_SIZE_XS,
    SPACING_MD,
    SPACING_SM,
    SPACING_XS,
)
from src.ui.components import disabled_reason, info_box


def render_intake_view() -> Dict[str, Any]:
    """Render the polished 3-step numbered intake UI in Streamlit."""
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

    col_q, col_formulate = st.columns([4.0, 1.0])
    with col_q:
        question_text = st.text_area(
            "Strategic Technology Question",
            value=initial_question,
            placeholder="e.g. What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?",
            key="input_user_question",
            height=85,
            help="Type your question for multi-source peer-reviewed literature synthesis.",
        )
    with col_formulate:
        st.markdown("<div style='height: 1.85rem;'></div>", unsafe_allow_html=True)
        st.button("Show framings", key="btn_formulate_question", type="secondary", use_container_width=True)

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
            <div style="background: {COLOR_BG_SURFACE}; border: 1px solid {COLOR_BORDER_STRONG}; border-radius: 8px; padding: 16px; margin: 0.5rem 0; font-family: {FONT_FAMILY};">
                <div style="font-weight: 700; color: {COLOR_PRIMARY}; font-size: {FONT_SIZE_SM}; margin-bottom: 0.35rem;">
                    Lens: {selected_framing.title}
                </div>
                <div style="font-size: {FONT_SIZE_SM}; color: {COLOR_TEXT_PRIMARY}; margin-bottom: 0.35rem;">
                    <strong>Focus:</strong> {selected_framing.focus}
                </div>
                <div style="font-size: {FONT_SIZE_SM}; color: {COLOR_TEXT_PRIMARY}; margin-bottom: 0.35rem;">
                    <strong>Counts as Evidence:</strong> {selected_framing.counts_as_evidence}
                </div>
                <div style="font-size: {FONT_SIZE_SM}; color: {COLOR_TEXT_MUTED};">
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
            st.success("Framing approved. You can now run the research.")
    else:
        st.markdown(info_box("Type a question in Step 1 to inspect candidate angles."), unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # Step 3: Run
    # --------------------------------------------------------------------------
    st.markdown("### 3. Run")

    run_disabled = True
    disabled_msg = ""

    if not clean_text:
        disabled_msg = "Type a question in Step 1."
    else:
        latest_approval = get_latest_gate1_approval(question_id)
        last_approved_sha256 = st.session_state.get("_last_approved_sha256")
        current_sha256 = compute_question_sha256(clean_text)

        if last_approved_sha256 and current_sha256 != last_approved_sha256:
            disabled_msg = "You changed the question after approving. Approve a framing again."
        elif latest_approval is None:
            disabled_msg = "Approve a framing in Step 2 to unlock Run."
        elif current_sha256 != latest_approval.question_sha256:
            disabled_msg = "You changed the question after approving. Approve a framing again."
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

    return {
        "question_id": question_id,
        "question_text": clean_text,
        "run_disabled": run_disabled,
        "run_submitted": run_submitted,
        "depth": depth_option,
        "tone": tone_option,
    }
