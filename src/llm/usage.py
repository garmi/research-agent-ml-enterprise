"""Per-run Gemini usage and cost: tokens from each reply's usageMetadata, plus the Google Search queries
grounded calls ran.

A run opens a meter with `metering()`; GeminiClient records every reply into the meter of the run it is
called from (a context variable, so a reasoning call from another browser session is never counted in a
run). Cost is an estimate from the price table in config.yaml (`pricing:`), which must be kept in step with
https://ai.google.dev/gemini-api/docs/pricing: the app cannot read Google's bill.
"""

from __future__ import annotations

import contextlib
import contextvars
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Mapping, Optional

# USD per million tokens (input, output; output includes thinking tokens) and per 1,000 search queries.
# Keys are model-name prefixes: the longest prefix of the reply's modelVersion wins.
DEFAULT_PRICING: Dict[str, Any] = {
    "usd_to_inr": 88.0,
    "search_per_1000_queries_usd": 14.0,
    "models": {
        "gemini-3.5-flash": {"input": 1.50, "output": 9.00},
        "gemini-3-flash": {"input": 0.50, "output": 3.00},
    },
}

_current: contextvars.ContextVar[Optional["UsageMeter"]] = contextvars.ContextVar("gemini_usage_meter", default=None)


@dataclass
class UsageMeter:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    search_calls: int = 0
    search_queries: int = 0
    by_model: Dict[str, Dict[str, int]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, model: str, usage: Optional[Mapping[str, Any]], search_queries: Optional[int] = None) -> None:
        """One Gemini reply. search_queries is given for a grounded call (the number of queries Google ran)."""
        u = usage or {}
        tokens_in = int(u.get("promptTokenCount") or 0) + int(u.get("toolUsePromptTokenCount") or 0)
        thinking = int(u.get("thoughtsTokenCount") or 0)
        tokens_out = int(u.get("candidatesTokenCount") or 0) + thinking
        with self._lock:
            self.calls += 1
            self.input_tokens += tokens_in
            self.output_tokens += tokens_out
            self.thinking_tokens += thinking
            if search_queries is not None:
                self.search_calls += 1
                self.search_queries += int(search_queries)
            m = self.by_model.setdefault(model or "unknown", {"calls": 0, "input_tokens": 0, "output_tokens": 0})
            m["calls"] += 1
            m["input_tokens"] += tokens_in
            m["output_tokens"] += tokens_out

    def summary(self, pricing: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Counts plus the estimated cost in USD and INR. Tokens of a model with no price leave the cost
        incomplete, and `unpriced_models` names them."""
        p = {**DEFAULT_PRICING, **(pricing or {})}
        prices = p.get("models") or {}
        token_usd, unpriced = 0.0, []
        for model, m in sorted(self.by_model.items()):
            price = _price_for(model, prices)
            if price is None:
                unpriced.append(model)
                continue
            token_usd += m["input_tokens"] / 1e6 * float(price["input"]) + m["output_tokens"] / 1e6 * float(price["output"])
        search_usd = self.search_queries / 1000 * float(p.get("search_per_1000_queries_usd") or 0)
        total_usd = token_usd + search_usd
        rate = float(p.get("usd_to_inr") or 0)
        return {
            "calls": self.calls, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "thinking_tokens": self.thinking_tokens, "search_calls": self.search_calls,
            "search_queries": self.search_queries, "by_model": {k: dict(v) for k, v in self.by_model.items()},
            "token_cost_usd": round(token_usd, 4), "search_cost_usd": round(search_usd, 4),
            "cost_usd": round(total_usd, 4), "cost_inr": round(total_usd * rate, 2), "usd_to_inr": rate,
            "unpriced_models": unpriced,
        }


def _price_for(model: str, prices: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    name = str(model or "").strip().lower().removeprefix("models/")
    matches = [k for k in prices if name.startswith(str(k).lower())]
    return prices[max(matches, key=len)] if matches else None


def record(model: str, usage: Optional[Mapping[str, Any]], search_queries: Optional[int] = None) -> None:
    """Add one Gemini reply to the current run's meter; outside a run, nothing is counted."""
    meter = _current.get()
    if meter is not None:
        meter.record(model, usage, search_queries)


@contextlib.contextmanager
def metering() -> Iterator[UsageMeter]:
    meter = UsageMeter()
    token = _current.set(meter)
    try:
        yield meter
    finally:
        _current.reset(token)


def pricing_from_config(cfg: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """config.yaml's `pricing:` over the defaults (model prices merge per model)."""
    user = dict((cfg or {}).get("pricing") or {})
    models = {**DEFAULT_PRICING["models"], **(user.pop("models", None) or {})}
    return {**DEFAULT_PRICING, **user, "models": models}


def cost_lines(usage: Optional[Mapping[str, Any]]) -> list:
    """The Checks page's lines for a run's usage; empty when the run made no Gemini calls."""
    if not usage or not usage.get("calls"):
        return []
    lines = [
        f"**Gemini cost for this run (estimate):** ≈ ₹{usage['cost_inr']:,.2f} (${usage['cost_usd']:.3f})",
        f"{usage['calls']} model calls · {usage['input_tokens']:,} input tokens · {usage['output_tokens']:,} output tokens"
        f" (of which {usage.get('thinking_tokens', 0):,} thinking) · {usage.get('search_queries', 0)} Google Search"
        f" queries in {usage.get('search_calls', 0)} grounded calls",
        f"Tokens ${usage.get('token_cost_usd', 0):.3f} + search ${usage.get('search_cost_usd', 0):.3f}, at "
        f"₹{usage.get('usd_to_inr', 0):g} per $ and the prices in config.yaml. Search is billed only past Google's "
        "free monthly allowance; the Ask and Scope steps are not included. Your Google Cloud bill is the real figure.",
    ]
    if usage.get("unpriced_models"):
        lines.append("No price set for " + ", ".join(usage["unpriced_models"]) + ": their tokens are not in the cost.")
    return lines
