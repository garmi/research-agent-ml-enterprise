"""Tests for Slice S18: page order, runs that survive a redeploy, dark mode, font, and the AI Guruji brand.

Requirements:
1. The Gate 1 question register sits inside the question step, before "3. Run" (Run is the page's
   last step); it no longer renders below the page.
2. The run history directory comes from RESEARCH_RUNS_DIR (a mounted Cloud Storage volume on Cloud Run),
   defaulting to outputs/runs, and a finished run read back from disk by a fresh process still renders.
3. A sidebar "Dark mode" switch applies a dark palette (CSS variables, page, sidebar, inputs, tabs and
   cards); the choice is kept in the URL (?theme=dark) so it survives a reload. Light adds nothing.
4. The page font is "Anthropic Sans" where the viewer has it installed, with Inter (served from Google
   Fonts) as the fallback; Anthropic Sans itself is never downloaded from a URL.
5. The site is branded "AI Guruji" (browser tab, header and sidebar).
"""

from __future__ import annotations

import json
from pathlib import Path

WEB = Path("web_app.py")
INTAKE = Path("src/ui/intake_view.py")


def _web() -> str:
    return WEB.read_text(encoding="utf-8")


# ------------------------------------------------------------------------------
# Test 1: Gate 1 register before Run
# ------------------------------------------------------------------------------
def test_question_register_before_run():
    intake = INTAKE.read_text(encoding="utf-8")
    assert "def render_intake_view(before_run" in intake
    assert intake.index("before_run()") < intake.index('st.markdown("### 3. Run")')
    web = _web()
    assert "render_intake_view(before_run=render_question_register)" in web
    assert "def render_question_register()" in web
    assert "BEFORE A RUN: the question register" not in web


# ------------------------------------------------------------------------------
# Test 2: Runs survive a redeploy
# ------------------------------------------------------------------------------
def test_runs_dir_is_configurable():
    web = _web()
    assert 'os.getenv("RESEARCH_RUNS_DIR")' in web
    deploy = Path("CLOUD_RUN_DEPLOY.md").read_text(encoding="utf-8")
    assert "RESEARCH_RUNS_DIR" in deploy and "Cloud Storage" in deploy


def test_run_read_back_from_disk_renders(tmp_path):
    """A run saved by one process and loaded by another (as after a redeploy) still renders."""
    from streamlit.testing.v1 import AppTest

    from src.ui.run_jobs import RunJobs

    payload = json.loads(Path("tests/fixtures/s18_saved_run.json").read_text(encoding="utf-8"))
    RunJobs(tmp_path).start(lambda on_progress: payload, meta={"topic": payload["strategic_question"]})
    import time

    for _ in range(100):
        job = RunJobs(tmp_path).get(next(p.stem for p in tmp_path.glob("job_*.json")))
        if job and job["state"] == "done":
            break
        time.sleep(0.02)
    at = AppTest.from_file("web_app.py")
    at.session_state["research_results"] = job["results"]
    at.run(timeout=20)
    assert not at.exception, at.exception


# ------------------------------------------------------------------------------
# Test 3: Dark mode
# ------------------------------------------------------------------------------
def test_dark_mode_css():
    from src.ui.theme_mode import theme_css, theme_from_query

    dark = theme_css("dark")
    for needed in ("--card-bg", "--text-primary", ".stApp", '[data-testid="stSidebar"]', '[data-baseweb="input"]',
                   '[data-baseweb="tab"]', ".paper-card", ".run-status"):
        assert needed in dark, needed
    assert theme_css("light") == ""
    assert theme_from_query({"theme": "dark"}) == "dark"
    assert theme_from_query({}) == "light" and theme_from_query({"theme": "x"}) == "light"
    web = _web()
    assert 'st.toggle("🌙 Dark mode"' in web and 'st.query_params["theme"]' in web and "theme_css(" in web


# ------------------------------------------------------------------------------
# Test 4: Font
# ------------------------------------------------------------------------------
def test_font_stack():
    web = _web()
    assert "--font-main: 'Anthropic Sans', 'Inter'," in web
    assert "family=Inter" in web and "Plus+Jakarta+Sans" not in web
    assert "Anthropic+Sans" not in web and "anthropic-sans" not in web.lower().replace("'anthropic sans'", "")


# ------------------------------------------------------------------------------
# Test 5: AI Guruji brand
# ------------------------------------------------------------------------------
def test_ai_guruji_brand():
    web = _web()
    assert 'page_title="AI Guruji"' in web
    assert "<h1>AI Guruji</h1>" in web
    assert "Executive AI Research Studio" not in web and "RESEARCH STUDIO" not in web
