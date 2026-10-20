"""Light / dark page theme (S18).

The page's design system is light (CSS variables plus many inline colours). Dark mode is a stylesheet
added after it: it redefines the CSS variables and recolours Streamlit's page, sidebar, inputs, tabs
and expanders, and the custom cards. Data grids (st.dataframe) draw on a canvas and keep their own
light theme.
"""

from __future__ import annotations

from typing import Any, Mapping

THEMES = ("light", "dark")

_DARK = """
<style>
:root {
    --surface-bg: #0B1220; --card-bg: #111A2E; --border-subtle: #24324A; --border-hover: #33445F;
    --text-primary: #E2E8F0; --text-secondary: #CBD5E1; --text-muted: #94A3B8;
    --status-success-bg: #0F2A22; --status-warning-bg: #2A2110;
}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stBottomBlockContainer"] {
    background: #0B1220 !important; color: #E2E8F0 !important;
}
[data-testid="stSidebar"], [data-testid="stSidebar"] > div { background: #0F172A !important; }
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp p, .stApp li, .stApp label, .stApp span,
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"], [data-testid="stWidgetLabel"] {
    color: #E2E8F0 !important;
}
[data-testid="stCaptionContainer"] { color: #94A3B8 !important; }
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div, [data-baseweb="base-input"],
.stApp input, .stApp textarea {
    background: #111A2E !important; color: #E2E8F0 !important; border-color: #33445F !important;
}
[data-baseweb="popover"] li, [data-baseweb="menu"] { background: #111A2E !important; color: #E2E8F0 !important; }
[data-baseweb="tab"] { color: #CBD5E1 !important; background: transparent !important; }
[data-baseweb="tab"][aria-selected="true"] { color: #93C5FD !important; }
[data-testid="stExpander"] details, [data-testid="stExpander"] summary {
    background: #111A2E !important; border-color: #24324A !important; color: #E2E8F0 !important;
}
[data-testid="stBaseButton-secondary"] { background: #1E293B !important; color: #E2E8F0 !important; border-color: #33445F !important; }
.stApp table, .stApp th, .stApp td { background: #111A2E !important; color: #E2E8F0 !important; border-color: #24324A !important; }
.studio-header, .verdict-banner, .paper-card, .finding-card, .step-rail, .sidebar-pod, .stat-tile, .signal-card,
.roadmap-item, .risk-item, .stepper-container {
    background: #111A2E !important; border-color: #24324A !important; color: #E2E8F0 !important;
}
.paper-card-title a, .roadmap-action, .step-label, .studio-header h1 { color: #F1F5F9 !important; }
.paper-tag { background: #1E293B !important; color: #CBD5E1 !important; }
.run-status { filter: brightness(0.9); }
.conf-badge { background: #1E293B !important; color: #CBD5E1 !important; }
.conf-high { background: #0F2A22 !important; color: #6EE7B7 !important; }
.conf-moderate { background: #2A2110 !important; color: #FCD34D !important; }
.conf-low { background: #2A1215 !important; color: #FCA5A5 !important; }
.line-tag { color: #94A3B8 !important; }
/* Inline light backgrounds and dark text written directly into card HTML. Browsers keep inline colours
   as rgb(...), so both spellings are matched. */
[style*="background: #FFFFFF"], [style*="background:#FFFFFF"], [style*="background: white"],
[style*="background: #F8FAFC"], [style*="background: #F1F5F9"],
[style*="background: rgb(255, 255, 255)"], [style*="background: rgb(248, 250, 252)"],
[style*="background: rgb(241, 245, 249)"] { background: #111A2E !important; }
[style*="border: 1px solid rgb(226, 232, 240)"], [style*="border: 1px solid #E2E8F0"] { border-color: #24324A !important; }
[style*="color: #0F172A"], [style*="color: #1E293B"], [style*="color: #334155"],
[style*="color: rgb(15, 23, 42)"], [style*="color: rgb(30, 41, 59)"], [style*="color: rgb(51, 65, 85)"] { color: #E2E8F0 !important; }
[style*="color: #475569"], [style*="color: #64748B"],
[style*="color: rgb(71, 85, 105)"], [style*="color: rgb(100, 116, 139)"] { color: #94A3B8 !important; }
</style>
"""


def theme_from_query(params: Mapping[str, Any]) -> str:
    """The theme named in the URL (?theme=dark), else light."""
    value = str((params or {}).get("theme") or "").lower()
    return value if value in THEMES else "light"


def theme_css(theme: str) -> str:
    """The stylesheet to add for a theme; light is the page's own design, so it adds nothing."""
    return _DARK if theme == "dark" else ""
