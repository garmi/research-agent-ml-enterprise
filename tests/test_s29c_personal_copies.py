"""Tests for Slice S29c: your own copies always download, even when the gates fail.

Requirements:
1. A "Your copy" bar on Brief, Evidence and Checks & share: Brief .md, Claims .csv, Ledger .json, and, when the run
   has a summary, Post .txt and Card .svg; plus the brief as copyable text. Always enabled, whatever the gates,
   the score or Check D say. The share pack's own downloads are always enabled too.
2. A run not cleared for publishing (status other than PUBLISH_READY / PUBLISHED) gives copies marked as drafts:
   the file name ends in _DRAFT, and the file starts with "DRAFT for personal use — not cleared for publishing", the
   failing gates and other reasons, and Check D's in-brief support rate. A cleared run gives clean files.
3. Sentences Check D removed are never in a copy. Publishing itself stays gated.
"""

from __future__ import annotations

import copy
import csv
import io
import json
from pathlib import Path

FIXTURE = json.loads(Path("tests/fixtures/s18_saved_run.json").read_text(encoding="utf-8"))
HEADER = "DRAFT for personal use — not cleared for publishing"


def _with_report(status="BLOCKED"):
    r = copy.deepcopy(FIXTURE)
    r["status"] = status
    r["report"] = {"answer": {"text": "Cycle time fell [P1]."},
                   "sections": [{"index": 1, "sub_question": "Does cycle time fall?", "sentences": [
                       {"type": "assertive", "text": "One study reports cycle time fell by 14% [P1]."}], "table": []}],
                   "tensions": [], "gaps": [], "implications": []}
    r["check_d"] = {"in_brief": 2, "supported_in_brief": 2,
                    "removed": [{"text": "Removed claim about velocity [P2].", "reason": "not in the quotes"}]}
    r["summary"] = {"hook": "Shorter cycles, same quality?", "opening": "I read the studies.",
                    "takeaways": [{"text": "Cycle time fell in one study [P1].", "papers": ["P1"]}],
                    "question": "What have you seen?", "hashtags": ["#Engineering", "#AI", "#DevEx"], "dropped": []}
    return r


# ------------------------------------------------------------------------------
# Test 1: Draft marking
# ------------------------------------------------------------------------------
def test_blocked_copy_is_marked_with_reasons():
    from src.output.personal_copy import personal_copy

    data, name, mime = personal_copy(_with_report("BLOCKED"), "brief_md")
    assert name.endswith("_DRAFT.md") and mime == "text/markdown"
    head = data[:800]
    assert HEADER in head.splitlines()[0]
    assert "G2" in head and "G5" in head, "failing gates are listed"
    assert "extractive fallback" in head, "publish reasons are listed"
    assert "Check D: 2 of 2 sentences in this brief are supported by their quotes" in head
    assert "Cycle time fell" in data


def test_cleared_copy_is_clean():
    from src.output.personal_copy import personal_copy

    data, name, _ = personal_copy(_with_report("PUBLISH_READY"), "brief_md")
    assert HEADER not in data and "_DRAFT" not in name


def test_removed_sentences_never_in_copies():
    from src.output.personal_copy import personal_copy

    for kind in ("brief_md", "ledger_json", "post_txt"):
        data, _, _ = personal_copy(_with_report(), kind)
        assert "Removed claim about velocity" not in data, kind


def test_claims_csv_and_post_and_card():
    from src.output.personal_copy import personal_copy

    data, name, mime = personal_copy(_with_report(), "claims_csv")
    assert name.endswith("_DRAFT.csv") and mime == "text/csv"
    lines = data.splitlines()
    assert HEADER in lines[0]
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[1:]))))
    assert rows and {"source", "claim", "quote", "grade"} <= set(rows[0])
    post, pname, _ = personal_copy(_with_report(), "post_txt")
    assert pname.endswith("_DRAFT.txt") and post.startswith(HEADER)
    card, cname, cmime = personal_copy(_with_report(), "card_svg")
    assert cname.endswith("_DRAFT.svg") and cmime == "image/svg+xml" and "DRAFT" in card
    assert personal_copy(FIXTURE, "post_txt") is None, "no summary, no post"


# ------------------------------------------------------------------------------
# Test 2: Always enabled on every results page
# ------------------------------------------------------------------------------
def _app(results, page):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("web_app.py")
    at.session_state["research_results"] = results
    at.session_state["page"] = page
    at.run(timeout=30)
    assert not at.exception, at.exception
    return at


def test_copy_bar_enabled_on_each_results_page():
    for page in ("brief", "evidence", "checks"):
        at = _app(_with_report("BLOCKED"), page)
        buttons = {b.proto.label: b for b in at.get("download_button")}
        for label in ("Brief .md", "Claims .csv", "Ledger .json", "Post .txt", "Card .svg"):
            hit = [b for lab, b in buttons.items() if label in lab]
            assert hit, (page, label)
            assert not hit[0].proto.disabled, (page, label)
        assert any("Your copy" in str(m.value) for m in at.markdown), page


def test_share_pack_downloads_enabled_when_blocked():
    at = _app(_with_report("BLOCKED"), "checks")
    for b in at.get("download_button"):
        assert not b.proto.disabled, b.proto.label


def test_publish_still_gated_and_old_blocks_gone():
    web = Path("web_app.py").read_text(encoding="utf-8")
    assert "disabled=share_blocked" not in web and "Export Prohibited" not in web
    assert 'disabled=not publish_ready' in web
