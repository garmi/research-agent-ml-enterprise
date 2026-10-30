"""Tests for per-run Gemini cost tracking.

Requirements:
1. Each Gemini reply's usageMetadata is added to the meter of the run it is made in: input = prompt + tool-use
   prompt tokens, output = reply + thinking tokens, priced by the model Google reports (modelVersion).
2. A grounded search call also counts the Google Search queries it ran.
3. Outside a run nothing is counted, and runs do not share a meter.
4. Cost = tokens at the model's price + queries at the search price, in USD and INR; a model with no price is named
   and left out of the cost. config.yaml's pricing overrides the defaults per model.
5. The Checks page lines show the cost, the counts and that it is an estimate; a run with no Gemini calls shows none.
6. Error text never carries a key, in either the AIza… or the AQ.… form.
"""

from __future__ import annotations

import pytest

from src.llm import usage


class _Resp:
    def __init__(self, data, code=200, text=""):
        self.status_code, self.ok, self.reason, self.text, self._data = code, code < 400, "OK", text, data

    def json(self):
        return self._data


def _reply(model="gemini-3.5-flash-001", prompt=1000, tool=0, out=200, thoughts=300, queries=None):
    meta = {"promptTokenCount": prompt, "toolUsePromptTokenCount": tool, "candidatesTokenCount": out,
            "thoughtsTokenCount": thoughts}
    cand = {"content": {"parts": [{"text": "OK"}]}}
    if queries is not None:
        cand["groundingMetadata"] = {"webSearchQueries": queries, "groundingChunks": []}
    return {"candidates": [cand], "usageMetadata": meta, "modelVersion": model}


def test_generate_and_search_are_metered(monkeypatch):
    from src.llm import gemini_client
    from src.llm.gemini_client import GeminiClient

    replies = [_reply(), _reply(prompt=500, tool=2000, out=50, thoughts=0, queries=["a", "b", "c"])]
    monkeypatch.setattr(gemini_client.requests, "post", lambda *a, **k: _Resp(replies.pop(0)))
    client = GeminiClient(api_key="test-key", model="gemini-flash-latest")
    with usage.metering() as meter:
        client.generate("hi")
        client.search_sources("find")
    s = meter.summary()
    assert (s["calls"], s["input_tokens"], s["output_tokens"], s["thinking_tokens"]) == (2, 3500, 550, 300)
    assert (s["search_calls"], s["search_queries"]) == (1, 3)
    assert list(s["by_model"]) == ["gemini-3.5-flash-001"], "priced by the model Google reports, not the alias"
    expected_usd = 3500 / 1e6 * 1.50 + 550 / 1e6 * 9.00 + 3 / 1000 * 14.0
    assert s["cost_usd"] == pytest.approx(expected_usd, abs=1e-4)
    assert s["cost_inr"] == pytest.approx(expected_usd * 88.0, abs=0.01)


def test_nothing_counted_outside_a_run_and_runs_are_separate():
    usage.record("gemini-3.5-flash", {"promptTokenCount": 10})
    with usage.metering() as first:
        usage.record("gemini-3.5-flash", {"promptTokenCount": 10})
    with usage.metering() as second:
        pass
    assert first.calls == 1 and second.calls == 0


def test_longest_price_prefix_and_unpriced_models():
    meter = usage.UsageMeter()
    meter.record("gemini-3-flash-preview", {"promptTokenCount": 1_000_000})
    meter.record("mystery-model", {"promptTokenCount": 1_000_000})
    s = meter.summary(usage.pricing_from_config({"pricing": {"models": {"gemini-3-flash-preview": {"input": 2, "output": 4}}}}))
    assert s["token_cost_usd"] == pytest.approx(2.0), "the longer, more specific prefix wins"
    assert s["unpriced_models"] == ["mystery-model"]
    assert "gemini-3.5-flash" in usage.pricing_from_config({"pricing": {"models": {"x": {}}}})["models"], \
        "config prices add to the defaults"


def test_checks_page_lines():
    assert usage.cost_lines(None) == [] and usage.cost_lines({"calls": 0}) == []
    meter = usage.UsageMeter()
    meter.record("gemini-3.5-flash", {"promptTokenCount": 200_000, "candidatesTokenCount": 30_000,
                                      "thoughtsTokenCount": 20_000}, search_queries=5)
    meter.record("unknown-x", {"promptTokenCount": 1})
    text = "\n".join(usage.cost_lines(meter.summary()))
    assert "₹" in text and "estimate" in text
    assert "200,001 input tokens" in text and "5 Google Search queries in 1 grounded calls" in text
    assert "No price set for unknown-x" in text


def test_keys_are_redacted_in_both_forms():
    from src.llm.gemini_client import redact_keys

    old = "AIza" + "B" * 35
    new = "AQ.Ab8RN6" + "x_y-z" * 8
    out = redact_keys(f"bad key {old} and {new}.")
    assert old not in out and new not in out and out.count("[REDACTED_KEY]") == 2
