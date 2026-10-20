from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Sanitize dynamic linker search paths to prevent macOS libiconv collisions
for _var in ("DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH"):
    if _var in os.environ and "conda" in os.environ[_var].lower():
        os.environ.pop(_var, None)

# Sanitize and strip whitespace on model and API keys
if os.getenv("GEMINI_MODEL"):
    os.environ["GEMINI_MODEL"] = os.getenv("GEMINI_MODEL", "").strip()
if os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "").strip()

from dotenv import load_dotenv
import pandas as pd
import streamlit as st

from src.analysis.business_context import detect_focus_areas
from src.analysis.insight_builder import derive_business_signal, summarize_findings
from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.analysis.question_formulator import FormulatedQuestion, QuestionFormulationAgent
from src.analysis.relevance import rank_papers
from src.analysis.synthesizer import SynthesisEngine
from src.config import default_outputs_dir, ensure_directories, load_config
from src.fetchers.arxiv_client import ArxivClient
from src.fetchers.crossref_client import CrossrefClient
from src.fetchers.openalex_client import OpenAlexClient
from src.fetchers.semantic_scholar_client import SemanticScholarClient
from src.llm.factory import build_llm
from src.output.content_pack import ContentPackBuilder
from src.output.report_builder import ReportBuilder
from src.publish.export_policy import evaluate_export_permissions

from src.ledger.service import LedgerService
from src.ledger.ui_views import (
    render_question_register,
    render_venue_tiering,
    render_gap_matrix_view,
    render_practitioner_entry_view,
    render_safe_table,
)
from src.engine.entry import start_run
from src.engine.ids import resolve_question_id
from src.engine.stub_mode import is_stub_mode
from src.ui.safe_page import safe_page, format_error_payload, render_safe_error
from src.ui.evidence_view import evidence_map_html, finding_card_html, paper_card_html, render_sentence
from src.ui.intake_view import approved_question_text, effective_provider, render_intake_view
from src.ui.rerun import board_editor_key, export_view, papers_for_rerun
from src.ui.publish_view import gate_rows, gates_summary, publish_eligibility
from src.ui.run_status import run_status, status_banner_html, status_code, step_rail, step_rail_html
from src.ui.brief_view import (
    brief_meta_line, distinct_signals, plain_html, report_blocks, report_markdown, roadmap_html, stopped_run_markdown,
)
from src.ui.run_jobs import RunJobs
from src.ui.theme_mode import theme_css, theme_from_query
from src.llm.model_names import gemini_model_name


logger = logging.getLogger("ExecutiveResearchStudio")
logging.basicConfig(level=logging.INFO)

load_dotenv()
config = load_config("config.yaml") if Path("config.yaml").exists() else {}
ensure_directories()
ledger_service = LedgerService()
question_agent = QuestionFormulationAgent(config)
multilane_runner = MultiLaneResearchRunner()
is_cloud_run = bool(os.getenv("K_SERVICE"))

# --- BACKEND CONNECTIVITY PROBING ---

