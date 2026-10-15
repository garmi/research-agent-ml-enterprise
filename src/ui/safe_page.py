"""Plain-English exception boundary for UI pages (Slice S1 Task 6).

Catches unhandled exceptions, protects user from stack trace disclosure,
displays an actionable plain-English message with a reference code and
sanitized copy details, and persists full debug tracebacks strictly to `logs/app.log`.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = "logs/app.log"
HEADLINE = "Something went wrong. Nothing was published."


def sanitize_message(message: str) -> str:
    """Remove filesystem paths, file extensions, and traceback tokens from error messages."""
    text = str(message or "")
    # Remove unix/windows absolute and relative paths
    text = re.sub(r"/(?:Users|home|var|tmp|private|usr|etc|opt)[\w\-./]+", "[redacted path]", text)
    text = re.sub(r"[a-zA-Z0-9_\-./]+\.py", "[redacted module]", text)
    text = re.sub(r"[A-Z]:\\[\w\-.\\]+", "[redacted path]", text)
    # Remove any traceback markers
    text = text.replace("Traceback", "[stack]")
    return text.strip() or "An internal error occurred."


def record_exception_to_log(
    exc: Exception,
    ref_code: str,
    log_path: str = DEFAULT_LOG_PATH,
) -> None:
    """Append full un-redacted exception traceback to log file."""
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tb_text = traceback.format_exc()

    entry = (
        f"======================================================================\n"
        f"TIMESTAMP: {timestamp}\n"
        f"REFERENCE: {ref_code}\n"
        f"EXCEPTION: {type(exc).__name__}: {str(exc)}\n"
        f"TRACEBACK:\n"
        f"{tb_text}\n"
        f"======================================================================\n\n"
    )
    with open(p, "a", encoding="utf-8") as f:
        f.write(entry)


def format_error_payload(exc: Exception, ref_code: Optional[str] = None) -> Dict[str, str]:
    """Generate sanitized dictionary for screen rendering."""
    code = ref_code or f"ERR-{uuid.uuid4().hex[:8].upper()}"
    clean_msg = sanitize_message(str(exc))
    exc_type = type(exc).__name__

    copy_details = (
        f"Reference: {code}\n"
        f"Type: {exc_type}\n"
        f"Details: {clean_msg}"
    )

    return {
        "headline": HEADLINE,
        "reference_text": f"Reference: {code}",
        "reference_code": code,
        "exception_type": exc_type,
        "clean_message": clean_msg,
        "copy_details": copy_details,
    }


def render_safe_error(payload: Dict[str, str]) -> None:
    """Render the plain-English error card in Streamlit."""
    try:
        import streamlit as st

        st.error(f"⚠️ **{payload['headline']}**")
        st.markdown(
            f"""
            <div style="background: #FEF2F2; border: 1px solid #FCA5A5; border-radius: 8px; padding: 1rem 1.25rem; margin: 1rem 0;">
                <div style="font-weight: 700; color: #991B1B; font-size: 0.95rem; margin-bottom: 0.25rem;">
                    {payload['reference_text']}
                </div>
                <div style="color: #7F1D1D; font-size: 0.88rem; margin-bottom: 0.75rem;">
                    An unexpected failure occurred while processing this step. No publication or ledger state was altered.
                </div>
                <div style="font-size: 0.82rem; color: #4B5563; margin-bottom: 0.4rem;">
                    Provide this reference code to engineering support or copy the error summary below:
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.code(payload["copy_details"], language="text")
    except Exception as render_err:
        logger.error("Failed to render error in Streamlit: %s", render_err)


def safe_page_boundary(
    func: Callable[[], Any],
    log_path: str = DEFAULT_LOG_PATH,
) -> Dict[str, str]:
    """Execute page function inside safety boundary.

    If an exception occurs, logs traceback to log_path and returns the sanitized
    error payload (and attempts Streamlit rendering if active).
    """
    try:
        func()
        return {}
    except Exception as exc:
        ref_code = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        record_exception_to_log(exc, ref_code, log_path=log_path)
        payload = format_error_payload(exc, ref_code=ref_code)
        render_safe_error(payload)
        return payload


from contextlib import contextmanager

@contextmanager
def safe_page(log_path: str = DEFAULT_LOG_PATH):
    """Context manager for wrapping page execution in plain-English safety boundary."""
    try:
        yield
    except Exception as exc:
        ref_code = f"ERR-{uuid.uuid4().hex[:8].upper()}"
        record_exception_to_log(exc, ref_code, log_path=log_path)
        payload = format_error_payload(exc, ref_code=ref_code)
        render_safe_error(payload)

