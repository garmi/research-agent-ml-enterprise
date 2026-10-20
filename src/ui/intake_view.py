"""Three-step intake view for Research Engine (Slice S2 Reasoned Question).

Replaces fixed static framings with a model-guided reasoning step:
  Step 1: Ask (user enters rough text + optional angle hint, button "Reason about my question")
  Step 2: Propose & Refine (editable fields, changes & reasons, coverage map, re-reason with feedback, approve)
  Step 3: Run (locked until approved; changes after approval clear approval and lock Run)
"""

from __future__ import annotations

import hashlib

import streamlit as st
from typing import Any, Callable, Dict, List, Optional

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
    resolve_model_name,
    split_user_sentences,
    validate_reasoned_package,
)
from src.ui.feedback_review import QUICK_ADJUSTMENTS, compose_feedback, feedback_prompt, proposal_diff, review_feedback
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


PROPOSAL_FIELD_KEYS = (
    "input_s2_refined_question",
    "input_s2_sub_questions",
    "input_s2_premises",
    "input_s2_in_scope",
    "input_s2_out_scope",
)


def _load_proposal(pkg: Dict[str, Any]) -> None:
    """Make `pkg` the active proposal. A keyed widget keeps its stored value and ignores a new
    value=, so the edit fields' stored values are dropped and rebuilt from the new proposal."""
    for k in PROPOSAL_FIELD_KEYS:
        st.session_state.pop(k, None)
    st.session_state["s2_active_package"] = pkg
    st.session_state["_last_approved_id"] = None
    st.session_state["_last_approved_package_sha256"] = None


def effective_provider(selected: str, has_gemini_key: bool, ollama_ok: bool) -> str:
    """The engine that will really run: Gemini without a key falls back to Ollama, then the stub."""
    p = str(selected or "").strip().lower()
    if p == "gemini" and not has_gemini_key:
        return "ollama" if ollama_ok else "stub"
    return p or ("ollama" if ollama_ok else "stub")


def approval_blockers(package: Dict[str, Any], raw_user_text: str = "") -> List[str]:
    """Schema and findings-guard errors that make an (edited) package unfit to approve."""
    _, errors = validate_reasoned_package(package, raw_user_text)
    return [e for e in errors if e.startswith(("Schema error", "Findings guard"))]


def approved_question_text(package: Optional[Dict[str, Any]], results: Optional[Dict[str, Any]]) -> str:
    """The question a re-draft must run: the approved refined question, never the raw input box text.

    `current_question` holds whatever is typed in Step 1, so using it after approval makes Gate 1
    look up the wrong question id and refuse the re-draft.
    """
    if package and package.get("refined_question"):
        return str(package["refined_question"])
    return str((results or {}).get("strategic_question") or "")


