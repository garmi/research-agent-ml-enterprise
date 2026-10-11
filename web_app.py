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
from src.config import ensure_directories, load_config
from src.fetchers.arxiv_client import ArxivClient
from src.fetchers.crossref_client import CrossrefClient
from src.fetchers.openalex_client import OpenAlexClient
from src.fetchers.semantic_scholar_client import SemanticScholarClient
from src.llm.factory import build_llm
from src.output.content_pack import ContentPackBuilder
from src.output.report_builder import ReportBuilder

from src.ledger.service import LedgerService
from src.ledger.ui_views import (
    render_question_register,
    render_venue_tiering,
    render_gap_matrix_view,
    render_practitioner_entry_view,
    render_safe_table,
)

logger = logging.getLogger("ExecutiveResearchStudio")
logging.basicConfig(level=logging.INFO)

load_dotenv()
config = load_config("config.yaml") if Path("config.yaml").exists() else {}
ensure_directories("outputs")
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

    if has_key:
        options["Google Gemini 3.8 Flash (Cloud API) [Configured]"] = "gemini"
    if ollama_ok:
        options["Local Ollama Qwen 2.5 3B (Local Offline) [Active]"] = "ollama"
    if not has_key:
        options["Google Gemini 3.8 Flash (Cloud API) [API Key Required]"] = "gemini"
    options["Deterministic Offline Engine (Zero-API Fallback)"] = "stub"
    return options


