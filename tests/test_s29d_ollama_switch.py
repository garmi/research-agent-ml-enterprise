"""Tests for Slice S29d: when Gemini's limit is reached, switch to Ollama and keep going (the app runs on your Mac).

Requirements:
1. Gemini's 429 / RESOURCE_EXHAUSTED, after the client's retries, raises GeminiQuotaExceeded (for the report and for
   grounded search), and the question reasoner passes it straight on. is_quota_error recognises it, also inside a
   wrapped message.
2. A run whose model step hit the limit says so in the banner: "Gemini's limit is reached", with "Switch to Ollama".
3. The switch: with Ollama reachable, a "Switch to Ollama and run again" button (it picks the Ollama engine and
   re-runs the same approved question); without it, the local start command. The reasoning pages offer the same.
4. Honest labels for local runs: the run records its engine; Check D's line names the local model as less reliable
   than Gemini; draft copies name the engine; the enterprise coverage line says web search is not available on the
   local model. The Ollama engine label shows OLLAMA_MODEL.
5. scripts/run_local.sh starts Ollama's model and the app locally and never holds a key.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest


# ------------------------------------------------------------------------------
# Test 1: The quota error
# ------------------------------------------------------------------------------
class _Resp:
    def __init__(self, code=429, text='{"error": {"status": "RESOURCE_EXHAUSTED"}}'):
        self.status_code, self.text, self.reason, self.ok = code, text, "Too Many Requests", code < 400

    def json(self):
        return {}


def test_429_raises_quota_error(monkeypatch):
    from src.llm import gemini_client
    from src.llm.gemini_client import GeminiClient, GeminiQuotaExceeded, is_quota_error

    monkeypatch.setattr(gemini_client.time, "sleep", lambda s: None)
    calls = []
    monkeypatch.setattr(gemini_client.requests, "post", lambda *a, **k: calls.append(1) or _Resp())
    client = GeminiClient(api_key="test-key", retries=2)
    with pytest.raises(GeminiQuotaExceeded):
        client.generate("hi")
    assert len(calls) == 3, "retries first, then gives up"
    with pytest.raises(GeminiQuotaExceeded):
        client.search_sources("hi")
    assert is_quota_error(GeminiQuotaExceeded("x"))
    assert is_quota_error(RuntimeError("Question reasoning failed: Gemini's usage limit is reached (HTTP 429)."))
    assert not is_quota_error(RuntimeError("HTTP 500"))


def test_reasoner_passes_quota_error_on(monkeypatch):
    from src.engine import reasoner
    from src.llm.gemini_client import GeminiQuotaExceeded

    def boom(**kwargs):
        raise GeminiQuotaExceeded("Gemini's usage limit is reached (HTTP 429).")

    monkeypatch.setattr(reasoner, "_call_model_for_reasoning", boom)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("STUB_LLM", raising=False)
    with pytest.raises(GeminiQuotaExceeded):
        reasoner.reason_question(user_text="Does a four-day week change output?", provider="gemini")


# ------------------------------------------------------------------------------
# Test 2: The banner
# ------------------------------------------------------------------------------
def test_banner_names_the_limit():
    from src.ui.run_status import run_status

    st = run_status({"is_fallback": True, "status": "BLOCKED",
                     "error_details": {"error_class": "GeminiQuotaExceeded", "error_message": "429"}})
    assert "Gemini's limit is reached" in st["headline"] and "Switch to Ollama" in st["next_step"]


# ------------------------------------------------------------------------------
# Test 3: The switch
# ------------------------------------------------------------------------------
def test_switch_offer():
    from src.ui.engine_switch import LOCAL_COMMAND, quota_hit, switch_offer

    assert quota_hit({"error_details": {"error_class": "GeminiQuotaExceeded"}}, {})
    assert quota_hit(None, {"gemini_quota_hit": True})
    assert not quota_hit({"error_details": {"error_class": "OfflineEngine"}}, {})
    assert switch_offer(True)["action"] == "switch"
    local = switch_offer(False)
    assert local["action"] == "local" and LOCAL_COMMAND in local["text"]
    assert "scripts/run_local.sh" in LOCAL_COMMAND


def test_web_app_wires_the_switch():
    web = Path("web_app.py").read_text(encoding="utf-8")
    assert "Switch to Ollama and run again" in web and '"auto_run_ollama"' in web
    assert "render_quota_switch(" in web
    intake = Path("src/ui/intake_view.py").read_text(encoding="utf-8")
    assert 'st.session_state["gemini_quota_hit"] = True' in intake


def test_ollama_label_shows_model(monkeypatch):
    from src.ui.engine_switch import ollama_label

    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")
    assert "qwen2.5:3b-instruct" in ollama_label()
    assert "Qwen 2.5 3B" not in Path("web_app.py").read_text(encoding="utf-8")


# ------------------------------------------------------------------------------
# Test 4: Honest labels
# ------------------------------------------------------------------------------
def test_local_model_labels(monkeypatch):
    from src.output.personal_copy import header_lines
    from src.ui.engine_switch import check_d_engine_note, engine_line

    local = {"engine": {"provider": "ollama", "model": "qwen2.5:3b-instruct"}, "status": "BLOCKED"}
    assert "less reliable than Gemini" in check_d_engine_note(local) and "qwen2.5:3b-instruct" in check_d_engine_note(local)
    assert check_d_engine_note({"engine": {"provider": "gemini", "model": "gemini-2.5-flash"}}) == ""
    assert engine_line(local) == "Engine: Ollama (qwen2.5:3b-instruct), local"
    assert any(l.startswith("Engine: Ollama") for l in header_lines(local))
    web = Path("web_app.py").read_text(encoding="utf-8")
    assert "check_d_engine_note(results)" in web[web.index('if page == "checks":'):]
    runner = Path("src/analysis/multilane_runner.py").read_text(encoding="utf-8")
    assert 'result["engine"]' in runner


def test_coverage_line_on_local_model():
    from src.analysis.multilane_runner import MultiLaneResearchRunner

    r = MultiLaneResearchRunner.__new__(MultiLaneResearchRunner)
    r._grounded = {"status": "not_searched", "coverage": [], "provider": "ollama"}
    assert any("not available on the local model" in line for line in r._enterprise_coverage())
    r._grounded = {"status": "not_searched", "coverage": [], "provider": "gemini"}
    assert any("it needs Gemini" in line for line in r._enterprise_coverage())


# ------------------------------------------------------------------------------
# Test 5: Local start script
# ------------------------------------------------------------------------------
def test_run_local_script():
    p = Path("scripts/run_local.sh")
    text = p.read_text(encoding="utf-8")
    assert os.stat(p).st_mode & stat.S_IXUSR
    assert "ollama pull" in text and "qwen2.5:3b-instruct" in text
    assert "RESEARCH_RUNS_DIR" in text and "streamlit run web_app.py" in text
    assert "AIza" not in text and "GEMINI_API_KEY=" not in text
