"""S29a: one step per page. Which steps are open, where to go next, and the stepper at the top of every page."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

STEPS = (("ask", "Ask"), ("scope", "Scope"), ("run", "Sources & run"),
         ("brief", "Brief"), ("evidence", "Evidence"), ("checks", "Checks & share"))
STEP_KEYS = [k for k, _ in STEPS]
STEP_LABELS = dict(STEPS)
RESULT_STEPS = ("brief", "evidence", "checks")


def available_steps(has_proposal: bool, approved: bool, has_results: bool, has_job: bool = False) -> List[str]:
    """Scope needs a proposal, Sources & run an approval (or a run already started), results need results."""
    if has_results:
        return list(STEP_KEYS)
    out = ["ask"]
    if has_proposal or approved or has_job:
        out.append("scope")
    if approved or has_job:
        out.append("run")
    return out


def resolve_step(requested: Optional[str], available: List[str]) -> str:
    """The requested step if open; otherwise Brief when results exist, else the furthest open step."""
    if requested in available:
        return str(requested)
    return "brief" if "brief" in available else available[-1]


def next_step(current: str, available: List[str]) -> Optional[str]:
    i = STEP_KEYS.index(current) + 1
    return STEP_KEYS[i] if i < len(STEP_KEYS) and STEP_KEYS[i] in available else None


def prev_step(current: str, available: List[str]) -> Optional[str]:
    i = STEP_KEYS.index(current) - 1
    return STEP_KEYS[i] if i >= 0 and STEP_KEYS[i] in available else None


def stepper_items(current: str, available: List[str]) -> List[Dict[str, str]]:
    """Each step's label and state: current, done (before the current one), open (reachable) or locked."""
    cur = STEP_KEYS.index(current)
    items = []
    for i, (key, label) in enumerate(STEPS):
        if key == current:
            state = "current"
        elif key not in available:
            state = "locked"
        else:
            state = "done" if i < cur else "open"
        mark = " ✓" if state == "done" else ""
        items.append({"key": key, "label": f"{i + 1} {label}{mark}", "state": state})
    return items


def go_to(step: str) -> None:
    """Move to a step (used as a button callback, and by the auto-advance hooks); the URL keeps it for reloads."""
    st.session_state["page"] = step
    st.query_params["step"] = step


# On a phone Streamlit stacks columns one per line; the stepper wraps three to a row instead.
_STEPPER_CSS = """<style>
@media (max-width: 640px) {
  .st-key-stepper [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: wrap !important; gap: 0.35rem !important; }
  .st-key-stepper [data-testid="stColumn"] { flex: 1 1 30% !important; min-width: 30% !important; width: 30% !important; }
  .st-key-stepper button { padding: 0.25rem 0.3rem !important; min-height: 2.2rem !important; }
  .st-key-stepper button p { font-size: 0.78rem !important; }
}
</style>"""


def render_stepper(current: str, available: List[str]) -> None:
    st.markdown(_STEPPER_CSS, unsafe_allow_html=True)
    with st.container(key="stepper"):
        cols = st.columns(len(STEPS))
        for col, item in zip(cols, stepper_items(current, available)):
            with col:
                st.button(item["label"], key=f"stepper_{item['key']}", use_container_width=True,
                          type="primary" if item["state"] == "current" else "secondary",
                          disabled=item["state"] == "locked", on_click=go_to, args=(item["key"],))


def render_nav(current: str, available: List[str]) -> None:
    """Back and Next at the end of every page."""
    back, nxt = prev_step(current, available), next_step(current, available)
    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    c1, _, c2 = st.columns([1.4, 3, 1.8])
    with c1:
        if back:
            st.button(f"← Back: {STEP_LABELS[back]}", key="nav_back", use_container_width=True, on_click=go_to, args=(back,))
    with c2:
        if nxt:
            st.button(f"Next: {STEP_LABELS[nxt]} →", key="nav_next", use_container_width=True, on_click=go_to, args=(nxt,))


_SCROLL_TOP = """<script>
function toTop() {
  const d = window.parent.document;
  for (const sel of ['[data-testid="stMain"]', '[data-testid="stAppViewContainer"]']) {
    const el = d.querySelector(sel); if (el) { el.scrollTop = 0; }
  }
  window.parent.scrollTo(0, 0);
}
toTop(); [150, 400, 900].forEach(ms => setTimeout(toTop, ms));
</script>"""


def scroll_to_top_on_change(page: str) -> None:
    """A new step starts at the top of the page (Streamlit keeps the old scroll position on a rerun)."""
    if st.session_state.get("_shown_page") != page:
        st.session_state["_shown_page"] = page
        import streamlit.components.v1 as components

        # The step name makes each page's frame different, so the browser loads it (and runs the script) again.
        components.html(_SCROLL_TOP.replace("<script>", f"<script>/* {page} */", 1), height=0)


def page_from_state(state: Any, query_params: Any, available: List[str]) -> str:
    """The step to show: the session's (set by go_to), else the URL's, checked against what is open."""
    page = resolve_step(state.get("page") or query_params.get("step"), available)
    state["page"] = page
    if query_params.get("step") != page:
        query_params["step"] = page
    return page
