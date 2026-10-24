"""Run status (S8): one headline, the reasons in plain words, and the next step, for every run.

The same results drive the status banner above the tabs and the step rail in the sidebar, so the
two never disagree.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

from src.ui.publish_view import publish_eligibility

STEPS = ("Question", "Evidence", "Claims", "Brief", "Checks & publish")

_STATUS = {
    "BLOCKED": ("error", "Draft blocked by the checks",
                "Open Checks & publish to see which gate failed and why, fix the evidence or wording, then re-draft."),
    "NOT_PUBLISHABLE": ("warn", "Draft is below the publish threshold",
                        "Add stronger or more varied sources, then run again."),
    "REVISE": ("warn", "Ready for review: publishing needs your reason",
               "Read the brief, then publish from Checks & publish with a reason, which is logged."),
    "PUBLISH_READY": ("ok", "Ready to publish",
                      "Read the brief, then publish from Checks & publish with your name."),
    "PUBLISHED": ("ok", "Published", "Download the deliverables from Checks & publish."),
    "FAILED": ("error", "The run failed", "Run it again; if it fails twice, check the model connection."),
}


def _reasons(results: Dict[str, Any]) -> List[str]:
    pub = results.get("publish_res") or {}
    return [str(r) for r in (pub.get("reasons") or ([pub["reason"]] if pub.get("reason") else []))]


def status_code(results: Dict[str, Any]) -> str:
    """The run's status, derived once for the banner, the step rail and the exports."""
    return str(
        results.get("status")
        or (results.get("publish_res") or {}).get("status")
        or (results.get("quality_scorecard") or {}).get("band")
        or "NOT_PUBLISHABLE"
    ).upper()


def run_status(results: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """{level, headline, why, next_step} for a run, or None before any run."""
    if not results:
        return None
    stopped = results.get("stopped_at")
    # A stopped run keeps every recorded reason (an unconfirmed practitioner abstraction comes first).
    stop_why = _reasons(results) or [str(results.get("stop_reason") or "")]
    if stopped == "check_a":
        return {"level": "error", "headline": "Stopped after the search: not enough on-topic evidence",
                "why": stop_why,
                "next_step": "See which sources were judged off-topic on the Evidence tab, then rephrase "
                             "or widen the question in Step 1 and run again."}
    if stopped == "check_b":
        return {"level": "error", "headline": "Stopped before drafting: too few usable claims",
                "why": stop_why,
                "next_step": "Add sources, or re-include claims on the Evidence tab, then re-draft."}
    if results.get("is_fallback") and (results.get("error_details") or {}).get("error_class") == "GeminiQuotaExceeded":
        # S29d: say plainly that the key's limit is used up, and how to keep going.
        return {"level": "warn", "headline": "Gemini's limit is reached: this draft was built from extracted quotes only",
                "why": ["Gemini answered 'limit reached' (HTTP 429), so the report was not written by a model."],
                "next_step": "Switch to Ollama on the Sources & run page to run it again on your Mac, or try Gemini "
                             "later. This draft cannot be published."}
    if results.get("is_fallback"):
        return {"level": "warn", "headline": "Draft built from extracted quotes only: the model was unavailable",
                "why": [str(results.get("blocking_banner") or "The language model did not respond.")],
                "next_step": "Check the model connection, then run again. This draft cannot be published."}
    status = status_code(results)
    level, headline, next_step = _STATUS.get(
        status, ("warn", f"Run ended with status {status or 'unknown'}", "Run it again."))
    if status in ("PUBLISH_READY", "REVISE"):
        # The banner never offers what the Publish step refuses (test mode, hosted demo, no draft).
        eligible, _, why_not = publish_eligibility(results)
        if not eligible:
            level, next_step = "warn", f"Publishing is not available here: {why_not}"
    return {"level": level, "headline": headline, "why": _reasons(results), "next_step": next_step}


_LEVEL_STYLE = {
    "error": ("#FEF2F2", "#FCA5A5", "#991B1B", "⛔"),
    "warn": ("#FFFBEB", "#FCD34D", "#92400E", "⚠️"),
    "ok": ("#F0FDF4", "#86EFAC", "#166534", "✅"),
}


def status_banner_html(status: Dict[str, Any]) -> str:
    """The one status banner shown above the run's tabs."""
    bg, border, fg, icon = _LEVEL_STYLE.get(status["level"], _LEVEL_STYLE["warn"])
    why = "".join(f"<li>{html.escape(r)}</li>" for r in status.get("why") or [])
    return (
        f'<div class="run-status" style="background:{bg};border:1px solid {border};color:{fg};">'
        f'<div class="run-status-head">{icon} {html.escape(status["headline"])}</div>'
        + (f'<ul class="run-status-why">{why}</ul>' if why else "")
        + f'<div class="run-status-next"><strong>Next:</strong> {html.escape(status["next_step"])}</div></div>'
    )


def step_rail(results: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Each step's state: done, stopped, current (waiting on you) or pending (not reached)."""
    if not results:
        return [{"label": s, "state": "current" if s == "Question" else "pending", "detail": ""} for s in STEPS]
    stop_index = {"check_a": 1, "check_b": 2}.get(results.get("stopped_at") or "")
    status = status_code(results)
    if stop_index is None:
        last = {"PUBLISHED": "done", "PUBLISH_READY": "current", "REVISE": "current"}.get(status, "stopped")
        states = ["done"] * 4 + [last]
    else:
        states = ["done"] * stop_index + ["stopped"] + ["pending"] * (len(STEPS) - stop_index - 1)
    details = [
        "",
        f"{len(results.get('papers') or [])} papers · {len(results.get('enterprise_sources') or [])} enterprise",
        f"{len(results.get('claims') or [])} claims",
        f"{len(results.get('findings') or [])} findings" if stop_index is None else "",
        status.replace("_", " ").lower() if stop_index is None else "",
    ]
    return [{"label": s, "state": st, "detail": d} for s, st, d in zip(STEPS, states, details)]


_STATE_ICON = {"done": ("✓", "#059669"), "stopped": ("✕", "#DC2626"), "current": ("●", "#2563EB"), "pending": ("○", "#94A3B8")}


def step_rail_html(steps: List[Dict[str, str]]) -> str:
    rows = []
    for i, s in enumerate(steps, start=1):
        icon, color = _STATE_ICON[s["state"]]
        detail = f'<div class="step-detail">{html.escape(s["detail"])}</div>' if s["detail"] else ""
        rows.append(
            f'<div class="step-row step-{s["state"]}"><span class="step-icon" style="color:{color};">{icon}</span>'
            f'<div><div class="step-label">{i}. {html.escape(s["label"])}</div>{detail}</div></div>'
        )
    return '<div class="step-rail">' + "".join(rows) + "</div>"