def is_ollama_reachable(timeout: float = 0.5) -> bool:
    """Fast check whether local Ollama server is responding."""
    try:
        url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
        req = urllib.request.Request(url, headers={"User-Agent": "ExecutiveResearchStudio/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_available_models() -> Dict[str, str]:
    """Map human-friendly model labels to internal provider identifiers."""
    options = {}
    has_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
    ollama_ok = is_ollama_reachable()

    # Local-first engines listed first
    if ollama_ok:
        options["Local Ollama Qwen 2.5 3B (Local Offline) [Active]"] = "ollama"
    options["Deterministic Offline Engine (Zero-API Fallback)"] = "stub"

    # Remote engines opt-in only
    if has_key:
        options[f"Google Gemini ({gemini_model_name()}) (Remote API — sends prompt out-of-boundary) [Configured]"] = "gemini"
    else:
        options[f"Google Gemini ({gemini_model_name()}) (Remote API — sends prompt out-of-boundary) [API Key Required]"] = "gemini"
    return options


def render_stub_banner_if_active() -> bool:
    """Render persistent red banner at top of page if stub mode is active."""
    if is_stub_mode():
        st.error("TEST MODE: synthetic data. Results are not real and cannot be published.")
        return True
    return False


# --- PAGE SETUP ---
st.set_page_config(
    page_title="AI Guruji",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- ENTERPRISE DESIGN SYSTEM STYLING ---
st.markdown(
    """
    <style>
    /* -------------------------------------------------------------
       AI GURUJI - DESIGN SYSTEM
       ------------------------------------------------------------- */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    :root {
        /* S18: Anthropic Sans where the viewer has it installed (it is not licensed for web serving), else Inter. */
        --font-main: 'Anthropic Sans', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        --font-mono: 'JetBrains Mono', monospace;
        --brand-primary: #1E3A8A;
        --brand-accent: #2563EB;
        --brand-accent-hover: #1D4ED8;
        --brand-gradient: linear-gradient(135deg, #1E3A8A 0%, #2563EB 50%, #4F46E5 100%);
        --surface-bg: #F8FAFC;
        --card-bg: #FFFFFF;
        --border-subtle: #E2E8F0;
        --border-hover: #CBD5E1;
        --text-primary: #0F172A;
        --text-secondary: #475569;
        --text-muted: #64748B;
        --status-success: #059669;
        --status-success-bg: #ECFDF5;
        --status-warning: #D97706;
        --status-warning-bg: #FFFBEB;
        --status-danger: #DC2626;
        --shadow-sm: 0 1px 2px 0 rgba(15, 23, 42, 0.05);
        --shadow-md: 0 4px 12px -2px rgba(15, 23, 42, 0.08), 0 2px 6px -1px rgba(15, 23, 42, 0.04);
        --shadow-lg: 0 10px 25px -5px rgba(15, 23, 42, 0.08), 0 8px 10px -6px rgba(15, 23, 42, 0.04);
    }

    html, body, [class*="css"] {
        font-family: var(--font-main) !important;
        color: var(--text-primary);
        letter-spacing: -0.01em;
    }

    /* Main container clean padding */
    .block-container {
        padding-top: 1.75rem !important;
        padding-bottom: 4rem !important;
        max-width: 1200px !important;
    }
    
    .studio-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        margin-bottom: 1.25rem;
        padding-bottom: 1.25rem;
        border-bottom: 1px solid var(--border-subtle);
    }

    .studio-title-group h1 {
        font-family: var(--font-main);
        font-weight: 800;
        font-size: 2.15rem;
        letter-spacing: -0.03em;
        color: #0F172A;
        margin: 0 0 0.35rem 0;
        display: flex;
        align-items: center;
        gap: 0.65rem;
    }

    .studio-title-group p {
        font-size: 0.98rem;
        color: var(--text-secondary);
        margin: 0;
        line-height: 1.5;
    }

    .meta-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        background: #F1F5F9;
        border: 1px solid #E2E8F0;
        border-radius: 9999px;
        padding: 0.35rem 0.85rem;
        font-size: 0.78rem;
        font-weight: 600;
        color: #334155;
        letter-spacing: 0.02em;
    }

    .pulse-dot {
        width: 7px;
        height: 7px;
        background-color: #10B981;
        border-radius: 50%;
        box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
        animation: pulse-green 2s infinite;
    }

    @keyframes pulse-green {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    .research-console-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 1.5rem;
        box-shadow: var(--shadow-md);
        margin-bottom: 1.75rem;
    }

    .topic-chip-label {
        font-size: 0.82rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--text-muted);
        margin-bottom: 0.5rem;
    }

    /* Topic button custom refinements: single-line ellipsis */
    div[data-testid="column"] button[kind="secondary"] {
        border-radius: 9px !important;
        border: 1px solid #E2E8F0 !important;
        background-color: #FFFFFF !important;
        color: #334155 !important;
        font-weight: 500 !important;
        font-size: 0.84rem !important;
        padding: 0.45rem 0.75rem !important;
        transition: all 0.15s ease-in-out !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    div[data-testid="column"] button[kind="secondary"]:hover {
        border-color: #93C5FD !important;
        background-color: #F8FAFC !important;
        color: #1D4ED8 !important;
        transform: translateY(-1px);
    }

    /* Primary Launch Button - Enabled (Single Blue Primary Button) */
    button[kind="primary"]:not(:disabled) {
        background: #2563EB !important;
        background-color: #2563EB !important;
        background-image: none !important;
        color: #FFFFFF !important;
        border: 1px solid #1D4ED8 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em !important;
        font-size: 0.95rem !important;
        padding: 0.65rem 1.4rem !important;
        box-shadow: 0 1px 3px rgba(37, 99, 235, 0.2) !important;
        transition: all 0.15s ease !important;
        cursor: pointer !important;
    }

    button[kind="primary"]:not(:disabled):hover {
        background: #1D4ED8 !important;
        background-color: #1D4ED8 !important;
        background-image: none !important;
        box-shadow: 0 2px 6px rgba(29, 78, 216, 0.3) !important;
        transform: translateY(-1px) !important;
    }

    /* Disabled Button: flat grey background, grey text with readable contrast, NO gradient */
    button:disabled,
    button[disabled],
    button[kind="primary"]:disabled,
    button[kind="secondary"]:disabled,
    button[disabled]:hover,
    button[disabled]:active {
        background: #E2E8F0 !important;
        background-color: #E2E8F0 !important;
        background-image: none !important;
        color: #475569 !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 8px !important;
        box-shadow: none !important;
        cursor: not-allowed !important;
        transform: none !important;
        opacity: 1 !important;
    }

    .verdict-banner {
        background: linear-gradient(180deg, #F0FDF4 0%, #F8FAFC 100%);
        border: 1px solid #BBF7D0;
        border-left: 5px solid #16A34A;
        border-radius: 10px;
        padding: 1.15rem 1.35rem;
        margin-bottom: 1.75rem;
    }

    .verdict-banner-title {
        font-weight: 700;
        font-size: 0.88rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #166534;
        margin-bottom: 0.35rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .verdict-banner-body {
        font-size: 1.05rem;
        line-height: 1.55;
        font-weight: 500;
        color: #0F172A;
        margin: 0;
    }

    .section-title {
        font-size: 1.15rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: #0F172A;
        margin: 1.5rem 0 0.85rem 0;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    /* Key Signal Cards */
    .signal-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.15rem;
        height: 100%;
        box-shadow: var(--shadow-sm);
        transition: border-color 0.2s ease;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }

    .signal-card:hover {
        border-color: #93C5FD;
        box-shadow: var(--shadow-md);
    }

    .signal-tag {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #2563EB;
        background: #EFF6FF;
        border-radius: 6px;
        padding: 0.2rem 0.55rem;
        display: inline-block;
        margin-bottom: 0.75rem;
        width: fit-content;
    }

    .signal-text {
        font-size: 0.92rem;
        font-weight: 500;
        line-height: 1.5;
        color: #1E293B;
        margin: 0;
    }

    .stat-tile {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.1rem 1.25rem;
        box-shadow: var(--shadow-sm);
        text-align: left;
    }

    .stat-label {
        font-size: 0.76rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #64748B;
        margin-bottom: 0.35rem;
    }

    .stat-value {
        font-size: 1.7rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        color: #0F172A;
        line-height: 1.1;
    }

    .stat-sub {
        font-size: 0.78rem;
        color: #059669;
        font-weight: 600;
        margin-top: 0.35rem;
    }

    .cite-pill {
        display: inline-flex;
        align-items: center;
        background: #EFF6FF;
        color: #1D4ED8;
        font-family: var(--font-mono);
        font-size: 0.78rem;
        font-weight: 600;
        padding: 0.08rem 0.38rem;
        border-radius: 4px;
        border: 1px solid #DBEAFE;
        text-decoration: none !important;
        cursor: pointer;
    }
    .cite-pill:hover {
        background: #DBEAFE;
        color: #1E40AF;
    }

    /* Empirical Findings and Risk Cards */
    .finding-item {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-left: 4px solid #3B82F6;
        border-radius: 8px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 0.75rem;
        font-size: 0.92rem;
        line-height: 1.5;
        color: #1E293B;
    }

    .risk-item {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-left: 4px solid #E11D48;
        border-radius: 8px;
        padding: 0.9rem 1.1rem;
        margin-bottom: 0.75rem;
        font-size: 0.92rem;
        line-height: 1.5;
        color: #1E293B;
    }

    div[data-baseweb="tab-list"] {
        gap: 0.35rem !important;
        border-bottom: 2px solid #E2E8F0 !important;
        padding-bottom: 0.25rem !important;
        margin-top: 1.5rem !important;
        margin-bottom: 1.5rem !important;
    }

    button[data-baseweb="tab"] {
        border-radius: 8px 8px 0 0 !important;
        padding: 0.65rem 1.1rem !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        color: #64748B !important;
        transition: all 0.15s ease !important;
    }

    button[data-baseweb="tab"][aria-selected="true"] {
        color: #1D4ED8 !important;
        border-bottom: 3px solid #2563EB !important;
        background: #EFF6FF !important;
    }

    .export-box {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 1.25rem 1.5rem;
        margin-top: 2rem;
    }

    .export-title {
        font-size: 0.95rem;
        font-weight: 700;
        color: #0F172A;
        margin-bottom: 0.3rem;
        display: flex;
        align-items: center;
        gap: 0.45rem;
    }

    .export-subtitle {
        font-size: 0.82rem;
        color: #64748B;
        margin-bottom: 1rem;
    }

    /* Sidebar Status Pod */
    .sidebar-pod {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 0.9rem 1rem;
        margin-bottom: 1rem;
    }

    .sidebar-pod-title {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #64748B;
        margin-bottom: 0.65rem;
    }

    .status-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.35rem 0;
        font-size: 0.84rem;
        color: #334155;
    }

    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        font-size: 0.76rem;
        font-weight: 600;
        color: #059669;
        background: #ECFDF5;
        padding: 0.15rem 0.5rem;
        border-radius: 9999px;
    }

    .status-dot-sm {
        width: 6px;
        height: 6px;
        background-color: #10B981;
        border-radius: 50%;
    }

    /* Modern Progress Stepper styling */
    .stepper-container {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1.5rem;
        box-shadow: var(--shadow-sm);
    }
    
    .stepper-status-text {
        font-size: 0.9rem;
        font-weight: 600;
        color: #1E293B;
        margin-bottom: 0.6rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .workflow-banner {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 0.85rem 1.1rem;
        margin-bottom: 1.25rem;
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.45rem;
        font-size: 0.8rem;
        font-weight: 600;
    }

    .workflow-step-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: #FFFFFF;
        border: 1px solid #CBD5E1;
        border-radius: 6px;
        padding: 0.25rem 0.6rem;
        color: #334155;
    }

    .workflow-step-pill.active {
        background: #EFF6FF;
        border-color: #3B82F6;
        color: #1D4ED8;
        font-weight: 700;
    }

    .lane-badge-a {
        background: #EFF6FF;
        color: #1D4ED8;
        border: 1px solid #BFDBFE;
        border-radius: 6px;
        padding: 0.25rem 0.55rem;
        font-size: 0.78rem;
        font-weight: 700;
    }

    .lane-badge-b {
        background: #F5F3FF;
        color: #6D28D9;
        border: 1px solid #DDD6FE;
        border-radius: 6px;
        padding: 0.25rem 0.55rem;
        font-size: 0.78rem;
        font-weight: 700;
    }

    .lane-badge-c {
        background: #ECFDF5;
        color: #047857;
        border: 1px solid #A7F3D0;
        border-radius: 6px;
        padding: 0.25rem 0.55rem;
        font-size: 0.78rem;
        font-weight: 700;
    }

    /* Hide Streamlit footer & deploy elements */
    .stDeployButton, footer, #MainMenu {
        visibility: hidden !important;
        display: none !important;
    }
    /* S8: run status banner, step rail, brief */
    .run-status { border-radius: 10px; padding: 0.8rem 1rem; margin: 0.75rem 0 1.1rem 0; font-size: 0.9rem; }
    .run-status-head { font-weight: 800; font-size: 1rem; }
    .run-status-why { margin: 0.35rem 0 0.25rem 1.1rem; padding: 0; font-size: 0.84rem; }
    .run-status-next { margin-top: 0.35rem; font-size: 0.86rem; }
    .step-rail { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 0.4rem 0.7rem; margin-bottom: 1rem; }
    .step-row { display: flex; gap: 0.55rem; align-items: flex-start; padding: 0.4rem 0; border-bottom: 1px solid #F1F5F9; }
    .step-row:last-child { border-bottom: none; }
    .step-icon { font-weight: 800; width: 1rem; text-align: center; }
    .step-label { font-weight: 700; font-size: 0.82rem; color: #0F172A; }
    .step-pending .step-label { color: #94A3B8; font-weight: 600; }
    .step-detail { font-size: 0.72rem; color: #64748B; }
    .brief-meta { font-size: 0.82rem; color: #475569; margin: 0.25rem 0 1rem 0; }
    .signal-list { margin: 0 0 1rem 1.1rem; padding: 0; font-size: 0.92rem; line-height: 1.5; }
    .roadmap-note { font-size: 0.78rem; color: #64748B; margin-bottom: 0.4rem; }
    .roadmap-item { display: flex; gap: 0.8rem; align-items: flex-start; background: white; border: 1px solid #E2E8F0; border-radius: 10px; padding: 0.75rem 1rem; margin-bottom: 0.5rem; }
    .roadmap-phase { background: #1E3A8A; color: white; border-radius: 6px; padding: 0.25rem 0.55rem; font-size: 0.74rem; font-weight: 700; white-space: nowrap; }
    .roadmap-action { font-weight: 700; font-size: 0.9rem; color: #0F172A; }
    .roadmap-impact { font-size: 0.8rem; color: #059669; font-weight: 600; margin-top: 0.1rem; }
    .paper-card { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 0.75rem; }
    .paper-card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.35rem; }
    .paper-tag { font-size: 0.76rem; background: #F1F5F9; color: #475569; padding: 0.15rem 0.55rem; border-radius: 4px; font-weight: 600; margin-left: 0.4rem; }
    .paper-custom { background: #DBEAFE; color: #1E40AF; }
    .paper-card-title { font-size: 0.98rem; font-weight: 700; margin-bottom: 0.25rem; }
    .paper-card-title a { color: #0F172A; text-decoration: none; }
    .paper-card-meta { font-size: 0.84rem; color: #64748B; overflow-wrap: anywhere; }
    .report-answer { background: var(--card-bg); border: 1px solid var(--border-subtle); border-left: 4px solid #2563EB; border-radius: 0; padding: 0.9rem 1.1rem; margin-bottom: 0.6rem; }
    .report-answer-head, .report-section-head { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center; justify-content: space-between; }
    .report-answer p { font-size: 1.02rem; line-height: 1.65; margin: 0.4rem 0 0 0; }
    .report-section { margin: 1.4rem 0 0.6rem 0; }
    .report-diagram { background: var(--card-bg); border: 1px solid var(--border-subtle); padding: 0.8rem 1rem; margin: 0.4rem 0 1rem 0; overflow-x: auto; }
    .report-diagram h3 { font-size: 1.02rem; margin: 0 0 0.3rem 0; }
    .report-section-head h3, .report-answer h3, .report-h { font-size: 1.08rem !important; margin: 0.2rem 0 !important; }
    .report-section-head { margin-top: 1.2rem; }
    .conf-badge { font-size: 0.74rem; font-weight: 600; padding: 0.2rem 0.6rem; border-radius: 6px; background: #F1F5F9; color: #475569; }
    .conf-high { background: #ECFDF5; color: #065F46; } .conf-moderate { background: #FFFBEB; color: #92400E; } .conf-low { background: #FEF2F2; color: #991B1B; }
    .sy-line, .ev-line { border-left: 3px solid #93C5FD; border-radius: 0; padding: 0.15rem 0 0.15rem 0.7rem; margin: 0.45rem 0; font-size: 0.95rem; line-height: 1.6; }
    .ev-line { border-left-color: #CBD5E1; }
    .line-tag { font-size: 0.7rem; color: #64748B; font-weight: 600; margin-right: 0.4rem; text-transform: none; }
    .ev-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; margin: 0.6rem 0 0.2rem 0; }
    .ev-table th, .ev-table td { border-bottom: 1px solid var(--border-subtle); padding: 0.35rem 0.4rem; text-align: left; vertical-align: top; }
    .report-list { margin: 0.2rem 0 0.8rem 1.1rem; font-size: 0.93rem; line-height: 1.6; }
    .report-empty { color: #64748B; font-size: 0.9rem; }
    .roadmap-phase-head { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: center; margin: 0.8rem 0 0.4rem 0; }
    .roadmap-basis { font-size: 0.78rem; color: #1E40AF; font-weight: 600; margin-top: 0.15rem; }
    .roadmap-flag { font-size: 0.78rem; color: #B45309; font-weight: 600; margin-top: 0.15rem; }

    /* S8: phone width. Streamlit stacks st.columns by itself; these cover the custom HTML. */
    @media (max-width: 640px) {
        .block-container { padding: 1rem 0.75rem 2rem 0.75rem !important; }
        .studio-header { flex-direction: column; align-items: flex-start !important; gap: 0.5rem; }
        .studio-header h1 { font-size: 1.35rem !important; }
        .meta-badge { display: none !important; }
        .verdict-banner { padding: 0.9rem !important; }
        .verdict-banner > div:first-child { flex-direction: column; align-items: flex-start !important; gap: 0.4rem; }
        .run-status { padding: 0.7rem 0.8rem; }
        .roadmap-item { flex-direction: column; gap: 0.4rem; }
        div[data-baseweb="tab-list"] { overflow-x: auto; flex-wrap: nowrap; }
        div[data-baseweb="tab-list"] button { white-space: nowrap; }
        table { display: block; overflow-x: auto; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- SESSION STATE INITIALIZATION ---
if "current_question" not in st.session_state:
    st.session_state["current_question"] = ""

if "raw_problem_input" not in st.session_state:
    st.session_state["raw_problem_input"] = ""

if "formulated_question_obj" not in st.session_state:
    st.session_state["formulated_question_obj"] = None

if "research_results" not in st.session_state:
    st.session_state["research_results"] = None


if "is_running" not in st.session_state:
    st.session_state["is_running"] = False

if "custom_acad_urls" not in st.session_state:
    st.session_state["custom_acad_urls"] = ""

if "custom_ent_urls" not in st.session_state:
    st.session_state["custom_ent_urls"] = ""

if "custom_prac_urls" not in st.session_state:
    st.session_state["custom_prac_urls"] = ""


# --- CITATION FORMATTER ---
def format_citation_pills(text: str, paper_map: Dict[str, Any]) -> str:
    """Escape model/source text, then format [P1], [P2] tags into citation pills (http(s) links only)."""
    return render_sentence(text, paper_map)


# --- ERROR DIAGNOSTICS FORMATTER ---
def format_user_friendly_error(exc: Exception) -> Dict[str, str]:
    """Translate raw technical exceptions into clean executive diagnostics."""
    err_str = str(exc)
    logger.error("Research pipeline error: %s", exc, exc_info=True)

    if "400" in err_str or "INVALID_ARGUMENT" in err_str:
        return {
            "title": "Model Configuration Error",
            "what_happened": "The language model service rejected the configuration or model name parameters.",
            "what_completed": "Academic literature search and deduplication completed.",
            "next_steps": "Check model settings in Advanced Settings, or verify your API key.",
        }
    if "API_KEY" in err_str or "unauthorized" in err_str.lower() or "403" in err_str:
        return {
            "title": "API Authentication Required",
            "what_happened": "Could not authenticate with the language model provider.",
            "what_completed": "Literature discovery retrieved papers from open academic repositories.",
            "next_steps": "Provide a temporary Gemini API key in Advanced Settings above to complete synthesis.",
        }
    if "Zero papers" in err_str or isinstance(exc, ConnectionError):
        return {
            "title": "No Matching Academic Literature Found",
            "what_happened": "Academic repositories (arXiv, OpenAlex, Crossref, Semantic Scholar) returned no matching papers.",
            "what_completed": "Topic query expansion generated search terms.",
            "next_steps": "Try broadening your topic query or focusing on general technical domain terms.",
        }
    return {
        "title": "Research Synthesis Interrupted",
        "what_happened": "An unexpected error occurred during paper extraction or report assembly.",
        "what_completed": "Literature discovery completed.",
        "next_steps": "Verify your model backend in Advanced Settings or run with 'Fast' depth.",
    }


def _generate_mock_papers(topic: str) -> List[Dict[str, Any]]:
    """Generate high-quality reproducible mock academic papers for stub/offline mode."""
    return [
        {
            "id": "p-empirical-01",
            "title": f"Empirical Evaluation of {topic} in Financial Software Delivery",
            "abstract": "Controlled experiment with 80 developers demonstrates that specification-driven test suites reduce hallucinated bugs by 42% while improving velocity by 25%.",
            "year": 2024,
            "venue": "ICSE",
            "url": "https://doi.org/10.1145/example1",
            "relevance_score": 0.95,
        },
        {
            "id": "p-arch-02",
            "title": f"Architectural Drift and Governance in Enterprise Agent Workflows: {topic}",
            "abstract": "We study agentic code generation across 50 production repositories. The study finds that without automated contracts, architectural consistency degrades over time.",
            "year": 2024,
            "venue": "IEEE Software",
            "url": "https://doi.org/10.1109/example2",
            "relevance_score": 0.90,
        },
        {
            "id": "p-sec-03",
            "title": f"Security Posture and Vulnerability Injection in Modern Agent Swarms: {topic}",
            "abstract": "Analysis of 12,000 generated pull requests reveals that unverified LLM suggestions introduce package hallucination in 14% of dependencies unless scanned by deterministic policies.",
            "year": 2024,
            "venue": "ACM CCS",
            "url": "https://doi.org/10.1145/example3",
            "relevance_score": 0.88,
        },
    ]


# --- PRODUCTION PIPELINE EXECUTOR (8-STAGE MULTI-LANE WORKFLOW) ---
def run_production_pipeline(
    topic: str,
    depth: str,
    tone: str,
    map_provider: str,
    reduce_provider: str,
    progress_box: Any = None,
    papers_override: Optional[List[Dict[str, Any]]] = None,
    custom_lane_urls: Optional[Dict[str, List[str]]] = None,
    allow_remote_practitioner_synthesis: bool = False,
    practitioner_abstraction_confirmed: bool = False,
    reasoned_package: Optional[Dict[str, Any]] = None,
    excluded_claim_keys: Optional[List[str]] = None,
    on_progress: Optional[Callable[[int, str, float], None]] = None,
) -> Dict[str, Any]:
    """Execute the formal 8-stage research engine workflow across Academic, Enterprise, and Practitioner lanes.
    In a background job (S9) progress goes to on_progress; it must not touch Streamlit."""
    stage_titles = {
        1: "Stage 1/8: Question Register (Gate 1 - YAML + SQLite Sync)",
        2: "Stage 2/8: Three-Lane Evidence Harvesting (Lanes A, B, C)",
        3: "Stage 3/8: Atomic Claim Extraction & Normalization",
        4: "Stage 4/8: Evidence Ledger Persistence & Deterministic Grading",
        5: "Stage 5/8: Strategic Gap Matrix Evaluation (Gate 4)",
        6: "Stage 6/8: Ledger-Only Claim-Driven Synthesis",
        7: "Stage 7/8: Deterministic Governance Audit (Gates G1–G6 & S1–S7)",
        8: "Stage 8/8: Publish Gate Verification & Versioned Deliverables",
    }

    def box_progress(stage_idx: int, stage_msg: str, progress_val: float):
        stage_label = stage_titles.get(stage_idx, f"Stage {stage_idx}/8")
        progress_box.markdown(
            f"""
            <div class="stepper-container">
                <div class="stepper-status-text">
                    <span style="display:inline-block; animation: spin 1s linear infinite;">🔄</span>
                    <strong>{stage_label}:</strong> {stage_msg}
                </div>
            </div>
            <style>
            @keyframes spin {{ 100% {{ transform: rotate(360deg); }} }}
            </style>
            """,
            unsafe_allow_html=True,
        )
        progress_box.progress(progress_val)

    q_id = resolve_question_id(topic)
    results = start_run(
        question_id=q_id,
        question_text=topic,
        depth=depth,
        tone=tone,
        map_provider=map_provider,
        reduce_provider=reduce_provider,
        on_progress=on_progress or box_progress,
        academic_papers_override=papers_override,
        custom_lane_urls=custom_lane_urls,
        allow_remote_practitioner_synthesis=allow_remote_practitioner_synthesis,
        practitioner_abstraction_confirmed=practitioner_abstraction_confirmed,
        reasoned_package=reasoned_package,
        excluded_claim_keys=excluded_claim_keys,
    )
    if progress_box is not None:
        progress_box.empty()
    return results


@st.cache_resource
def get_run_jobs(base_dir: str) -> RunJobs:
    """One job registry per server process (shared by all sessions), keyed by its directory."""
    return RunJobs(base_dir, error_formatter=format_user_friendly_error)


# S18: on Cloud Run, point RESEARCH_RUNS_DIR at a mounted Cloud Storage volume so runs survive a redeploy.
run_jobs = get_run_jobs(os.getenv("RESEARCH_RUNS_DIR") or str(Path(default_outputs_dir()) / "runs"))


def launch_run_job(meta: Dict[str, Any], **pipeline_kwargs: Any) -> None:
    """Run the pipeline as a background job (S9) so it outlives this browser session, keep the
    job id in the URL so a reconnect or reload picks it up, then rerun to show its progress."""
    job_id = run_jobs.start(
        lambda on_progress: run_production_pipeline(on_progress=on_progress, **pipeline_kwargs), meta=meta
    )
    st.query_params["run"] = job_id
    st.session_state["loaded_job"] = None
    st.rerun()


def resume_run_from_url() -> Optional[Dict[str, Any]]:
    """Load the run named in the URL into this session once it has finished; return the job."""
    job = run_jobs.get(st.query_params.get("run"))
    if job and job["state"] == "done" and st.session_state.get("loaded_job") != job["job_id"]:
        st.session_state["research_results"] = job["results"]
        st.session_state["loaded_job"] = job["job_id"]
        st.session_state["current_question"] = job["meta"].get("topic", "")
        if job["meta"].get("last_lane_urls") is not None:
            st.session_state["last_lane_urls"] = job["meta"]["last_lane_urls"]
    return job


@st.fragment(run_every=2)
def render_job_progress(job_id: str) -> None:
    """Live progress for a background run; reruns the page when the run finishes."""
    job = run_jobs.get(job_id)
    if not job:
        return
    if job["state"] != "running":
        st.rerun(scope="app")
    st.info(
        f"⏳ **Research is running** (stage {job.get('stage') or 0} of 8): {job.get('message', '')}\n\n"
        "You can keep this page open. If the connection drops, reload the page: the run carries on and its result appears here."
    )
    st.progress(min(max(float(job.get("progress") or 0.0), 0.0), 1.0))


# ==============================================================================
# SIDEBAR: PHASE WORKFLOW TRACKER & ITERATIVE FEEDBACK LOOPS
# ==============================================================================
available_models = get_available_models()
has_gemini_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
ollama_online = is_ollama_reachable()
current_job = resume_run_from_url()
results = st.session_state.get("research_results")


with st.sidebar:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 0.65rem; margin-bottom: 1rem;">
            <div style="background: linear-gradient(135deg, #2563EB, #1E40AF); color: white; width: 34px; height: 34px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 1.15rem; font-weight: bold; box-shadow: 0 2px 6px rgba(37,99,235,0.3);">
                🔬
            </div>
            <div>
                <div style="font-weight: 800; font-size: 1rem; color: #0F172A; line-height: 1.1;">AI Guruji</div>
                <div style="font-size: 0.74rem; font-weight: 600; color: #64748B; letter-spacing: 0.04em;">EVIDENCE-BACKED RESEARCH</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 1. STEPS: where this run is, the same states the status banner reports (S8)
    st.markdown('<div class="sidebar-pod-title">Steps</div>', unsafe_allow_html=True)
    st.markdown(step_rail_html(step_rail(results)), unsafe_allow_html=True)

    # 2. SYSTEM STATUS POD
    st.markdown(
        f"""
        <div class="sidebar-pod">
            <div class="sidebar-pod-title">System Status</div>
            <div class="status-row">
                <span>Gemini Cloud API</span>
                <span class="status-badge"><span class="status-dot-sm"></span>{'Configured' if has_gemini_key else 'Missing'}</span>
            </div>
            <div class="status-row">
                <span>Local Ollama</span>
                <span class="status-badge" style="background: {'#ECFDF5' if ollama_online else '#F1F5F9'}; color: {'#059669' if ollama_online else '#64748B'};">
                    <span class="status-dot-sm" style="background-color: {'#10B981' if ollama_online else '#94A3B8'};"></span>{'Online' if ollama_online else 'Offline'}
                </span>
            </div>
            <div style="margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid #F1F5F9; font-size: 0.72rem; color: #64748B;">
                Active Engine: <strong style="color: #334155;">{'Test mode (synthetic data)' if is_stub_mode() else ('Local Ollama' if ollama_online else ('Gemini' if has_gemini_key else 'Offline Extractive Engine'))}</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 3. PREVIOUS RUNS: finished runs on this server, so they survive a new session (S9)
    st.markdown('<div class="sidebar-pod-title" style="margin-top: 1rem;">Previous Research Runs</div>', unsafe_allow_html=True)
    past_runs = run_jobs.recent(limit=8)
    if not past_runs:
        st.markdown(
            """
            <div style="font-size: 0.78rem; color: #94A3B8; background: #F8FAFC; border: 1px dashed #E2E8F0; border-radius: 8px; padding: 0.75rem; text-align: center;">
                No finished runs yet.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for item in past_runs:
            run_title = item["meta"].get("topic") or "Research Run"
            if len(run_title) > 36:
                run_title = run_title[:33] + "..."
            if st.button(f"📋 {run_title}", key=f"hist_{item['job_id']}", use_container_width=True):
                st.query_params["run"] = item["job_id"]
                st.session_state["loaded_job"] = None
                st.rerun()

    if st.session_state["research_results"] is not None:
        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
        if st.button("➕ Start new research", use_container_width=True):
            st.session_state["research_results"] = None
            st.session_state["current_question"] = ""
            st.session_state["loaded_job"] = None
            st.query_params.pop("run", None)
            st.rerun()


# ==============================================================================
# HEADER
# ==============================================================================
render_stub_banner_if_active()

st.markdown(
    """
    <div class="studio-header">
        <div class="studio-title-group">
            <h1>AI Guruji</h1>
            <p>Evidence-backed research briefs: every finding traced to its source, every claim checked before you publish.</p>
        </div>
        <div class="meta-badge">
            <span class="pulse-dot"></span>
            Academic, enterprise and field evidence
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# S18/S19b: light / dark page theme, kept in the URL (?theme=dark) so a reload keeps it. The switch sits
# under the header (not in the sidebar) so it can always be found and switched back.
_theme_col, _ = st.columns([1.2, 4.8])
with _theme_col:
    dark_on = st.toggle("🌙 Dark mode", value=theme_from_query(st.query_params) == "dark", key="ui_dark_mode")
if dark_on:
    st.query_params["theme"] = "dark"
elif "theme" in st.query_params:
    del st.query_params["theme"]
st.markdown(theme_css("dark" if dark_on else "light"), unsafe_allow_html=True)

if os.getenv("HOSTED_DEMO") == "1":
    st.info("🔒 **Demo: no private data is stored** • Hosted demonstration instance. API key overrides, practitioner observations, and persistent ledger writes are disabled.")

def _load_question(qid: str, text: str) -> None:
    """Load Question callback: runs before the rerun, so it can set the Step 1 box (a keyed widget)."""
    st.session_state["current_question"] = text
    st.session_state["input_user_question"] = text
    st.toast(f"Loaded {qid} into Step 1: {text[:80]}", icon="✅")


def render_question_register() -> None:
    """The Gate 1 question register, shown in the question step before Run (S18)."""
    with st.expander("📋 Browse Registered Inquiries (Gate 1 Question Register)", expanded=False):
        reg_questions = ledger_service.repo.list_questions()
        if not reg_questions:
            reg_questions = ledger_service.load_questions_from_yaml()
        if reg_questions:
            for q in reg_questions:
                q_col1, q_col2 = st.columns([4.2, 0.8])
                with q_col1:
                    st.markdown(f"**`{q.id}`** ({q.scope.upper()}) — {q.text}")
                with q_col2:
                    st.button("Load Question", key=f"load_q_{q.id}", use_container_width=True,
                              on_click=_load_question, args=(q.id, q.text))


# ==============================================================================
# PHASE 1: QUESTION FRAMING & SIMPLIFIED CONFIGURATION
# ==============================================================================
is_stub_requested = is_stub_mode()

# Once a run exists the question collapses to one line; open it to edit and run again.
show_intake_expanded = results is None

with st.expander(
    "1. Question"
    + (f": {st.session_state.get('current_question', '')[:75]}" if results else ": frame it and approve the scope"),
    expanded=show_intake_expanded,
):
    # Reasoning runs on the engine chosen in the Inference Model selector (rendered further down;
    # its key holds the last choice), resolved the same way the run handler resolves it.
    _sel_label = st.session_state.get("select_inference_model")
    if _sel_label in available_models:
        _sel_provider = available_models[_sel_label]
    else:
        _sel_provider = "stub" if is_stub_requested else ("ollama" if ollama_online else ("gemini" if has_gemini_key else "stub"))
    st.session_state["selected_model_provider"] = effective_provider(
        _sel_provider, has_gemini_key=bool(os.getenv("GEMINI_API_KEY", "").strip()), ollama_ok=ollama_online
    )
    intake_state = render_intake_view(before_run=render_question_register)
    query_input = intake_state["question_text"]
    run_submitted = intake_state["run_submitted"]
    depth_option = intake_state["depth"]
    tone_option = intake_state["tone"]

    # SIMPLIFIED SINGLE OPTIONAL DRAWER (Replaces the 2 confusing hubs)
    with st.expander("⚙️ Optional: Custom Source URLs & Synthesis Engine Settings (Automatic defaults active)", expanded=False):
        st.caption(
            "**How this works:** By default, the engine **automatically** searches Academic repositories (arXiv, OpenAlex, Crossref, Semantic Scholar) "
            "and Enterprise feeds (DORA, SEC EDGAR, engineering blogs). Only use the fields below if you want to inject specific URLs or switch the LLM backend."
        )
        opt_col1, opt_col2 = st.columns([1.1, 1.4])

        with opt_col1:
            st.markdown("##### 1. Synthesis Engine & API Key")
            model_names = list(available_models.keys())
            if is_stub_requested and "Deterministic Offline Engine (Zero-API Fallback)" not in model_names:
                available_models["Deterministic Offline Engine (Zero-API Fallback)"] = "stub"
                model_names.append("Deterministic Offline Engine (Zero-API Fallback)")

            if is_stub_requested:
                default_idx = next((i for i, k in enumerate(model_names) if available_models.get(k) == "stub"), 0)
            elif is_ollama_reachable():
                default_idx = next((i for i, k in enumerate(model_names) if available_models.get(k) == "ollama"), 0)
            elif has_gemini_key:
                default_idx = next((i for i, k in enumerate(model_names) if available_models.get(k) == "gemini"), 0)
            else:
                default_idx = next((i for i, k in enumerate(model_names) if available_models.get(k) == "stub"), 0)

            sel_model_label = st.selectbox("Inference Model", model_names, index=default_idx, key="select_inference_model")

            if os.getenv("HOSTED_DEMO") == "1":
                st.info("API key override disabled on shared instance.")
            else:
                custom_key = st.text_input(
                    "Temporary Gemini API Key (Optional)",
                    value="",
                    type="password",
                    placeholder="Paste Gemini API key to use cloud synthesis...",
                    help="Kept in memory for this session only.",
                )
                if custom_key.strip():
                    os.environ["GEMINI_API_KEY"] = custom_key.strip()

        with opt_col2:
            st.markdown("##### 2. Add Specific URLs or Field Notes (Optional)")
            custom_acad_input = st.text_area(
                "Academic Paper URLs / DOIs (Lane A — Optional, one per line):",
                value=st.session_state.get("custom_acad_urls", ""),
                key="custom_acad_urls_input",
                placeholder="https://arxiv.org/abs/2401.05432\nhttps://doi.org/10.1145/3611643",
                height=68,
            )
            st.session_state["custom_acad_urls"] = custom_acad_input

            custom_ent_input = st.text_area(
                "Enterprise Blog / Filing URLs (Lane B — Optional, one per line):",
                value=st.session_state.get("custom_ent_urls", ""),
                key="custom_ent_urls_input",
                placeholder="https://netflixtechblog.com/...\nhttps://www.sec.gov/edgar/...",
                height=68,
            )
            st.session_state["custom_ent_urls"] = custom_ent_input

            if os.getenv("HOSTED_DEMO") == "1":
                st.warning("🔒 Practitioner lane is disabled in hosted demo mode. Demo: no private data is stored.")
                custom_prac_input = ""
                st.session_state["custom_prac_urls"] = ""
                prac_abs_confirmed = False
                allow_remote_prac_synth = False
            else:
                custom_prac_input = st.text_area(
                    "Local Practitioner Field Notes (Lane C — Optional, stays on this machine):",
                    value=st.session_state.get("custom_prac_urls", ""),
                    key="custom_prac_urls_input",
                    placeholder="Delivery note: Canary rollout verified 0-downtime...",
                    height=68,
                )
                st.session_state["custom_prac_urls"] = custom_prac_input
                prac_abs_confirmed = st.checkbox(
                    "Confirm Practitioner Abstraction (No client names included)",
                    value=False,
                )
                allow_remote_prac_synth = False

selected_provider = available_models.get(sel_model_label, "gemini").strip()
# Re-runs (Feedback Loop 1, evidence board) resolve the engine the same way the main run does.
rerun_provider = effective_provider(selected_provider, has_gemini_key=bool(os.getenv("GEMINI_API_KEY", "").strip()), ollama_ok=ollama_online)


# ==============================================================================
# RUN HANDLER
# ==============================================================================
if run_submitted:
    active_query = query_input.strip()
    if not active_query:
        st.warning("⚠️ Please enter a research topic in Step 1 to begin.")
    else:
        lane_urls = {
            "academic": [u.strip() for u in custom_acad_input.splitlines() if u.strip()],
            "enterprise": [u.strip() for u in custom_ent_input.splitlines() if u.strip()],
            "practitioner": [u.strip() for u in custom_prac_input.splitlines() if u.strip()],
        }

        target_provider = selected_provider
        if target_provider == "gemini" and not os.getenv("GEMINI_API_KEY", "").strip():
            if is_ollama_reachable():
                st.info("ℹ️ **Gemini API Key Not Configured:** Automatically routed synthesis to **Local Ollama**.")
                target_provider = "ollama"
            else:
                st.info("ℹ️ **Gemini API Key Not Configured:** Automatically routed synthesis to **Deterministic Offline Engine**.")
                target_provider = "stub"

        st.session_state["current_question"] = active_query
        st.session_state["last_lane_urls"] = lane_urls
        launch_run_job(
            {"topic": active_query, "last_lane_urls": lane_urls},
            topic=active_query,
            depth=depth_option,
            tone=tone_option,
            map_provider=target_provider,
            reduce_provider=target_provider,
            papers_override=_generate_mock_papers(active_query) if is_stub_requested else None,
            custom_lane_urls=lane_urls,
            allow_remote_practitioner_synthesis=allow_remote_prac_synth,
            practitioner_abstraction_confirmed=prac_abs_confirmed,
            reasoned_package=intake_state.get("reasoned_package"),
        )

# A background run in progress, or one that failed, is shown here (S9).
if current_job and current_job["state"] == "running":
    render_job_progress(current_job["job_id"])
elif current_job and current_job["state"] == "failed":
    err = current_job.get("error") or {}
    st.error(
        f"**{err.get('title', 'Run failed')}**\n\n"
        f"• **What happened:** {err.get('what_happened', '')}\n\n"
        + (f"• **What completed:** {err['what_completed']}\n\n" if err.get("what_completed") else "")
        + (f"• **What to do next:** {err['next_steps']}" if err.get("next_steps") else "")
    )


# ==============================================================================
# PHASE OUTPUTS WORKSPACE (PHASES 2, 3, AND 4)
# ==============================================================================
results = st.session_state.get("research_results")

if results:
    paper_map = {p["key"]: p for p in results.get("papers", [])}
    claims_by_id_map = {c["id"]: c for c in results.get("claims", [])}
    gap_info = results.get("gap_matrix") or {}
    status = status_code(results)

    # ONE STATUS BANNER (S8): where the run stopped, why, and what to do next
    st.markdown(status_banner_html(run_status(results)), unsafe_allow_html=True)
    err_det = results.get("error_details") or {}
    if results.get("is_fallback") and err_det and err_det.get("error_class") not in (None, "OfflineEngine"):
        with st.expander("Model connection details", expanded=False):
            st.code(f"Error Class: {err_det.get('error_class')}\nMessage: {err_det.get('error_message')}", language="text")

    # Helper to render a single finding: click the sentence to see its cited quotes and hedges (S5)
    def _render_traceable_finding_card(item: Dict[str, Any], idx_num: int) -> None:
        st.markdown(
            finding_card_html(item, idx_num, item.get("text", ""), paper_map=paper_map),
            unsafe_allow_html=True,
        )

    # One tab per step after the question
    tab_brief, tab_evidence, tab_claims, tab_checks = st.tabs([
        "Brief",
        "Evidence",
        "Claims & gaps",
        "Checks & publish",
    ])

    # ==========================================================================
    # BRIEF: the draft read as an executive brief
    # ==========================================================================
    with tab_brief:
        report = results.get("report")
        if report:
            # S19: the question-shaped report (answer, a section per sub-question, tensions, gaps, implications).
            findings_by_text = {str(f.get("text", "")).strip(): f for f in results.get("findings") or []}
            # One st.markdown per block (see report_blocks); report_html joins the same blocks for exports.
            for block in report_blocks(report, paper_map, findings_by_text, meta=brief_meta_line(results),
                                       negatives=results.get("negative_findings"), diagram=results.get("diagram")):
                st.markdown(block, unsafe_allow_html=True)
        else:
            # Runs saved before S19 keep the earlier layout.
            verdict_text = results.get("verdict") or (
                f"Empirical synthesis across {len(results.get('papers', []))} academic papers and "
                f"{len(results.get('claims', []))} ledger claims."
            )
            verdict_formatted = format_citation_pills(verdict_text, paper_map)

            st.markdown(
                f"""
                <div class="verdict-banner">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <div class="verdict-banner-title">
                            <span>Bottom line</span>
                        </div>
                        <span style="background: #1E3A8A; color: white; padding: 0.25rem 0.75rem; border-radius: 6px; font-size: 0.78rem; font-weight: 700;">
                            {plain_html(gap_info.get('outcome_label', 'Outcome 1: Supported'))}
                        </span>
                    </div>
                    <p class="verdict-banner-body">{verdict_formatted}</p>
                    <div style="margin-top: 0.65rem; padding-top: 0.65rem; border-top: 1px solid rgba(15,23,42,0.1); font-size: 0.85rem; color: #1E293B;">
                        <strong>Research vs practice:</strong> {plain_html(gap_info.get('rationale', 'Empirical academic research is corroborated by active enterprise practice.'))}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(f'<div class="brief-meta">{plain_html(brief_meta_line(results))}</div>', unsafe_allow_html=True)

            # Signals that add something beyond the findings below (signals copied from findings are dropped)
            extra_signals = distinct_signals(results.get("signals") or [], results.get("findings") or [])
            if extra_signals:
                st.markdown('<div class="section-title"><span>Key signals</span></div>', unsafe_allow_html=True)
                st.markdown(
                    "<ul class=\"signal-list\">" + "".join(f"<li>{format_citation_pills(sig['text'], paper_map)}</li>" for sig in extra_signals[:3]) + "</ul>",
                    unsafe_allow_html=True,
                )

            st.markdown('<div class="section-title"><span>Findings</span></div>', unsafe_allow_html=True)
            st.caption("Click a finding to see the quotes it rests on, their grade and any hedging.")

            if results.get("findings"):
                for idx_f, item in enumerate(results["findings"], start=1):
                    _render_traceable_finding_card(item, idx_f)
            else:
                st.info("No empirical findings met the threshold criteria for this question. Check 'What the Evidence Does Not Support' below.")

            # Risks & Negative Findings side by side
            r_col1, r_col2 = st.columns(2)
            with r_col1:
                st.markdown("##### Risks")
                if results.get("risks"):
                    for risk in results["risks"]:
                        st.markdown(
                            f"""
                            <div class="risk-item">
                                <strong>•</strong> {format_citation_pills(risk, paper_map)}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("No specific delivery risk assertions recorded in the ledger for this run.")

            with r_col2:
                st.markdown("##### What the evidence does not show")
                if results.get("negative_findings"):
                    for nf in results["negative_findings"]:
                        st.markdown(
                            f"""
                            <div style="background: #F8FAFC; border: 1px solid #CBD5E1; border-left: 4px solid #64748B; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 0.6rem; font-size: 0.88rem; color: #334155;">
                                {plain_html(nf)}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("No negative findings recorded.")

            if results.get("roadmap"):
                st.markdown("##### Recommended next steps")
                st.markdown(roadmap_html(results.get("roadmap", [])), unsafe_allow_html=True)

    # ==========================================================================
    # EVIDENCE: the three lanes' sources, Check A detail, exclude-and-re-draft
    # ==========================================================================
    with tab_evidence:
        st.markdown("### Evidence")
        _map_html = evidence_map_html(results.get("report"), results.get("papers", []))
        if _map_html:
            # S19b: which paper backs which sub-question, before the full paper list.
            st.markdown("#### Evidence map")
            st.caption("Each row is a paper; a dot means that question's section cites it. Hover a Q heading to see "
                       "the question. Papers marked 'not cited' were found but not used in the brief.")
            st.markdown(_map_html, unsafe_allow_html=True)
        # Check A: on-topic evidence (DEC-016)
        check_a_info = results.get("check_a") or {}
        if check_a_info and results.get("stopped_at") != "check_a":
            st.caption(f"Check A passed: {check_a_info.get('reason', '')}")
        breadth = results.get("breadth") or {}
        if breadth.get("checked"):
            # S15: how many candidates Check A judged, how many were on topic, and how many were used.
            st.caption(f"Checked {breadth['checked']} papers · {breadth.get('on_topic', 0)} on topic · "
                       f"used the best {breadth.get('used', 0)} by venue quality and relevance.")
        if check_a_info.get("sources"):
            with st.expander("Check A: which sources were judged on-topic", expanded=results.get("stopped_at") == "check_a"):
                st.table([
                    {
                        "Source": src.get("title", ""),
                        "Lane": str(src.get("lane", "")).capitalize(),
                        "Verdict": "On-topic" if src.get("verdict") == "on_topic" else "Off-topic",
                        "Why": src.get("reason", ""),
                    }
                    for src in check_a_info["sources"]
                ])

        st.markdown(
            "The academic papers, enterprise sources and your field notes this run found. "
            "To drop an off-topic paper, use **Exclude weak papers and re-draft** at the bottom of this tab."
        )

        st.markdown(f"#### 🎓 Lane A: Academic Papers Ingested ({len(results.get('papers', []))})")
        for p in results.get("papers", []):
            st.markdown(paper_card_html(p), unsafe_allow_html=True)

        st.markdown("---")
        ent_sources = results.get("enterprise_sources", [])
        st.markdown(f"#### 🏢 Lane B: Enterprise Literature & Benchmarks ({len(ent_sources)})")
        if ent_sources:
            for es in ent_sources:
                es_date = es.get("pub_date")
                es_date_str = es_date if (es_date and str(es_date).lower() not in ("none", "null")) else "Date unknown"
                st.markdown(
                    f"""
                    <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 0.9rem 1.15rem; margin-bottom: 0.65rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
                            <span style="font-size: 0.78rem; font-weight: 700; color: #6D28D9; background: #F5F3FF; padding: 0.15rem 0.5rem; border-radius: 4px;">{es.get('source_type', 'enterprise').upper()}</span>
                            <span style="font-size: 0.74rem; color: #64748B;">Commercial Stake: <strong>{es.get('commercial_stake', 'vendor').upper()}</strong></span>
                        </div>
                        <div style="font-weight: 700; font-size: 0.94rem; color: #0F172A; margin-bottom: 0.25rem;">
                            <a href="{es.get('url', '#')}" target="_blank" style="color: #0F172A; text-decoration: none;">{es.get('title')} ↗</a>
                        </div>
                        <div style="font-size: 0.8rem; color: #64748B;">
                            Org/Venue: <strong>{es.get('venue')}</strong> &nbsp;•&nbsp; Date: <strong>{es_date_str}</strong>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No enterprise claims recorded for this question.")

        st.markdown("---")
        prac_obs = results.get("practitioner_observations", [])
        st.markdown(f"#### 🛠️ Lane C: Local Practitioner Observations ({len(prac_obs)})")
        if prac_obs:
            for po in prac_obs:
                st.markdown(
                    f"""
                    <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 0.9rem 1.15rem; margin-bottom: 0.65rem;">
                        <div style="font-weight: 700; font-size: 0.92rem; color: #0F172A; margin-bottom: 0.25rem;">{po.get('situation')}</div>
                        <div style="font-size: 0.82rem; color: #334155; margin-bottom: 0.25rem;"><strong>Action:</strong> {po.get('action')}</div>
                        <div style="font-size: 0.8rem; color: #047857; font-weight: 600;"><strong>Outcome:</strong> {po.get('outcome')} &nbsp;•&nbsp; Date: {po.get('date')}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No local practitioner observations recorded for this question.")

        # FEEDBACK LOOP 1: Paper Exclusion & Re-Synthesis
        st.markdown("---")
        st.markdown("#### Exclude weak papers and re-draft")
        st.caption("Found an off-topic or weak paper? Exclude it below to re-grade the claims and re-draft the brief.")
        paper_choices = [f"[{p['key']}] {p['title']}" for p in results.get("papers", [])]
        excluded_papers = st.multiselect("Select papers to exclude from synthesis:", options=paper_choices)

        if st.button("🔄 Execute Feedback Loop: Re-Synthesize Without Excluded Papers", type="secondary"):
            if not excluded_papers:
                st.warning("Please select at least one paper to exclude.")
            else:
                excluded_keys = {re.search(r"\[(P\d+)\]", s).group(1) for s in excluded_papers if re.search(r"\[(P\d+)\]", s)}
                remaining = papers_for_rerun(results, drop_keys=excluded_keys, drop_custom=False)
                if not remaining:
                    st.error("Cannot exclude all papers. At least 1 paper is required for synthesis.")
                else:
                    topic_rerun = approved_question_text(st.session_state.get("s2_active_package"), results)
                    launch_run_job(
                        {"topic": topic_rerun, "last_lane_urls": st.session_state.get("last_lane_urls")},
                        topic=topic_rerun,
                        depth=depth_option,
                        tone=tone_option,
                        map_provider=rerun_provider,
                        reduce_provider=rerun_provider,
                        papers_override=remaining,
                        allow_remote_practitioner_synthesis=allow_remote_prac_synth,
                        practitioner_abstraction_confirmed=prac_abs_confirmed,
                        reasoned_package=st.session_state.get("s2_active_package"),
                    )

    # ==========================================================================
    # CLAIMS & GAPS: the claim ledger and the gap matrix
    # ==========================================================================
    with tab_claims:
        st.markdown("### Claims & gaps")
        st.markdown(
            "Every extracted claim is stored in the evidence ledger with its full untruncated assertion, "
            "verbatim source excerpt (≤ 25 words), deterministic evidence grade, and source paper link."
        )

        # Strategic Gap Matrix Summary
        gap_data = results.get("gap_matrix", {})
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("Academic Lane State", gap_data.get("academic_state", "SUPPORTED").upper())
        m_col2.metric("Enterprise Lane State", gap_data.get("enterprise_state", "SUPPORTED").upper())
        m_col3.metric("Field Lane State", gap_data.get("field_state", "SUPPORTED").upper())
        m_col4.metric("Strategic Outcome", f"Outcome {gap_data.get('outcome', 1)}")

        st.markdown("---")
        claims_list = results.get("claims", [])
        if claims_list:
            c_filter_col1, c_filter_col2 = st.columns(2)
            with c_filter_col1:
                selected_lane_filter = st.selectbox("Filter by Evidence Lane", ["All Lanes", "ACADEMIC", "ENTERPRISE", "PRACTITIONER"])
            with c_filter_col2:
                selected_grade_filter = st.selectbox("Filter by Deterministic Grade", ["All Grades", "STRONG", "MODERATE", "WEAK", "VENDOR_CLAIM", "ANECDOTE"])

            filtered_claims = claims_list
            if selected_lane_filter != "All Lanes":
                filtered_claims = [c for c in filtered_claims if c["lane"] == selected_lane_filter]
            if selected_grade_filter != "All Grades":
                filtered_claims = [c for c in filtered_claims if c["grade"] == selected_grade_filter]

            st.caption(f"Displaying {len(filtered_claims)} of {len(claims_list)} atomic claim records (Zero character truncation applied)")

            claims_table_data = [
                {
                    "Claim ID": c["id"],
                    "Source": f"[{c.get('source_key', 'SRC')}] {c.get('source_title', 'Unknown')}",
                    "Venue & Year": f"{c.get('venue', 'Repo')} ({c.get('year', 'n/a')})",
                    "Lane": c["lane"],
                    "Grade": c["grade"],
                    "Full Paraphrased Assertion": c["assertion"],
                    "Verbatim Source Excerpt (<=25 words)": c["excerpt"],
                    "Study Type": c["study_type"],
                    "Rules Fired": c["rules"],
                }
                for c in filtered_claims
            ]
            render_safe_table(claims_table_data, use_container_width=True)
        else:
            st.info("No claims recorded in ledger for this run.")

        # EVIDENCE BOARD (S4): choose the claims that go into the draft. Check B re-runs on re-draft.
        st.markdown("---")
        st.markdown("#### 🗂️ Evidence Board: choose which claims go into the draft")
        check_b_info = results.get("check_b") or {}
        if results.get("stopped_at") == "check_b":
            st.error(f"**Run blocked at Check B.** {results.get('stop_reason', '')}")
        elif check_b_info:
            st.caption(f"Check B passed: {check_b_info.get('reason', '')}")

        excluded_list = results.get("excluded_claims", [])
        operator_excluded = [c for c in excluded_list if c.get("exclusion_kind") == "operator"]
        set_aside = [c for c in excluded_list if c not in operator_excluded]
        board_claims = list(claims_list) + operator_excluded
        if board_claims:
            import pandas as pd

            board_df = pd.DataFrame([
                {
                    "Include": c not in operator_excluded,
                    "Claim": c["assertion"],
                    "Source": f"[{c.get('source_key', 'SRC')}] {c.get('source_title', 'Unknown')}",
                    "Lane": c["lane"].capitalize(),
                    "Grade": c["grade"].capitalize(),
                }
                for c in board_claims
            ])
            edited = st.data_editor(
                board_df,
                key=board_editor_key(results),
                hide_index=True,
                use_container_width=True,
                disabled=["Claim", "Source", "Lane", "Grade"],
            )
            excluded_keys = [c["content_key"] for c, keep in zip(board_claims, edited["Include"].tolist()) if not keep]
            st.caption(f"{len(board_claims) - len(excluded_keys)} of {len(board_claims)} claims will go into the draft.")
        else:
            excluded_keys = []
            st.caption("No claims to choose from yet. Add a source below and re-draft.")
        if set_aside:
            with st.expander(f"{len(set_aside)} malformed claims were set aside by Check B"):
                render_safe_table(
                    [{"Claim": c["assertion"], "Source": c.get("source_title", ""), "Why": c["exclusion_reason"]} for c in set_aside],
                    use_container_width=True,
                )

        new_source_url = st.text_input("Add a source URL (academic lane)", key="evidence_board_new_url")
        if st.button("🔄 Re-draft with these choices", type="primary", key="evidence_board_redraft"):
            lane_urls_redraft = {k: list(v) for k, v in (st.session_state.get("last_lane_urls") or {}).items()}
            if new_source_url.strip():
                lane_urls_redraft.setdefault("academic", []).append(new_source_url.strip())
            topic_redraft = approved_question_text(st.session_state.get("s2_active_package"), results)
            launch_run_job(
                {"topic": topic_redraft, "last_lane_urls": lane_urls_redraft},
                topic=topic_redraft,
                depth=depth_option,
                tone=tone_option,
                map_provider=rerun_provider,
                reduce_provider=rerun_provider,
                # Custom-URL papers are re-fetched from lane_urls_redraft, so they are not passed twice.
                papers_override=papers_for_rerun(results) or None,
                custom_lane_urls=lane_urls_redraft,
                allow_remote_practitioner_synthesis=allow_remote_prac_synth,
                practitioner_abstraction_confirmed=prac_abs_confirmed,
                reasoned_package=st.session_state.get("s2_active_package"),
                excluded_claim_keys=excluded_keys,
            )

    # ==========================================================================
    # CHECKS & PUBLISH: gates G1-G6, scorecard, human publish, downloads
    # ==========================================================================
    with tab_checks:
        st.markdown("### Checks & publish")
        audit_res = results.get("gates_audit", {})
        # A gate with no data counts as a fail (S6): only an audited PASS on all six is a pass.
        all_gates_pass = audit_res.get("passed", False)
        if all_gates_pass:
            st.success("✅ All six gates passed on this draft's own evidence.")
        else:
            st.error(f"⛔ Not all gates passed ({gates_summary(audit_res)}). A gate with no data counts as a fail; see why below.")

        g_col1, g_col2 = st.columns(2)
        with g_col1:
            st.markdown("##### Gates G1–G6")
            render_safe_table(gate_rows(audit_res), use_container_width=True)

        with g_col2:
            st.markdown("##### Quality Scorecard (S1–S7 Components)")
            score_data = results.get("quality_scorecard", {})
            comp_scores = score_data.get("components") or {}
            if comp_scores:
                s_df = [{"Component": k, "Score": v} for k, v in comp_scores.items()]
                render_safe_table(s_df, use_container_width=True)
            else:
                st.caption("Not scored: this run stopped before drafting.")

        # PUBLISH (S6): runs never publish themselves; a named reviewer does, here.
        st.markdown("---")
        st.markdown("##### Publish")
        eligible, needs_reason, why_not = publish_eligibility(results)
        reviewer_name = st.text_input("Reviewer name", key=f"publish_reviewer_{results.get('run_id')}")
        signoff_reason = st.text_area(
            "Sign-off reason" + (" (required for REVISE)" if needs_reason else ""),
            key=f"publish_reason_{results.get('run_id')}",
            height=70,
        )
        if why_not:
            (st.info if eligible else st.warning)(why_not)
        publish_ready = eligible and reviewer_name.strip() and (signoff_reason.strip() or not needs_reason)
        if st.button("Publish this draft", type="primary", disabled=not publish_ready, key=f"publish_btn_{results.get('run_id')}"):
            ok, pub = multilane_runner.publisher.publish_output(
                output_id=results["doc_id"],
                reviewer=reviewer_name.strip(),
                signoff_reason=signoff_reason.strip() or "Approved by reviewer.",
                force_publish_non_band=needs_reason,
            )
            if ok:
                results["status"] = "PUBLISHED"
                results["publish_res"] = {**results.get("publish_res", {}), **pub, "published": True, "status": "PUBLISHED"}
                st.session_state["research_results"] = results
                st.success("Published. The sign-off is logged with your name and reason.")
                st.rerun()
            else:
                st.error(f"Not published: {pub.get('reason', 'unknown reason')}")

        st.markdown("---")
        st.markdown("##### Complete Sentence-Level Grounding Trace (`output_sentences` Ledger)")
        traces = results.get("sentence_traces", [])
        if traces:
            for t in traces:
                if t["type"] == "heading":
                    st.markdown(f"**[Ordinal {t['ordinal']} • Heading]** {t['text']}")
                else:
                    c_pill = f" ➔ Cited Claims: `{', '.join(t['claims'])}`" if t.get("claims") else f" ➔ Type: `{t['type']}`"
                    st.markdown(f"- **[Ordinal {t['ordinal']}]** {t['text']}{c_pill}")

    # EXPORT CENTER TOOLBAR
    st.markdown(
        """
        <div class="export-box">
            <div class="export-title">
                <span>📦 Export Deliverables</span>
            </div>
            <div class="export-subtitle">
                Download verified executive briefings, structured data ledgers, and interactive presentations:
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    is_allowed = results.get("publish_res", {}).get("allowed") is True
    gate_violations = (results.get("gates_audit") or results.get("publish_res", {}).get("gate_results") or {}).get("violations", {})
    pub_reasons = results.get("publish_res", {}).get("reasons", [])
    quality_score = results.get("quality_scorecard", {}).get("total_score")

    perm = evaluate_export_permissions(
        status=status,
        allowed=is_allowed,
        gate_violations=gate_violations,
        reasons=pub_reasons,
        quality_score=quality_score,
    )

    if perm.is_blocked:
        st.error(
            f"🚫 **Export Prohibited (BLOCKED):** Hard governance gate violations prevent publication or draft generation. "
            f"Failing gates: {', '.join(perm.failing_gates) if perm.failing_gates else 'Hard gate failures present'}. "
            "No overrides are permitted."
        )
    elif not perm.can_download_full:
        st.warning(
            f"🔒 **Draft Export Only ({status}):** Output has not achieved `PUBLISH_READY` status. "
            "Only watermarked draft deliverables (.md and .json) are available. "
            "LinkedIn pack and presentation deck are disabled until publication gates pass."
        )

    export_col1, export_col2, export_col3, export_col4, export_col5 = st.columns(5)

    builder = ReportBuilder()
    syn_raw = results.get("synthesis", {})
    topic_str = st.session_state.get("current_question", results.get("strategic_question", "Executive Briefing"))

    if results.get("report") and (perm.can_download_full or perm.can_download_draft):
        # S19: the brief download follows the report, built from the checked ledger sentences.
        brief_content = report_markdown(results["report"], question=results.get("strategic_question", topic_str),
                                        diagram=results.get("diagram"), papers=results.get("papers", []))
        if not perm.can_download_full:
            brief_content = "# DRAFT, NOT FOR PUBLICATION\n\n" + brief_content
        json_content = json.dumps(export_view(results), indent=2, default=str)
    elif perm.can_download_full:
        brief_content = builder.build_markdown(topic_str, syn_raw) if syn_raw else f"# Executive Research Brief\n\n**Topic:** {topic_str}\n\n## Verdict\n{results.get('verdict', '')}\n"
        json_content = json.dumps(syn_raw or export_view(results), indent=2)
    elif perm.can_download_draft and results.get("stopped_at"):
        # S13: nothing was drafted, so the download says why the run stopped instead of an empty template.
        brief_content = stopped_run_markdown(results)
        json_content = json.dumps({"watermark": "DRAFT, NOT FOR PUBLICATION", "status": status,
                                   "failing_gates": perm.failing_gates, **export_view(results)}, indent=2)
    elif perm.can_download_draft:
        brief_content = builder.build_draft_markdown(topic_str, syn_raw, failing_gates=perm.failing_gates, status=status)
        draft_json_obj = {
            "watermark": "DRAFT, NOT FOR PUBLICATION",
            "status": status,
            "failing_gates": perm.failing_gates,
        }
        draft_json_obj.update(syn_raw or results)
        json_content = json.dumps(draft_json_obj, indent=2)
    else:
        brief_content = ""
        json_content = ""

    papers_df = pd.DataFrame(results.get("papers", []))
    csv_content = papers_df.to_csv(index=False)
    linkedin_pack = builder.build_linkedin_pack(topic_str, syn_raw) if syn_raw else "# LinkedIn Executive Thought Leadership Pack\n\n"
    deck_path = Path(default_outputs_dir()) / "reports" / "strategic_storyline.html"
    deck_html = deck_path.read_text(encoding="utf-8") if deck_path.exists() else builder.build_html_storyline(topic_str, syn_raw)

    with export_col1:
        st.download_button(
            label="📄 " + ("Executive Brief (.md)" if perm.can_download_full else "Draft Brief (.md)"),
            data=brief_content,
            file_name="Executive_Research_Brief.md" if perm.can_download_full else "Executive_Research_Brief_DRAFT.md",
            mime="text/markdown",
            disabled=not (perm.can_download_full or perm.can_download_draft),
            use_container_width=True,
        )
    with export_col2:
        st.download_button(
            label="📊 " + ("JSON Ledger (.json)" if perm.can_download_full else "Draft Ledger (.json)"),
            data=json_content,
            file_name="evidence_ledger.json" if perm.can_download_full else "evidence_ledger_DRAFT.json",
            mime="application/json",
            disabled=not (perm.can_download_full or perm.can_download_draft),
            use_container_width=True,
        )
    with export_col3:
        st.download_button(
            label="📦 Paper Index (.csv)",
            data=csv_content,
            file_name="paper_index.csv",
            mime="text/csv",
            disabled=not perm.can_download_csv,
            use_container_width=True,
        )
    with export_col4:
        st.download_button(
            label="📱 LinkedIn Pack (.md)",
            data=linkedin_pack,
            file_name="LinkedIn_Executive_Pack.md",
            mime="text/markdown",
            disabled=not perm.can_download_linkedin,
            use_container_width=True,
        )
    with export_col5:
        st.download_button(
            label="🏛️ Presentation Deck (.html)",
            data=deck_html,
            file_name="Executive_Deck.html",
            mime="text/html",
            disabled=not perm.can_download_deck,
            use_container_width=True,
        )
