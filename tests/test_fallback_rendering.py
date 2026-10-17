"""Test for bug fix: AppTest rendering when is_fallback is True."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest


def test_fallback_rendering_does_not_raise_name_error():
    """Verify that when results['is_fallback'] is True, web_app.py does not raise NameError for gap_info."""
    at = AppTest.from_file("web_app.py")
    at.session_state["research_results"] = {
        "topic": "Test topic",
        "is_fallback": True,
        "generation_mode": "extractive_fallback",
        "blocking_banner": "EXTRACTIVE FALLBACK MODE • Primary model unavailable (Offline). Output generated from verified extractive claims only and is blocked from publication.",
        "duration": "10s",
        "papers": [],
        "claims": [],
        "verdict": "Test verdict",
        "signals": [
            {"tag": "Signal 1", "text": "Signal text [P1]"},
            {"tag": "Signal 2", "text": "Signal text [P2]"},
            {"tag": "Signal 3", "text": "Signal text [P3]"},
        ],
        "findings": [],
        "risks": [],
        "metrics": {"volume": 0, "sources": 0, "horizon": "2024", "quality": "NOT_PUBLISHABLE"},
        "quality_scorecard": {"band": "NOT_PUBLISHABLE", "total": 40},
        "gates_audit": {"passed": False, "reasons": ["Blocked"]},
    }
    at.run(timeout=10)
    assert not at.exception, f"App raised exception during fallback rendering: {at.exception}"