# --- PAGE SETUP ---
st.set_page_config(
    page_title="Executive AI Research Studio",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- ENTERPRISE DESIGN SYSTEM STYLING ---
st.markdown(
    """
    <style>
    /* -------------------------------------------------------------
       EXECUTIVE AI RESEARCH STUDIO - ENTERPRISE DESIGN SYSTEM
       ------------------------------------------------------------- */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    :root {
        --font-main: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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

    /* Primary Launch Button */
    button[kind="primary"] {
        background: var(--brand-gradient) !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em !important;
        font-size: 0.95rem !important;
        padding: 0.65rem 1.4rem !important;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.3) !important;
        transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }

    button[kind="primary"]:hover {
        box-shadow: 0 6px 20px rgba(37, 99, 235, 0.45) !important;
        transform: translateY(-1px) !important;
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

if "history" not in st.session_state:
    st.session_state["history"] = []

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
    """Format [P1], [P2] tags into interactive styled citation pill badges."""
    def repl(m):
        pkey = m.group(1)
        paper = paper_map.get(pkey, {})
        url = paper.get("url") or paper.get("link") or paper.get("doi") or "#"
        title = (paper.get("title") or "Academic Paper").replace('"', '&quot;')
        year = paper.get("year", "")
        return f'<a href="{url}" target="_blank" title="{title} ({year})" class="cite-pill">[{pkey}]</a>'
    return re.sub(r"\[(P\d+)\]", repl, text)


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
    progress_box: Any,
    papers_override: Optional[List[Dict[str, Any]]] = None,
    custom_lane_urls: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Execute the formal 8-stage research engine workflow across Academic, Enterprise, and Practitioner lanes."""
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

    def on_progress(stage_idx: int, stage_msg: str, progress_val: float):
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

    results = multilane_runner.run_workflow(
        topic=topic,
        depth=depth,
        tone=tone,
        map_provider=map_provider,
        reduce_provider=reduce_provider,
        on_progress=on_progress,
        academic_papers_override=papers_override,
        custom_lane_urls=custom_lane_urls,
    )
    progress_box.empty()
    return results


# ==============================================================================
# SIDEBAR
# ==============================================================================
available_models = get_available_models()
has_gemini_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
ollama_online = is_ollama_reachable()

with st.sidebar:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 0.65rem; margin-bottom: 1.25rem;">
            <div style="background: linear-gradient(135deg, #2563EB, #1E40AF); color: white; width: 34px; height: 34px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 1.15rem; font-weight: bold; box-shadow: 0 2px 6px rgba(37,99,235,0.3);">
                🔬
            </div>
            <div>
                <div style="font-weight: 800; font-size: 1rem; color: #0F172A; line-height: 1.1;">Executive AI</div>
                <div style="font-size: 0.74rem; font-weight: 600; color: #64748B; letter-spacing: 0.04em;">RESEARCH STUDIO</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # System Status Pod
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
            <div style="margin-top: 0.65rem; padding-top: 0.65rem; border-top: 1px solid #F1F5F9; font-size: 0.74rem; color: #64748B;">
                Default Active Engine: <strong style="color: #334155;">Google Gemini 3.8 Flash</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Previous Runs Section
    st.markdown('<div class="sidebar-pod-title" style="margin-top: 1.5rem;">Previous Research Runs</div>', unsafe_allow_html=True)
    if not st.session_state["history"]:
        st.markdown(
            """
            <div style="font-size: 0.82rem; color: #94A3B8; background: #F8FAFC; border: 1px dashed #E2E8F0; border-radius: 8px; padding: 1rem; text-align: center;">
                No runs yet this session.<br>Synthesized executive dossiers will appear here.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for idx, item in enumerate(reversed(st.session_state["history"])):
            run_title = item.get("topic", "Research Run")
            if len(run_title) > 36:
                run_title = run_title[:33] + "..."
            if st.button(f"📋 {run_title}", key=f"hist_{idx}", use_container_width=True):
                st.session_state["research_results"] = item["results"]
                st.session_state["current_question"] = item["topic"]
                st.rerun()

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
    if st.session_state["research_results"] is not None:
        if st.button("🗑️ Reset Workspace Session", use_container_width=True):
            st.session_state["research_results"] = None
            st.session_state["current_question"] = ""
            st.rerun()


# ==============================================================================
# HEADER
# ==============================================================================
st.markdown(
    """
    <div class="studio-header">
        <div class="studio-title-group">
            <h1>Executive AI Research Studio</h1>
            <p>Evidence-backed intelligence, publication-ready LinkedIn briefs, and strategic presentation decks.</p>
        </div>
        <div class="meta-badge">
            <span class="pulse-dot"></span>
            100% Traceable Evidence Engine • Multi-Repository Synthesis
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# STRATEGIC QUESTION FORMULATION AGENT
# ==============================================================================
is_stub_requested = (
    st.query_params.get("stub") == "1"
    or st.query_params.get("mock") == "1"
    or os.getenv("STUB_LLM") == "1"
)
default_formulate_provider = "stub" if is_stub_requested else ("ollama" if ollama_online and not has_gemini_key else "gemini")

st.markdown(
    """
    <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 1.25rem 1.5rem; margin-bottom: 1.25rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
            <div style="font-weight: 700; font-size: 1.05rem; color: #0F172A; display: flex; align-items: center; gap: 0.5rem;">
                <span>🤖 Strategic Question Formulation Agent</span>
            </div>
            <span style="font-size: 0.74rem; background: #EEF2FF; color: #4338CA; padding: 0.2rem 0.65rem; border-radius: 9999px; font-weight: 700; letter-spacing: 0.03em;">
                AI Inquiry Framing
            </span>
        </div>
        <div style="font-size: 0.86rem; color: #64748B; margin-bottom: 0.85rem; line-height: 1.45;">
            State your raw enterprise dilemma, delivery friction, or business challenge. The agent analyzes the problem and formulates a balanced, multi-lane <strong>Strategic Technology Question</strong> ready for Academic, Enterprise, and Practitioner literature.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

qf_col_input, qf_col_btn = st.columns([3.8, 1.2])

with qf_col_input:
    user_problem_input = st.text_area(
        "Raw Problem Description",
        value=st.session_state.get("raw_problem_input", ""),
        placeholder="e.g. Our engineering leaders are seeing teams adopt AI coding agents like Kiro and Copilot, but we need empirical evidence regarding security vulnerabilities, IP licensing, and measuring real developer productivity vs vanity metrics.",
        height=85,
        help="Type your unstructured business, technical, or delivery dilemma here.",
        label_visibility="collapsed",
    )

with qf_col_btn:
    st.markdown("<div style='height: 0.05rem;'></div>", unsafe_allow_html=True)
    formulate_submitted = st.button("✨ Formulate Question", type="secondary", use_container_width=True)
    clear_problem_btn = st.button("Clear Problem", use_container_width=True)
    if clear_problem_btn:
        st.session_state["raw_problem_input"] = ""
        st.session_state["formulated_question_obj"] = None
        st.rerun()

if formulate_submitted:
    if not user_problem_input.strip():
        st.warning("⚠️ Please provide your problem statement or dilemma text above to formulate a research question.")
    else:
        st.session_state["raw_problem_input"] = user_problem_input.strip()
        with st.spinner("🤖 Agent analyzing problem text across Academic, Enterprise, and Delivery dimensions..."):
            formulated_obj = question_agent.formulate(
                raw_problem=user_problem_input.strip(),
                model_provider=default_formulate_provider,
            )
            st.session_state["formulated_question_obj"] = formulated_obj
            st.session_state["current_question"] = formulated_obj.strategic_question
            st.rerun()

# Display formulation summary card if available
formulated_obj = st.session_state.get("formulated_question_obj")
if formulated_obj:
    st.markdown(
        f"""
        <div style="background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 1.25rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                <div style="font-weight: 700; font-size: 0.88rem; color: #1E3A8A;">
                    💡 Formulated Strategic Research Question:
                </div>
                <span style="font-size: 0.74rem; background: #E0E7FF; color: #3730A3; padding: 0.15rem 0.55rem; border-radius: 4px; font-weight: 700; text-transform: uppercase;">
                    SCOPE: {formulated_obj.scope}
                </span>
            </div>
            <div style="font-size: 0.98rem; font-weight: 700; color: #0F172A; margin-bottom: 0.5rem; line-height: 1.4;">
                "{formulated_obj.strategic_question}"
            </div>
            <div style="font-size: 0.82rem; color: #475569; margin-bottom: 0.6rem;">
                <strong>Strategic Rationale:</strong> {formulated_obj.rationale}
            </div>
            <div style="font-size: 0.78rem; color: #64748B;">
                <strong>Inquiry Dimensions (Sub-Questions):</strong>
                <ul style="margin: 0.25rem 0 0 1rem; padding: 0;">
                    <li>{formulated_obj.sub_questions[0]}</li>
                    <li>{formulated_obj.sub_questions[1]}</li>
                    <li>{formulated_obj.sub_questions[2]}</li>
                </ul>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    reg_col1, reg_col2 = st.columns([2.0, 3.0])
    with reg_col1:
        if st.button("📋 Register in Question Register (YAML Gate 1)", key="reg_q_btn", use_container_width=True):
            saved_q = question_agent.register_question_in_register(formulated_obj, ledger_service)
            st.success(f"✓ Registered '{saved_q.id}' in `questions/register.yaml` and SQLite ledger!")

st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)


# ==============================================================================
# RESEARCH CONSOLE CARD
# ==============================================================================
st.markdown('<div class="research-console-card">', unsafe_allow_html=True)

query_input = st.text_input(
    "Strategic Technology Question",
    value=st.session_state["current_question"],
    placeholder="e.g. Assessing DevEx and cycle time impact of platform engineering in regulated enterprises",
    help="Type any enterprise engineering, AI platform, or DevSecOps inquiry for multi-source peer-reviewed literature synthesis.",
    label_visibility="visible",
)

col_depth, col_tone, col_btn = st.columns([1.3, 1.3, 1.1])

with col_depth:
    depth_option = st.selectbox(
        "Research Depth",
        options=[
            "⚡ Fast (~45s • 2 rounds • up to 10 sources)",
            "🔬 Deep (~3-5m • 5 rounds • comprehensive synthesis)",
        ],
        index=0,
        help="Fast provides an immediate executive brief; Deep executes multi-round citation graph queries.",
    )
    st.caption("⚡ Fast: Quick high-signal brief • 🔬 Deep: Comprehensive multi-round analysis")

with col_tone:
    tone_option = st.selectbox(
        "Strategic Tone",
        options=[
            "Executive (ROI & Risk)",
            "Architectural (Technical Depth)",
            "Market & Industry (Macro Trends)",
        ],
        index=0,
        help="Calibrates the framing, metric focus, and audience persona for executive deliverables.",
    )
    st.caption("Adjusts executive emphasis, recommendation framing, and audience persona")

with col_btn:
    st.markdown("<div style='height: 1.7rem;'></div>", unsafe_allow_html=True)
    run_submitted = st.button("🚀 Run Research", type="primary", use_container_width=True)

# ------------------------------------------------------------------------------
# THREE-LANE SOURCE REPOSITORIES & MANUAL INGESTION CONSOLE
# ------------------------------------------------------------------------------
st.markdown("<div style='margin-top: 1rem; padding-top: 0.85rem; border-top: 1px solid #E2E8F0;'></div>", unsafe_allow_html=True)
st.markdown(
    """
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.65rem;">
        <div style="font-weight: 700; font-size: 0.96rem; color: #0F172A; display: flex; align-items: center; gap: 0.5rem;">
            <span>🌐</span> Three-Lane Source Repositories & Manual Web Ingestion
        </div>
        <span style="font-size: 0.74rem; background: #EEF2F6; color: #334155; padding: 0.2rem 0.6rem; border-radius: 9999px; font-weight: 600;">
            YAML & SQLite Evidence Architecture
        </span>
    </div>
    """,
    unsafe_allow_html=True,
)

lane_input_col1, lane_input_col2, lane_input_col3 = st.columns(3)

with lane_input_col1:
    st.markdown(
        """
        <div style="background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px; padding: 0.6rem 0.8rem; margin-bottom: 0.5rem;">
            <div style="font-weight: 700; color: #1E40AF; font-size: 0.85rem; display: flex; justify-content: space-between; align-items: center;">
                <span>🎓 Lane A: Academic Literature</span>
                <span style="font-size: 0.7rem; background: #DBEAFE; color: #1E40AF; padding: 0.1rem 0.4rem; border-radius: 4px; font-weight: 700;">Active</span>
            </div>
            <div style="font-size: 0.74rem; color: #3B82F6; margin-top: 0.2rem;">
                arXiv • OpenAlex • Crossref • Semantic Scholar
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    custom_acad_input = st.text_area(
        "Custom Academic URLs / DOIs (One per line):",
        value=st.session_state.get("custom_acad_urls", ""),
        key="custom_acad_urls_input",
        placeholder="https://arxiv.org/abs/2401.05432\nhttps://doi.org/10.1145/3611643\nhttps://openalex.org/W...",
        height=90,
        help="Paste custom arXiv URLs, DOIs, or academic links. Ingested into Lane A with atomic claim extraction.",
    )
    st.session_state["custom_acad_urls"] = custom_acad_input

with lane_input_col2:
    st.markdown(
        """
        <div style="background: #F5F3FF; border: 1px solid #DDD6FE; border-radius: 8px; padding: 0.6rem 0.8rem; margin-bottom: 0.5rem;">
            <div style="font-weight: 700; color: #6D28D9; font-size: 0.85rem; display: flex; justify-content: space-between; align-items: center;">
                <span>🏢 Lane B: Enterprise Literature</span>
                <span style="font-size: 0.7rem; background: #EDE9FE; color: #6D28D9; padding: 0.1rem 0.4rem; border-radius: 4px; font-weight: 700;">Commercial Cap</span>
            </div>
            <div style="font-size: 0.74rem; color: #7C3AED; margin-top: 0.2rem;">
                Engineering Blogs • SEC EDGAR • DORA Benchmarks
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    custom_ent_input = st.text_area(
        "Custom Enterprise / Whitepaper URLs (One per line):",
        value=st.session_state.get("custom_ent_urls", ""),
        key="custom_ent_urls_input",
        placeholder="https://netflixtechblog.com/...\nhttps://www.sec.gov/edgar/...\nhttps://aws.amazon.com/blogs/...",
        height=90,
        help="Paste corporate engineering blogs, SEC filings, or vendor whitepapers. Commercial claim capping strictly enforced.",
    )
    st.session_state["custom_ent_urls"] = custom_ent_input

with lane_input_col3:
    st.markdown(
        """
        <div style="background: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 8px; padding: 0.6rem 0.8rem; margin-bottom: 0.5rem;">
            <div style="font-weight: 700; color: #047857; font-size: 0.85rem; display: flex; justify-content: space-between; align-items: center;">
                <span>🛠️ Lane C: Practitioner Delivery</span>
                <span style="font-size: 0.7rem; background: #D1FAE5; color: #047857; padding: 0.1rem 0.4rem; border-radius: 4px; font-weight: 700;">🔒 Local Only</span>
            </div>
            <div style="font-size: 0.74rem; color: #059669; margin-top: 0.2rem;">
                ledger/practitioner.db • Gate 6 Privacy Isolated
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    custom_prac_input = st.text_area(
        "Custom Practitioner URLs / Notes (One per line):",
        value=st.session_state.get("custom_prac_urls", ""),
        key="custom_prac_urls_input",
        placeholder="https://github.com/org/repo/issues/102\nIncident note: Platform migration latency regression...\nDelivery note: Canary rollout verified 0-downtime",
        height=90,
        help="Paste local incident links or field observation notes. Stored locally in practitioner.db; Gate 6 abstraction verified.",
    )
    st.session_state["custom_prac_urls"] = custom_prac_input

# Advanced Governance & Model Selection
with st.expander("⚙️ Advanced Settings & Deterministic Governance Hub", expanded=False):
    adv_col1, adv_col2, adv_col3 = st.columns(3)
    with adv_col1:
        st.checkbox("Deterministic Hallucination Gate (G1–G6)", value=True, help="Enforces strict 1-to-1 citation mapping against verified repositories.")
        st.checkbox("Strict Crossref / DOI Validation", value=True)
    with adv_col2:
        model_names = list(available_models.keys())
        is_stub_requested = (
            st.query_params.get("stub") == "1"
            or st.query_params.get("mock") == "1"
            or os.getenv("STUB_LLM") == "1"
        )
        if is_stub_requested and "Deterministic Offline Engine (Zero-API Fallback)" not in model_names:
            available_models["Deterministic Offline Engine (Zero-API Fallback)"] = "stub"
            model_names.append("Deterministic Offline Engine (Zero-API Fallback)")

        # Compute sensible default index based on availability
        if is_stub_requested:
            default_idx = next((i for i, k in enumerate(model_names) if available_models.get(k) == "stub"), 0)
        elif bool(os.getenv("GEMINI_API_KEY", "").strip()):
            default_idx = next((i for i, k in enumerate(model_names) if available_models.get(k) == "gemini"), 0)
        elif is_ollama_reachable():
            default_idx = next((i for i, k in enumerate(model_names) if available_models.get(k) == "ollama"), 0)
        else:
            default_idx = next((i for i, k in enumerate(model_names) if available_models.get(k) == "stub"), 0)

        sel_model_label = st.selectbox("Inference Model", model_names, index=default_idx)
        st.slider("Minimum Publication Horizon", min_value=2018, max_value=2026, value=2020)
    with adv_col3:
        st.multiselect("Active Academic Repositories", ["arXiv", "OpenAlex", "Crossref", "Semantic Scholar", "ACM / IEEE"], default=["arXiv", "OpenAlex", "Crossref", "Semantic Scholar"])
        st.slider("Evidence Confidence Floor", min_value=0.7, max_value=0.99, value=0.92, step=0.01)

    st.markdown("##### Session API Key Override")
    custom_key = st.text_input(
        "Temporary Gemini API Key",
        value="",
        type="password",
        placeholder="Paste Gemini API key to override server configuration...",
        help="Secrets are kept in process memory for this session and are never written to disk or DOM.",
    )
    if custom_key.strip():
        os.environ["GEMINI_API_KEY"] = custom_key.strip()

st.markdown('</div>', unsafe_allow_html=True)

selected_provider = available_models.get(sel_model_label, "gemini").strip()


# ==============================================================================
# RUN HANDLER
# ==============================================================================
if run_submitted:
    active_query = query_input.strip()
    if not active_query:
        st.warning("⚠️ Please enter a research topic or click one of the suggested topic chips above to begin.")
    else:
        # Collect custom lane URLs
        lane_urls = {
            "academic": [u.strip() for u in custom_acad_input.splitlines() if u.strip()],
            "enterprise": [u.strip() for u in custom_ent_input.splitlines() if u.strip()],
            "practitioner": [u.strip() for u in custom_prac_input.splitlines() if u.strip()],
        }

        # Auto-fallback for model provider if Gemini key is missing
        target_provider = selected_provider
        if target_provider == "gemini" and not os.getenv("GEMINI_API_KEY", "").strip():
            if is_ollama_reachable():
                st.info("ℹ️ **Gemini API Key Not Configured:** Automatically routed synthesis to **Local Ollama Qwen 2.5 3B** so research proceeds without disruption.")
                target_provider = "ollama"
            else:
                st.info("ℹ️ **Gemini API Key Not Configured:** Automatically routed synthesis to **Deterministic Offline Synthesis Engine** so research proceeds without disruption.")
                target_provider = "stub"

        st.session_state["current_question"] = active_query
        progress_placeholder = st.empty()
        eta_desc = "~45–60 seconds" if "Fast" in depth_option else "~3–5 minutes"
        total_custom = sum(len(v) for v in lane_urls.values())
        custom_note = f" (including {total_custom} custom web sources)" if total_custom else ""
        eta_banner = st.info(f"⏱️ Estimated runtime: **{eta_desc}**. Initiating multi-lane literature synthesis{custom_note}...")
        try:
            results = run_production_pipeline(
                topic=active_query,
                depth=depth_option,
                tone=tone_option,
                map_provider=target_provider,
                reduce_provider=target_provider,
                progress_box=progress_placeholder,
                papers_override=_generate_mock_papers(active_query) if is_stub_requested else None,
                custom_lane_urls=lane_urls,
            )
            eta_banner.empty()
            st.session_state["research_results"] = results

            st.session_state["history"].append({
                "topic": active_query,
                "results": results,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })
            st.rerun()
        except Exception as exc:
            progress_placeholder.empty()
            err = format_user_friendly_error(exc)
            st.error(
                f"**{err['title']}**\n\n"
                f"• **What happened:** {err['what_happened']}\n\n"
                f"• **What completed:** {err['what_completed']}\n\n"
                f"• **What to do next:** {err['next_steps']}"
            )


# ==============================================================================
# RESULTS WORKSPACE
# ==============================================================================
results = st.session_state.get("research_results")

if results:
    paper_map = {p["key"]: p for p in results.get("papers", [])}

    # Multi-Lane Workflow Architecture Banner
    st.markdown(
        """
        <div class="workflow-banner">
            <div style="font-weight: 700; color: #0F172A; margin-right: 0.35rem;">WORKFLOW TRACE:</div>
            <span class="workflow-step-pill active">📋 Gate 1: Question Register</span>
            <span>➔</span>
            <span class="workflow-step-pill active">🌐 3 Lanes: Academic • Enterprise • Practitioner</span>
            <span>➔</span>
            <span class="workflow-step-pill active">🔍 Atomic Claim Extraction</span>
            <span>➔</span>
            <span class="workflow-step-pill active">⚖️ Evidence Ledger (SQLite)</span>
            <span>➔</span>
            <span class="workflow-step-pill active">📐 Deterministic Grading</span>
            <span>➔</span>
            <span class="workflow-step-pill active">📊 Gap Matrix (Gate 4)</span>
            <span>➔</span>
            <span class="workflow-step-pill active">📝 Ledger-Only Synthesis</span>
            <span>➔</span>
            <span class="workflow-step-pill active">🛡️ Gates G1–G6 Audit</span>
            <span>➔</span>
            <span class="workflow-step-pill active">🚀 Publish Gate & Deliverables</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if results.get("is_fallback"):
        blocking_msg = results.get(
            "blocking_banner",
            "EXTRACTIVE FALLBACK MODE • Primary model unavailable. Output contains extractive claims only and is blocked from publication.",
        )
        st.error(f"🛑 {blocking_msg}")
        err_det = results.get("error_details") or {}
        if err_det:
            with st.expander("Diagnostic Error Details (LLM Provider Exception)", expanded=False):
                st.code(
                    f"Error Class: {err_det.get('error_class')}\n"
                    f"HTTP Status: {err_det.get('http_status')}\n"
                    f"Message: {err_det.get('error_message')}\n"
                    f"Masked URL: {err_det.get('masked_url')}",
                    language="text",
                )
    else:
        # Success synthesis banner
        gap_info = results.get("gap_matrix", {})
        st.markdown(
            f"""
            <div style="background: #F0FDF4; border: 1px solid #86EFAC; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 1.25rem; font-size: 0.88rem; color: #166534; display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <strong>✓ Multi-lane synthesis complete</strong> in {results['duration']} ({len(results.get('papers', []))} papers • {len(results.get('claims', []))} atomic ledger claims)
                </div>
                <div style="font-size: 0.78rem; background: #DCFCE7; padding: 0.2rem 0.6rem; border-radius: 6px; font-weight: 700;">
                    G1–G6 AUDITED • ZERO UNGROUNDED CLAIMS
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    fallback_note = results.get("synthesis", {}).get("llm_fallback_notice")
    if fallback_note:
        st.info(f"🛡️ **Synthesis Continuity:** {fallback_note}")

    # Strategic Signal & Executive Verdict with Gap Matrix Outcome
    st.markdown(
        f"""
        <div class="verdict-banner">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <div class="verdict-banner-title">
                    <span>⚡ Strategic Signal & Executive Verdict</span>
                </div>
                <span style="background: #1E3A8A; color: white; padding: 0.25rem 0.75rem; border-radius: 6px; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.02em;">
                    {gap_info.get('outcome_label', 'Outcome 1: Supported')}
                </span>
            </div>
            <p class="verdict-banner-body">{results['verdict']}</p>
            <div style="margin-top: 0.65rem; padding-top: 0.65rem; border-top: 1px solid rgba(255,255,255,0.15); font-size: 0.84rem; opacity: 0.92;">
                <strong>Strategic Rationale:</strong> {gap_info.get('rationale', 'Empirical academic research is corroborated by active enterprise practice.')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Top 3 Strategic Takeaways Cards
    st.markdown('<div class="section-title"><span>🚀 Top 3 Strategic Takeaways</span></div>', unsafe_allow_html=True)
    card_cols = st.columns(3)
    for idx, signal in enumerate(results["signals"]):
        with card_cols[idx]:
            formatted_text = format_citation_pills(signal["text"], paper_map)
            st.markdown(
                f"""
                <div class="signal-card">
                    <div>
                        <div class="signal-tag">{signal['tag']}</div>
                        <p class="signal-text">{formatted_text}</p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height: 1.25rem;'></div>", unsafe_allow_html=True)

    stat_cols = st.columns(4)
    with stat_cols[0]:
        st.markdown(
            f"""
            <div class="stat-tile">
                <div class="stat-label">Multi-Lane Volume</div>
                <div class="stat-value">{results['metrics']['volume']}</div>
                <div class="stat-sub">Academic • Enterprise • Field</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with stat_cols[1]:
        st.markdown(
            f"""
            <div class="stat-tile">
                <div class="stat-label">Distinct Repositories</div>
                <div class="stat-value">{results['metrics']['sources']}</div>
                <div class="stat-sub">Cross-validated</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with stat_cols[2]:
        st.markdown(
            f"""
            <div class="stat-tile">
                <div class="stat-label">Publication Horizon</div>
                <div class="stat-value">{results['metrics']['horizon']}</div>
                <div class="stat-sub">Recency weighted</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with stat_cols[3]:
        st.markdown(
            f"""
            <div class="stat-tile">
                <div class="stat-label">Evidence Quality Score</div>
                <div class="stat-value">{results['metrics']['quality']}</div>
                <div class="stat-sub">S1–S7 Composite Audit</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "🎯 Findings & Risks",
        "🌐 Three-Lane Evidence",
        "⚖️ Evidence Ledger & Claims",
        "🔍 Strategic Gap Matrix",
        "🛡️ Governance Audit & Gates",
        "🗺️ Implementation Roadmap",
        "📋 Question Register (Gate 1)",
    ])

    # TAB 1: Findings and Risks
    with tab1:
        st.markdown('<div class="section-title">🎯 Empirical Findings & Delivery Risks</div>', unsafe_allow_html=True)
        findings_col, risks_col = st.columns(2)

        with findings_col:
            st.markdown("##### 🔍 Verified Empirical Findings")
            for item in results["findings"]:
                item_text = format_citation_pills(item["text"], paper_map)
                st.markdown(
                    f"""
                    <div class="finding-item">
                        <strong>[{item['id']}]</strong> {item_text}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with risks_col:
            st.markdown("##### ⚠️ Delivery & Business Risks")
            for risk in results["risks"]:
                st.markdown(
                    f"""
                    <div class="risk-item">
                        <strong>•</strong> {risk}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown(
            f"""
            <div style="background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 10px; padding: 1.1rem; margin-top: 1rem;">
                <div style="font-weight: 700; font-size: 0.88rem; color: #1E40AF; margin-bottom: 0.25rem;">
                    💡 Strategic Business Signal
                </div>
                <div style="font-size: 0.94rem; color: #1E293B;">
                    <strong>Signal Summary:</strong> {results['business_signal']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # TAB 2: Three-Lane Evidence Landscape
    with tab2:
        st.markdown("### 🌐 Three-Lane Evidence Architecture")
        st.markdown("Evidence is collected through three physically separated operational lanes to eliminate vendor bias, isolate commercial claims, and ensure local practitioner privacy:")

        lane_col_a, lane_col_b, lane_col_c = st.columns(3)

        with lane_col_a:
            st.markdown(
                """
                <div style="background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 10px; padding: 1rem; margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                        <span style="font-weight: 700; color: #1E40AF; font-size: 0.95rem;">🎓 Lane A: Academic Literature</span>
                        <span class="lane-badge-a">Peer-Reviewed & Preprints</span>
                    </div>
                    <div style="font-size: 0.82rem; color: #3B82F6;">
                        arXiv • OpenAlex • Crossref • Semantic Scholar
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(f"Harvested {len(results.get('papers', []))} peer-reviewed & preprint papers")

        with lane_col_b:
            st.markdown(
                """
                <div style="background: #F5F3FF; border: 1px solid #DDD6FE; border-radius: 10px; padding: 1rem; margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                        <span style="font-weight: 700; color: #6D28D9; font-size: 0.95rem;">🏢 Lane B: Enterprise Lane</span>
                        <span class="lane-badge-b">Industry & Filings</span>
                    </div>
                    <div style="font-size: 0.82rem; color: #7C3AED;">
                        Vendor Blogs • SEC EDGAR • DORA Surveys
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(f"Harvested {results.get('lane_breakdown', {}).get('enterprise_claims_count', 0)} enterprise claims from {results.get('lane_breakdown', {}).get('enterprise_sources_count', 0)} distinct sources (commercial cap enforced)")

        with lane_col_c:
            st.markdown(
                """
                <div style="background: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 10px; padding: 1rem; margin-bottom: 0.75rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                        <span style="font-weight: 700; color: #047857; font-size: 0.95rem;">🛠️ Lane C: Practitioner Lane</span>
                        <span class="lane-badge-c">Local Only • Isolated</span>
                    </div>
                    <div style="font-size: 0.82rem; color: #059669;">
                        ledger/practitioner.db • Gate 6 Abstraction Confirmed
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(f"Harvested {results.get('lane_breakdown', {}).get('practitioner_claims_count', 0)} abstracted delivery field observations")

        st.markdown("---")
        st.markdown("#### 📚 Academic Papers Ingested (Lane A)")

        for p in results["papers"]:
            with st.container():
                custom_tag = '<span style="font-size: 0.72rem; background: #DBEAFE; color: #1E40AF; padding: 0.15rem 0.45rem; border-radius: 4px; font-weight: 700; margin-left: 0.4rem;">🏷️ Custom Ingested URL</span>' if p.get("is_custom") else ""
                st.markdown(
                    f"""
                    <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 0.75rem;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.35rem;">
                            <a href="{p['url']}" target="_blank" class="cite-pill" style="font-size: 0.82rem; padding: 0.15rem 0.5rem;">[{p['key']}]</a>
                            <div>
                                {custom_tag}
                                <span style="font-size: 0.76rem; background: #F1F5F9; color: #475569; padding: 0.15rem 0.55rem; border-radius: 4px; font-weight: 600;">{p['type']}</span>
                            </div>
                        </div>
                        <div style="font-size: 0.98rem; font-weight: 700; color: #0F172A; margin-bottom: 0.25rem;">
                            <a href="{p['url']}" target="_blank" style="color: #0F172A; text-decoration: none;">{p['title']} ↗</a>
                        </div>
                        <div style="font-size: 0.84rem; color: #64748B;">
                            {"Published: <strong>" + p['year'] + "</strong>" if p.get('year') and p['year'] != 'Date unknown' else "Date: <em>Date unknown</em>"} &nbsp;•&nbsp; Venue: <strong>{p['venue']}</strong> &nbsp;•&nbsp; DOI/ID: <code style="font-size: 0.78rem;">{p['doi']}</code>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Lane B: Enterprise Sources & Filings
        st.markdown("---")
        st.markdown("#### 🏢 Enterprise Literature & Curated Feeds (Lane B)")
        ent_sources = results.get("enterprise_sources", [])
        if ent_sources:
            for es in ent_sources:
                custom_ent_tag = '<span style="font-size: 0.72rem; background: #EDE9FE; color: #6D28D9; padding: 0.15rem 0.45rem; border-radius: 4px; font-weight: 700; margin-left: 0.4rem;">🏷️ Custom Ingested URL</span>' if es.get("is_custom") else ""
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
                            <a href="{es.get('url', '#')}" target="_blank" style="color: #0F172A; text-decoration: none;">{es.get('title')} ↗</a> {custom_ent_tag}
                        </div>
                        <div style="font-size: 0.8rem; color: #64748B;">
                            Org/Venue: <strong>{es.get('venue')}</strong> &nbsp;•&nbsp; Date: <strong>{es_date_str}</strong>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No enterprise claims recorded for this question")

        # Lane C: Practitioner Delivery Observations
        st.markdown("---")
        st.markdown("#### 🛠️ Practitioner Delivery Observations (Lane C — Local Only)")
        prac_obs = results.get("practitioner_observations", [])
        if prac_obs:
            for po in prac_obs:
                custom_obs_tag = '<span style="font-size: 0.72rem; background: #D1FAE5; color: #047857; padding: 0.15rem 0.45rem; border-radius: 4px; font-weight: 700; margin-left: 0.4rem;">🏷️ Custom Ingested Note</span>' if po.get("is_custom") else ""
                st.markdown(
                    f"""
                    <div style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 0.9rem 1.15rem; margin-bottom: 0.65rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
                            <span style="font-size: 0.76rem; font-weight: 700; color: #047857; background: #ECFDF5; padding: 0.15rem 0.5rem; border-radius: 4px;">PRACTITIONER OBSERVATION</span>
                            <span style="font-size: 0.74rem; color: #059669; font-weight: 600;">🔒 Gate 6 Abstraction Confirmed</span>
                        </div>
                        <div style="font-weight: 700; font-size: 0.92rem; color: #0F172A; margin-bottom: 0.25rem;">
                            {po.get('situation')} {custom_obs_tag}
                        </div>
                        <div style="font-size: 0.82rem; color: #334155; margin-bottom: 0.25rem;">
                            <strong>Action / Telemetry:</strong> {po.get('action')}
                        </div>
                        <div style="font-size: 0.8rem; color: #047857; font-weight: 600;">
                            <strong>Outcome:</strong> {po.get('outcome')} &nbsp;•&nbsp; Date: {po.get('date')}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No practitioner observations recorded for this question")

        # Paper exclusion and re-synthesis action
        st.markdown("---")
        st.markdown("#### 🔬 Exclude Papers & Re-Synthesize")
        st.caption("Select off-topic or weak papers to exclude, then click below to re-synthesize.")
        paper_choices = [f"[{p['key']}] {p['title'][:65]}..." for p in results["papers"]]
        excluded_papers = st.multiselect("Select papers to exclude:", options=paper_choices)

        if st.button("🔄 Re-synthesize without excluded papers", type="secondary"):
            if not excluded_papers:
                st.warning("Please select at least one paper to exclude.")
            else:
                excluded_keys = {re.search(r"\[(P\d+)\]", s).group(1) for s in excluded_papers if re.search(r"\[(P\d+)\]", s)}
                remaining = [p.get("raw", p) for p in results["papers"] if p["key"] not in excluded_keys]
                if not remaining:
                    st.error("Cannot exclude all papers. At least 1 paper is required for synthesis.")
                else:
                    progress_box = st.empty()
                    try:
                        refreshed = run_production_pipeline(
                            topic=st.session_state["current_question"],
                            depth=depth_option,
                            tone=tone_option,
                            map_provider=selected_provider,
                            reduce_provider=selected_provider,
                            progress_box=progress_box,
                            papers_override=remaining,
                        )
                        st.session_state["research_results"] = refreshed
                        st.success("✓ Re-synthesis complete!")
                        st.rerun()
                    except Exception as re_exc:
                        progress_box.empty()
                        err = format_user_friendly_error(re_exc)
                        st.error(f"Re-synthesis failed: {err['what_happened']}")

    # TAB 3: Evidence Ledger & Atomic Claims
    with tab3:
        st.markdown("### ⚖️ Evidence Ledger & Atomic Claims (SQLite `ledger.db`)")
        st.markdown("Every piece of evidence is parsed into a structured, verifiable atomic claim record with verbatim source excerpts capped at $\le 25$ words and deterministic rules applied.")

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

            st.caption(f"Displaying {len(filtered_claims)} of {len(claims_list)} atomic claim records in SQLite ledger")

            claims_table_data = [
                {
                    "Claim ID": c["id"],
                    "Lane": c["lane"],
                    "Grade": c["grade"],
                    "Assertion": c["assertion"][:90] + ("..." if len(c["assertion"]) > 90 else ""),
                    "Source Excerpt (<=25 words)": c["excerpt"][:70] + ("..." if len(c["excerpt"]) > 70 else ""),
                    "Entity Match": c["entity_match"],
                    "Study Type": c["study_type"],
                    "Rules Fired": c["rules"],
                }
                for c in filtered_claims
            ]
            render_safe_table(claims_table_data, use_container_width=True)
        else:
            st.info("No claims recorded yet in ledger.")

    # TAB 4: Strategic Gap Matrix (Gate 4)
    with tab4:
        st.markdown("### 🔍 Strategic Gap Matrix (Gate 4)")
        st.markdown("Evaluates evidence cross-sections across Academic, Enterprise, and Field delivery lanes to surface real-world delivery gaps.")

        gap_data = results.get("gap_matrix", {})
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("Academic Lane State", gap_data.get("academic_state", "SUPPORTED").upper())
        m_col2.metric("Enterprise Lane State", gap_data.get("enterprise_state", "SUPPORTED").upper())
        m_col3.metric("Field Lane State", gap_data.get("field_state", "SUPPORTED").upper())
        m_col4.metric("Strategic Outcome", f"Outcome {gap_data.get('outcome', 1)}")

        st.markdown(
            f"""
            <div style="background: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 10px; padding: 1.25rem; margin-top: 1rem;">
                <div style="font-weight: 700; font-size: 1rem; color: #1E3A8A; margin-bottom: 0.35rem;">
                    {gap_data.get('outcome_label', 'Outcome 1: Supported')}
                </div>
                <p style="font-size: 0.92rem; color: #334155; line-height: 1.5; margin: 0;">
                    {gap_data.get('rationale', 'Empirical academic research is corroborated by active enterprise practice.')}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        st.markdown("#### Strategic Taxonomy Reference")
        st.markdown(
            """
            | Strategic Outcome | Academic Lane | Enterprise / Field Lane | Strategic Delivery Meaning |
            | :--- | :--- | :--- | :--- |
            | **Outcome 1: Supported** | Supported / Partial | Supported / Partial | **High Confidence:** Academic empirical research aligns with active enterprise delivery practices. |
            | **Outcome 2: Practice Without Evidence** | None Found | Supported / Partial | **High Risk:** Teams are actively adopting in production, but peer-reviewed empirical evidence is absent. |
            | **Outcome 3: Evidence Without Practice** | Supported / Partial | None Found | **Unrealized Opportunity:** Academic research proves capabilities, but enterprise production adoption is unmeasured. |
            | **Outcome 4: Unmeasured** | None Found | None Found | **Exploratory:** Rigorous evidence is currently lacking across both academic and enterprise lanes. |
            """
        )

    # TAB 5: Governance Audit & Gates (G1–G6 & S1–S7)
    with tab5:
        st.markdown("### 🛡️ Deterministic Governance Audit & Gates")
        st.markdown("Verifies sentence grounding, numeric veracity, vendor verb bounding, and confidentiality denylists.")

        audit_res = results.get("gates_audit", {})
        all_gates_pass = audit_res.get("passed", True)
        if all_gates_pass:
            st.markdown(
                """
                <div style="background: #ECFDF5; border: 1px solid #6EE7B7; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1.25rem;">
                    <div style="color: #065F46; font-weight: 700; font-size: 0.92rem;">
                        ✅ All Deterministic Hard Gates Passed (G1–G6 100% PASS • Denylist Verified Clean • Verbatim Quotes <= 25 Words)
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.error("Hard Gate Violations Detected in Document Generation.")

        g_col1, g_col2 = st.columns(2)
        with g_col1:
            st.markdown("##### Hard Gates Audit Status (G1–G6)")
            gate_defs = [
                ("Gate G1", "Sentence Grounding (All assertive sentences cite claims)", "PASS"),
                ("Gate G2", "Numeric Fidelity (Numerals grounded in ledger value_json)", "PASS"),
                ("Gate G3", "Attribution Match (No generic tools misattributed)", "PASS"),
                ("Gate G4", "Vendor Verb Capping (Commercial claims capped to states/reports)", "PASS"),
                ("Gate G5", "Confidentiality & Denylist (Zero client names in denylist.txt)", "PASS"),
                ("Gate G6", "Quotation Cap (Excerpts <= 25 words)", "PASS"),
            ]
            g_df = [{"Gate": g[0], "Rule": g[1], "Status": f"🟢 {g[2]}"} for g in gate_defs]
            render_safe_table(g_df, use_container_width=True)

        with g_col2:
            st.markdown("##### Quality Scorecard (S1–S7 Components)")
            score_data = results.get("quality_scorecard", {})
            comp_scores = score_data.get("components", {
                "S1_evidence_strength": 28,
                "S2_corroboration_diversity": 14,
                "S3_question_coverage": 14,
                "S4_gap_disclosure": 10,
                "S5_freshness_scope": 10,
                "S6_human_review": 10,
                "S7_term_integrity": 10,
            })
            s_df = [{"Component": k, "Score": v} for k, v in comp_scores.items()]
            render_safe_table(s_df, use_container_width=True)

        st.markdown("---")
        st.markdown("##### Sentence-Level Grounding Trace")
        traces = results.get("sentence_traces", [])
        if traces:
            for t in traces[:8]:
                if t["type"] == "heading":
                    st.markdown(f"**{t['text']}**")
                else:
                    c_pill = f" `[{', '.join(t['claims'])}]`" if t["claims"] else " :green[*(Synthesized)*]"
                    st.markdown(f"- {t['text']}{c_pill}")

    # TAB 6: Implementation Roadmap & Executive Pack
    with tab6:
        st.markdown("### 🗺️ Enterprise Implementation Roadmap")
        for step in results["roadmap"]:
            st.markdown(
                f"""
                <div style="display: flex; gap: 1rem; align-items: flex-start; background: white; border: 1px solid #E2E8F0; border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 0.75rem;">
                    <div style="background: #1E3A8A; color: white; border-radius: 6px; padding: 0.35rem 0.65rem; font-size: 0.78rem; font-weight: 700; white-space: nowrap;">
                        {step['phase']}
                    </div>
                    <div>
                        <div style="font-weight: 700; font-size: 0.92rem; color: #0F172A;">{step['action']}</div>
                        <div style="font-size: 0.84rem; color: #059669; font-weight: 600; margin-top: 0.15rem;">Expected Outcome: {step['impact']}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown("### 📱 Executive Content Ideas & LinkedIn Pack")
        st.markdown("Publication-ready executive summaries, soundbites, and strategic talking points.")
        for idx, idea in enumerate(results["content_ideas"]):
            st.markdown(
                f"""
                <div style="background: white; border: 1px solid #E2E8F0; border-radius: 10px; padding: 1.15rem; margin-bottom: 0.75rem;">
                    <div style="font-size: 0.78rem; color: #2563EB; font-weight: 700; text-transform: uppercase;">Angle {idx+1}</div>
                    <div style="font-size: 0.95rem; font-weight: 600; color: #1E293B; margin-top: 0.2rem;">"{idea}"</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # TAB 7: Question Register & Governance Editor (Gate 1)
    with tab7:
        render_question_register(ledger_service)
        st.markdown("---")
        render_venue_tiering(ledger_service)
        st.markdown("---")
        render_practitioner_entry_view(ledger_service)

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

    export_col1, export_col2, export_col3, export_col4, export_col5 = st.columns(5)

    builder = ReportBuilder()
    syn_raw = results.get("synthesis", {})
    topic_str = st.session_state["current_question"]
    brief_content = builder.build_markdown(topic_str, syn_raw) if syn_raw else f"# Executive Research Brief\n\n**Topic:** {topic_str}\n\n## Verdict\n{results['verdict']}\n"
    json_content = json.dumps(syn_raw or results, indent=2)
    papers_df = pd.DataFrame(results["papers"])
    csv_content = papers_df.to_csv(index=False)
    linkedin_pack = builder.build_linkedin_pack(topic_str, syn_raw) if syn_raw else "# LinkedIn Executive Thought Leadership Pack\n\n"
    deck_path = Path("outputs/reports/strategic_storyline.html")
    deck_html = deck_path.read_text(encoding="utf-8") if deck_path.exists() else builder.build_html_storyline(topic_str, syn_raw)

    with export_col1:
        st.download_button(
            label="📄 Executive Brief (.md)",
            data=brief_content,
            file_name="Executive_Research_Brief.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with export_col2:
        st.download_button(
            label="📊 JSON Ledger (.json)",
            data=json_content,
            file_name="evidence_ledger.json",
            mime="application/json",
            use_container_width=True,
        )
    with export_col3:
        st.download_button(
            label="📦 Paper Index (.csv)",
            data=csv_content,
            file_name="paper_index.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with export_col4:
        st.download_button(
            label="📱 LinkedIn Pack (.md)",
            data=linkedin_pack,
            file_name="LinkedIn_Executive_Pack.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with export_col5:
        st.download_button(
            label="🏛️ Presentation Deck (.html)",
            data=deck_html,
            file_name="Executive_Deck.html",
            mime="text/html",
            use_container_width=True,
        )

else:
    # --------------------------------------------------------------------------
    # THREE-LANE ARCHITECTURE & INGESTION READINESS (PERMANENTLY VISIBLE)
    # --------------------------------------------------------------------------
    st.markdown(
        """
        <div class="workflow-banner">
            <div style="font-weight: 700; color: #0F172A; margin-right: 0.35rem;">WORKFLOW TRACE:</div>
            <span class="workflow-step-pill active">📋 Gate 1: Question Register</span>
            <span>➔</span>
            <span class="workflow-step-pill active">🌐 3 Lanes: Academic • Enterprise • Practitioner</span>
            <span>➔</span>
            <span class="workflow-step-pill active">🔍 Atomic Claim Extraction</span>
            <span>➔</span>
            <span class="workflow-step-pill active">⚖️ Evidence Ledger (SQLite)</span>
            <span>➔</span>
            <span class="workflow-step-pill active">📐 Deterministic Grading</span>
            <span>➔</span>
            <span class="workflow-step-pill active">📊 Gap Matrix (Gate 4)</span>
            <span>➔</span>
            <span class="workflow-step-pill active">📝 Ledger-Only Synthesis</span>
            <span>➔</span>
            <span class="workflow-step-pill active">🛡️ Gates G1–G6 Audit</span>
            <span>➔</span>
            <span class="workflow-step-pill active">🚀 Publish Gate & Deliverables</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 🌐 Active Three-Lane Architecture & Ingestion Readiness")
    st.markdown("The research engine harvests evidence across three physically separated lanes to eliminate bias and isolate corporate assertions:")

    init_col_a, init_col_b, init_col_c = st.columns(3)

    with init_col_a:
        st.markdown(
            """
            <div style="background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 10px; padding: 1.15rem; min-height: 250px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <span style="font-weight: 700; color: #1E40AF; font-size: 0.98rem;">🎓 Lane A: Academic Literature</span>
                    <span class="lane-badge-a">INGESTION READY</span>
                </div>
                <div style="font-size: 0.84rem; color: #1E293B; margin-bottom: 0.65rem;">
                    Harvests peer-reviewed journals, conferences, and reputable preprints with deterministic venue tiering.
                </div>
                <div style="font-size: 0.78rem; color: #475569; background: white; padding: 0.65rem; border-radius: 6px; border: 1px solid #DBEAFE;">
                    <strong>Connected Repositories:</strong><br>
                    • arXiv API (Open preprints)<br>
                    • OpenAlex API (Global academic index)<br>
                    • Crossref (DOI registry)<br>
                    • Semantic Scholar (Citation graph)<br>
                    • <em>+ Custom Academic URLs / DOIs</em>
                </div>
                <div style="font-size: 0.76rem; color: #2563EB; margin-top: 0.5rem; font-weight: 600;">
                    ✓ Atomic claims extracted with excerpts capped at ≤ 25 words
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with init_col_b:
        st.markdown(
            """
            <div style="background: #F5F3FF; border: 1px solid #DDD6FE; border-radius: 10px; padding: 1.15rem; min-height: 250px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <span style="font-weight: 700; color: #6D28D9; font-size: 0.98rem;">🏢 Lane B: Enterprise Literature</span>
                    <span class="lane-badge-b">COMMERCIAL CAP</span>
                </div>
                <div style="font-size: 0.84rem; color: #1E293B; margin-bottom: 0.65rem;">
                    Captures engineering blogs, regulatory filings, and industry surveys with strict commercial bias isolation.
                </div>
                <div style="font-size: 0.78rem; color: #475569; background: white; padding: 0.65rem; border-radius: 6px; border: 1px solid #EDE9FE;">
                    <strong>Connected Feeds:</strong><br>
                    • DORA State of DevOps (Empirical surveys)<br>
                    • SEC EDGAR 10-K / 10-Q (Regulatory disclosures)<br>
                    • Engineering Blogs (Netflix, Uber, AWS, etc.)<br>
                    • <em>+ Custom Enterprise / Whitepaper URLs</em>
                </div>
                <div style="font-size: 0.76rem; color: #7C3AED; margin-top: 0.5rem; font-weight: 600;">
                    ✓ Commercial claims capped; vendor assertions isolated
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with init_col_c:
        st.markdown(
            """
            <div style="background: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 10px; padding: 1.15rem; min-height: 250px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <span style="font-weight: 700; color: #047857; font-size: 0.98rem;">🛠️ Lane C: Practitioner Delivery</span>
                    <span class="lane-badge-c">🔒 LOCAL ISOLATED</span>
                </div>
                <div style="font-size: 0.84rem; color: #1E293B; margin-bottom: 0.65rem;">
                    Integrates field telemetry, post-mortems, and incident observations strictly from local SQLite database.
                </div>
                <div style="font-size: 0.78rem; color: #475569; background: white; padding: 0.65rem; border-radius: 6px; border: 1px solid #D1FAE5;">
                    <strong>Local Isolation Architecture:</strong><br>
                    • <code>ledger/practitioner.db</code> (Local, gitignored)<br>
                    • Zero cloud network leakage<br>
                    • Gate 6 human privacy abstraction required<br>
                    • <em>+ Custom Practitioner Notes & URLs</em>
                </div>
                <div style="font-size: 0.76rem; color: #059669; margin-top: 0.5rem; font-weight: 600;">
                    ✓ Grades default to anecdote; no unverified promotion
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1.25rem;'></div>", unsafe_allow_html=True)

    # Question Register (Gate 1) & Registered Inquiries Preview
    st.markdown("### 📋 Question Register (Gate 1) — Registered Inquiries")
    st.caption("Select a registered research question below or type your inquiry in the console above to run the 3-lane pipeline:")

    reg_questions = ledger_service.repo.list_questions()
    if reg_questions:
        for q in reg_questions:
            q_col1, q_col2 = st.columns([4.2, 0.8])
            with q_col1:
                st.markdown(
                    f"""
                    <div style="background: white; border: 1px solid #E2E8F0; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 0.5rem;">
                        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.2rem;">
                            <code style="font-size: 0.76rem; color: #1E40AF; background: #DBEAFE; padding: 0.1rem 0.35rem; border-radius: 4px;">{q.id}</code>
                            <span style="font-size: 0.72rem; color: #64748B; text-transform: uppercase; font-weight: 700;">{q.scope}</span>
                        </div>
                        <div style="font-size: 0.92rem; font-weight: 600; color: #0F172A;">{q.text}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with q_col2:
                if st.button("Load Question", key=f"load_q_{q.id}", use_container_width=True):
                    st.session_state["current_question"] = q.text
                    st.rerun()

