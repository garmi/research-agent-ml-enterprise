"""Tests for Slice S9: a run survives a dropped browser session; Gemini model naming; leaner landing page.

Requirements:
1. A run executes as a background job. Its progress and result are recorded outside the browser
   session, so a new session (after a reconnect or reload) can pick up the same run by its id.
2. A failed run records a plain-words error instead of vanishing.
3. Only one run executes at a time; starting another while one runs returns the running job.
4. Finished runs are listed newest first, so the sidebar history survives a new session.
5. web_app.py starts runs and re-drafts through the job runner, keeps the job id in the URL, and
   polls progress; it never runs the pipeline inline in the page.
6. One helper names the Gemini model (env GEMINI_MODEL, else config, default gemini-3.5-flash), and the
   model picker shows that name instead of a hard-coded version.
7. The pre-run "Active Three-Lane Architecture & Ingestion Readiness" section is gone.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from src.ui.run_jobs import RunJobs


def _wait(jobs: RunJobs, job_id: str, timeout: float = 5.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        job = jobs.get(job_id)
        if job and job["state"] in ("done", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


# ------------------------------------------------------------------------------
# Test 1: Result survives the session
# ------------------------------------------------------------------------------
def test_job_result_survives_new_session(tmp_path):
    gate = threading.Event()

    def target(on_progress):
        on_progress(3, "Extracting claims", 0.4)
        gate.wait(2)
        return {"run_id": "run_1", "status": "BLOCKED", "papers": [{"key": "P1"}]}

    jobs = RunJobs(tmp_path)
    job_id = jobs.start(target, meta={"topic": "AI assistants and cycle time"})
    time.sleep(0.1)
    running = jobs.get(job_id)
    assert running["state"] == "running" and running["stage"] == 3 and running["message"] == "Extracting claims"
    gate.set()
    done = _wait(jobs, job_id)
    assert done["state"] == "done" and done["results"]["run_id"] == "run_1"

    # A fresh registry (new process or session) reads the same run from disk.
    again = RunJobs(tmp_path).get(job_id)
    assert again["state"] == "done" and again["results"]["status"] == "BLOCKED"
    assert again["meta"]["topic"] == "AI assistants and cycle time"


# ------------------------------------------------------------------------------
# Test 2: Failures are recorded
# ------------------------------------------------------------------------------
def test_failed_job_records_error(tmp_path):
    def target(on_progress):
        raise RuntimeError("Gemini request failed: 403")

    jobs = RunJobs(tmp_path, error_formatter=lambda exc: {"title": "Model error", "what_happened": str(exc)})
    job = _wait(jobs, jobs.start(target, meta={"topic": "t"}))
    assert job["state"] == "failed" and job["error"]["what_happened"] == "Gemini request failed: 403"
    assert RunJobs(tmp_path).get(job["job_id"])["state"] == "failed"


# ------------------------------------------------------------------------------
# Test 3: One run at a time
# ------------------------------------------------------------------------------
def test_one_run_at_a_time(tmp_path):
    gate = threading.Event()
    jobs = RunJobs(tmp_path)
    first = jobs.start(lambda on_progress: gate.wait(2) and {"run_id": "a"}, meta={"topic": "a"})
    second = jobs.start(lambda on_progress: {"run_id": "b"}, meta={"topic": "b"})
    assert second == first and jobs.running() == first
    gate.set()
    _wait(jobs, first)
    assert jobs.running() is None


# ------------------------------------------------------------------------------
# Test 4: History survives the session
# ------------------------------------------------------------------------------
def test_recent_runs_newest_first(tmp_path):
    jobs = RunJobs(tmp_path)
    ids = []
    for topic in ("first", "second"):
        ids.append(jobs.start(lambda on_progress, t=topic: {"run_id": t}, meta={"topic": topic}))
        _wait(jobs, ids[-1])
        time.sleep(0.01)
    recent = RunJobs(tmp_path).recent(limit=5)
    assert [r["meta"]["topic"] for r in recent] == ["second", "first"]
    assert all("results" not in r for r in recent), "the list stays light; results load on click"


def test_unknown_job_is_none(tmp_path):
    assert RunJobs(tmp_path).get("nope") is None
    assert RunJobs(tmp_path).get("../../etc/passwd") is None


# ------------------------------------------------------------------------------
# Test 5: web_app uses the job runner
# ------------------------------------------------------------------------------
def test_web_app_runs_through_jobs():
    src = Path("web_app.py").read_text(encoding="utf-8")
    assert "refreshed = run_production_pipeline(" not in src
    assert "results = run_production_pipeline(" not in src
    assert src.count("launch_run_job(") >= 4  # definition + run + two re-drafts
    assert 'st.query_params["run"]' in src
    assert "@st.fragment(run_every=" in src
    assert "run_jobs.recent(" in src
    assert 'st.session_state["history"].append' not in src


# ------------------------------------------------------------------------------
# Test 6: Gemini model naming
# ------------------------------------------------------------------------------
def test_gemini_model_name(monkeypatch):
    from src.llm.model_names import DEFAULT_GEMINI_MODEL, gemini_model_name

    assert DEFAULT_GEMINI_MODEL == "gemini-3.5-flash"
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert gemini_model_name({}) == "gemini-3.5-flash"
    assert gemini_model_name({"gemini": {"model": "gemini-3.5-pro"}}) == "gemini-3.5-pro"
    monkeypatch.setenv("GEMINI_MODEL", " gemini-x ")
    assert gemini_model_name({"gemini": {"model": "gemini-3.5-pro"}}) == "gemini-x"

    for path in ("web_app.py", "src/llm/factory.py", "src/llm/gemini_client.py", "src/engine/reasoner.py", "config.yaml"):
        text = Path(path).read_text(encoding="utf-8")
        assert "2.5-flash" not in text and "Gemini 2.5" not in text, path
    assert "gemini_model_name()" in Path("web_app.py").read_text(encoding="utf-8")


# ------------------------------------------------------------------------------
# Test 7: Landing section removed
# ------------------------------------------------------------------------------
def test_three_lane_landing_removed():
    src = Path("web_app.py").read_text(encoding="utf-8")
    assert "Active Three-Lane Architecture & Ingestion Readiness" not in src
