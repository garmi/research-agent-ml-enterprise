"""Shared UI components for Research Engine (Slice S1 Round 3).

Provides reusable, accessible HTML component snippets styled with constants from src.ui.theme:
- status_badge: formatted badge for PUBLISH_READY / REVISE / BLOCKED / NOT_PUBLISHABLE
- disabled_reason: neutral info box displaying why an action is currently disabled
- info_box: neutral contextual informational box
"""

from __future__ import annotations

import html
from typing import Optional

from src.ui.theme import (
    COLOR_BORDER,
    COLOR_DISABLED_BOX_BG,
    COLOR_DISABLED_BOX_BORDER,
    COLOR_DISABLED_BOX_TEXT,
    COLOR_INFO_BOX_BG,
    COLOR_INFO_BOX_BORDER,
    COLOR_INFO_BOX_TEXT,
    COLOR_STATUS_BLOCKED_BG,
    COLOR_STATUS_BLOCKED_BORDER,
    COLOR_STATUS_BLOCKED_TEXT,
    COLOR_STATUS_NOT_PUBLISHABLE_BG,
    COLOR_STATUS_NOT_PUBLISHABLE_BORDER,
    COLOR_STATUS_NOT_PUBLISHABLE_TEXT,
    COLOR_STATUS_PUBLISH_READY_BG,
    COLOR_STATUS_PUBLISH_READY_BORDER,
    COLOR_STATUS_PUBLISH_READY_TEXT,
    COLOR_STATUS_REVISE_BG,
    COLOR_STATUS_REVISE_BORDER,
    COLOR_STATUS_REVISE_TEXT,
    FONT_FAMILY,
    FONT_SIZE_SM,
    FONT_SIZE_XS,
    SPACING_SM,
    SPACING_XS,
)

_STATUS_CONFIG = {
    "PUBLISH_READY": {
        "label": "PUBLISH READY",
        "text_color": COLOR_STATUS_PUBLISH_READY_TEXT,
        "bg_color": COLOR_STATUS_PUBLISH_READY_BG,
        "border_color": COLOR_STATUS_PUBLISH_READY_BORDER,
    },
    "REVISE": {
        "label": "REVISE",
        "text_color": COLOR_STATUS_REVISE_TEXT,
        "bg_color": COLOR_STATUS_REVISE_BG,
        "border_color": COLOR_STATUS_REVISE_BORDER,
    },
    "BLOCKED": {
        "label": "BLOCKED",
        "text_color": COLOR_STATUS_BLOCKED_TEXT,
        "bg_color": COLOR_STATUS_BLOCKED_BG,
        "border_color": COLOR_STATUS_BLOCKED_BORDER,
    },
    "NOT_PUBLISHABLE": {
        "label": "NOT PUBLISHABLE",
        "text_color": COLOR_STATUS_NOT_PUBLISHABLE_TEXT,
        "bg_color": COLOR_STATUS_NOT_PUBLISHABLE_BG,
        "border_color": COLOR_STATUS_NOT_PUBLISHABLE_BORDER,
    },
}


def status_badge(status: str, reason: Optional[str] = None) -> str:
    """Return HTML snippet for a publication readiness status badge."""
    canonical_key = (status or "").strip().upper().replace(" ", "_")
    config = _STATUS_CONFIG.get(canonical_key)
    if not config:
        config = {
            "label": html.escape(status or "UNKNOWN"),
            "text_color": COLOR_STATUS_NOT_PUBLISHABLE_TEXT,
            "bg_color": COLOR_STATUS_NOT_PUBLISHABLE_BG,
            "border_color": COLOR_STATUS_NOT_PUBLISHABLE_BORDER,
        }

    label = config["label"]
    escaped_reason = html.escape(reason.strip()) if reason and reason.strip() else ""
    reason_html = (
        f'<span style="font-size: {FONT_SIZE_XS}; color: {config["text_color"]}; opacity: 0.9; margin-left: {SPACING_SM};">'
        f'{escaped_reason}</span>'
        if escaped_reason
        else ""
    )

    return (
        f'<div style="display: inline-flex; align-items: center; background: {config["bg_color"]}; '
        f'color: {config["text_color"]}; border: 1px solid {config["border_color"]}; '
        f'border-radius: 6px; padding: {SPACING_XS} {SPACING_SM}; font-family: {FONT_FAMILY}; '
        f'font-size: {FONT_SIZE_XS}; font-weight: 700; letter-spacing: 0.04em;">'
        f'<span>{label}</span>{reason_html}'
        f'</div>'
    )


def disabled_reason(text: str) -> str:
    """Return HTML snippet for a neutral box explaining why an action is disabled."""
    escaped = html.escape(text.strip())
    return (
        f'<div style="background: {COLOR_DISABLED_BOX_BG}; border: 1px solid {COLOR_DISABLED_BOX_BORDER}; '
        f'border-radius: 8px; padding: 0.65rem 0.95rem; margin: 0.5rem 0; font-family: {FONT_FAMILY}; '
        f'font-size: {FONT_SIZE_SM}; color: {COLOR_DISABLED_BOX_TEXT}; line-height: 1.45;">'
        f'<span>ℹ️ {escaped}</span>'
        f'</div>'
    )


def info_box(text: str) -> str:
    """Return HTML snippet for a neutral contextual information box."""
    escaped = html.escape(text.strip())
    return (
        f'<div style="background: {COLOR_INFO_BOX_BG}; border: 1px solid {COLOR_INFO_BOX_BORDER}; '
        f'border-radius: 8px; padding: 0.65rem 0.95rem; margin: 0.5rem 0; font-family: {FONT_FAMILY}; '
        f'font-size: {FONT_SIZE_SM}; color: {COLOR_INFO_BOX_TEXT}; line-height: 1.45;">'
        f'<span>ℹ️ {escaped}</span>'
        f'</div>'
    )