def render_intake_view(before_run: Optional[Callable[[], None]] = None) -> Dict[str, Any]:
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
                    _load_proposal(pkg)
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

        # Feedback & Re-reasoning (S15): quick adjustments plus free text, each a numbered point that is
        # checked by rule against the new proposal after re-reasoning.
        st.markdown("---")
        st.markdown("##### Adjust the proposal (optional)")
        adjustments = st.multiselect("Quick adjustments", list(QUICK_ADJUSTMENTS), key="ms_s2_quick_adjustments")
        adj_col1, adj_col2 = st.columns(2)
        with adj_col1:
            add_sub_question = st.text_input("Add a sub-question about:", key="input_s2_add_sub_question",
                                             placeholder="e.g. code review delays")
        with adj_col2:
            drop_terms = st.text_input("Drop these terms:", key="input_s2_drop_terms",
                                       placeholder="e.g. throughput, velocity")
        feed_col1, feed_col2 = st.columns([3.5, 1.5])
        with feed_col1:
            user_feedback = st.text_input(
                "Other feedback for the model:",
                placeholder="e.g. Focus more on code review bottlenecks and defect detection.",
                key="input_s2_user_feedback",
            )
        with feed_col2:
            st.markdown("<div style='height: 1.85rem;'></div>", unsafe_allow_html=True)
            rereason_clicked = st.button("🔄 Re-reason with feedback", key="btn_rereason_feedback", use_container_width=True)

        if rereason_clicked:
            points = compose_feedback(adjustments, add_sub_question, drop_terms, user_feedback)
            if not points:
                st.warning("Choose an adjustment or write feedback above.")
            else:
                try:
                    with st.spinner("Re-reasoning with your feedback..."):
                        v2_pkg = reason_question(
                            user_text=st.session_state.get("s2_raw_text", clean_text),
                            angle_hint=angle_hint,
                            provider=active_provider,
                            feedback=feedback_prompt(points),
                            previous_package=current_package,
                        )
                    proposals_history.append(v2_pkg)
                    st.session_state["s2_proposals"] = proposals_history
                    st.session_state["s2_feedback_review"] = {
                        "for_version": len(proposals_history),
                        "rows": review_feedback(points, current_package, v2_pkg),
                        "diff": proposal_diff(current_package, v2_pkg),
                    }
                    _load_proposal(v2_pkg)
                    st.rerun()
                except Exception as exc:
                    st.session_state["s2_feedback_review"] = {
                        "for_version": len(proposals_history),
                        "rows": review_feedback(points, current_package, None, blocked_reason=str(exc)),
                        "diff": None,
                    }
                    st.error(f"Re-reasoning error: {exc}")

        review = st.session_state.get("s2_feedback_review")
        if review and review.get("for_version") == len(proposals_history):
            with st.expander("What your feedback changed", expanded=True):
                st.dataframe([{"Your feedback": r["point"], "Result": r["result"], "What changed": r["what_changed"]}
                              for r in review["rows"]], hide_index=True, use_container_width=True)
                d = review.get("diff")
                if d:
                    if d["question_changed"]:
                        st.markdown(f"**Question before:** {d['question_before']}")
                        st.markdown(f"**Question after:** {d['question_after']}")
                    else:
                        st.caption("The question itself did not change.")
                    for label, key in (("Sub-questions added", "sub_questions_added"), ("Sub-questions removed", "sub_questions_removed"),
                                       ("Added to out of scope", "out_of_scope_added"), ("Added to in scope", "in_scope_added")):
                        if d.get(key):
                            st.markdown(f"**{label}:**\n" + "\n".join(f"- {x}" for x in d[key]))

        # Unlisted terms confirmation check
        raw_user_input = st.session_state.get("s2_raw_text", clean_text)
        unlisted_terms = find_unlisted_terms(current_package, raw_user_input)
        terms_confirmed = True
        if unlisted_terms:
            terms_str = ", ".join(f"'{t}'" for t in unlisted_terms)
            st.warning(f"⚠️ **Model-introduced terms:** The proposal introduces terms not present in your input: {terms_str}")
            terms_confirmed = st.checkbox(
                f"I acknowledge and confirm these terms introduced by the model: {terms_str}",
                # Scoped to this exact set of terms, so a confirmation never carries over to new terms.
                key="chk_confirm_unlisted_terms_" + hashlib.sha256(terms_str.encode("utf-8")).hexdigest()[:12],
            )

        # Approval button
        q_id = resolve_question_id(current_package["refined_question"])
        curr_pkg_hash = compute_package_sha256(current_package)
        last_approved_hash = st.session_state.get("_last_approved_package_sha256")

        blockers = approval_blockers(current_package, raw_user_input)
        for b in blockers:
            st.error(b.replace("Schema error: ", "Fix before approving: "))

        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
        approve_disabled = not terms_confirmed or bool(blockers)
        if st.button("✅ Approve this reasoned question", key="btn_approve_reasoned_package", type="primary", disabled=approve_disabled):
            prompt_hash = get_prompt_file_hash()
            save_gate1_approval(
                question_id=q_id,
                raw_user_text=st.session_state.get("s2_raw_text", clean_text),
                proposals=proposals_history,
                final_package=current_package,
                provider=active_provider,
                model_name=resolve_model_name(active_provider),
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

    # S18: anything the page puts before the last step (the Gate 1 question register).
    if before_run is not None:
        before_run()

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
                "⚡ Fast (~1-2 min • 12 checked, up to 5 papers used)",
                "🔬 Deep (~4-8 min • 30 checked, up to 15 papers used)",
            ],
            index=1,  # S11: Deep by default; Fast for a quick look
            key="select_research_depth",
            help="Check A judges every candidate paper, then the best on-topic ones by venue and relevance are used. Either depth widens the search once if too few papers are on topic.",
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
