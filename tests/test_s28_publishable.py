"""Tests for Slice S28: briefs that can be shared with confidence.

Requirements:
1. A synthesis-like sentence that cites claims from a single source and has no single-source wording is marked
   by rule before the gates: a cross-study lead-in ("Taken together,") is dropped and ", according to one study"
   (or "one vendor" / "one organisation" for enterprise sources) goes before its tags. The change is recorded in
   checks_json["single_source_marked"]; G4 then passes it. Sentences citing two or more sources are unchanged.
2. Papers from journals, conferences or publications whose venue is not verified are set aside by default
   (research.exclude_unverified_venues), keeping preprints and operator-added papers; the set-aside count is
   reported. If fewer than research.min_verified_papers remain, the best unverified papers are kept and the run
   says so.
3. Check D verifies citation support: each grounded sentence is judged against the exact quotes it cites
   (supported / partial / unsupported, with a reason), in batches, by the model; without a model the rule
   verdict is used (all figures present and two or more shared terms with some quote, else "unchecked").
   Practitioner quotes are never sent to the model (DEC-013).
4. The run reports the support rate; any unsupported sentence blocks publishing (status BLOCKED with a Check D
   reason). The Checks & publish tab shows the rate and each judged sentence, unsupported first, and lets the
   reviewer tick the sentences they verified themselves.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.ledger.models import Claim, OutputSentence


# ------------------------------------------------------------------------------
# Test 1: Single-source marking
# ------------------------------------------------------------------------------
def test_mark_single_source():
    from src.score.checker import GateChecker
    from src.synth.generator import mark_single_source

    ch = GateChecker()
    one = [Claim(id="a", source_id="s1", text="t", source_excerpt="e", grade="moderate")]
    two = one + [Claim(id="b", source_id="s2", text="t", source_excerpt="e", grade="moderate")]
    text, mark = mark_single_source("Taken together, review gates cut defects [P3].", "synthesis", one, ch)
    assert text == "Review gates cut defects, according to one study [P3]." and mark == "one study"
    text, mark = mark_single_source("Teams cut wait time [E2].", "synthesis", one, ch, labels={"s1": "Vendor says"})
    assert text == "Teams cut wait time, according to one vendor [E2]."
    text, mark = mark_single_source("Teams cut wait time [E2].", "synthesis", one, ch, labels={"s1": "Practitioner write-up"})
    assert text.endswith("according to one organisation [E2].")
    assert mark_single_source("Review gates cut defects [P3][P4].", "synthesis", two, ch) == ("Review gates cut defects [P3][P4].", "")
    assert mark_single_source("One study reports cuts [P3].", "synthesis", one, ch)[1] == ""
    assert mark_single_source("Review gates cut defects [P3].", "assertive", one, ch)[1] == "", "evidence sentences are about one source anyway"


# ------------------------------------------------------------------------------
# Test 2: Unverified venues
# ------------------------------------------------------------------------------
def test_unverified_venues_set_aside():
    from src.analysis.multilane_runner import set_aside_unverified

    papers = [{"id": "a", "label": "Peer-Reviewed Journal"}, {"id": "b", "label": "Journal (venue not verified)"},
              {"id": "c", "label": "Preprint"}, {"id": "d", "label": "Publication (venue not verified)", "is_custom": True},
              {"id": "e", "label": "Conference (venue not verified)"}, {"id": "f", "label": "Conference"}]
    kept, aside, note = set_aside_unverified(papers, min_keep=3)
    assert [p["id"] for p in kept] == ["a", "c", "d", "f"] and [p["id"] for p in aside] == ["b", "e"]
    assert "2 papers from unverified venues" in note
    kept, aside, note = set_aside_unverified(papers[:2], min_keep=3)
    assert [p["id"] for p in kept] == ["a", "b"] and not aside and "kept" in note.lower()


# ------------------------------------------------------------------------------
# Test 3: Check D
# ------------------------------------------------------------------------------
def _sent(i, text, cids, typ="assertive"):
    return OutputSentence(id=f"s{i}", output_id="o", ordinal=i, text=text, type=typ, claim_ids_json=cids)


CLAIMS = {
    "c1": Claim(id="c1", source_id="p1", text="The study reports that AI review cut first-review wait by 30% in 12 teams.",
                source_excerpt="AI review cut first-review wait by 30% (Location: Abstract)", grade="moderate"),
    "c2": Claim(id="c2", source_id="p2", text="The study reports that reviewers ignored most bot comments.",
                source_excerpt="reviewers ignored most bot comments (Location: Abstract)", grade="weak"),
    "cp": Claim(id="cp", source_id="prac1", text="Our client X cut review time.", source_excerpt="client X", grade="anecdote"),
}
LANES = {"p1": "academic", "p2": "academic", "prac1": "practitioner"}
SENTS = [_sent(1, "One study reports AI review cut first-review wait by 30% [P1].", ["c1"]),
         _sent(2, "One study reports reviewers ignored most bot comments [P2].", ["c2"]),
         _sent(3, "Teams halved defects [P1].", ["c1"]),
         _sent(4, "A heading", [], "heading"),
         _sent(5, "Field note says review time fell.", ["cp"])]


class Judge:
    model = "fake"

    def __init__(self):
        self.prompts = []

    def generate(self, prompt, system_prompt=None, temperature=0.0, json_mode=False):
        self.prompts.append(prompt)
        return json.dumps({"verdicts": [{"id": "S1", "verdict": "supported", "reason": "Quote states the 30% cut."},
                                        {"id": "S2", "verdict": "partial", "reason": "Quote says most, sentence says most."},
                                        {"id": "S3", "verdict": "unsupported", "reason": "No quote mentions defects."}]})


def test_check_d_with_model():
    from src.engine.check_d_support import run_check_d

    judge = Judge()
    res = run_check_d(SENTS, CLAIMS, LANES, judge)
    v = {i["sentence_id"]: i["verdict"] for i in res["items"]}
    assert v == {"s1": "supported", "s2": "partial", "s3": "unsupported", "s5": "local, not checked"}
    assert res["checked"] == 3 and res["supported"] == 1 and res["unsupported"] == 1
    assert res["rate"] == round(1 / 3, 3)
    sent = " ".join(judge.prompts)
    assert "client X" not in sent, "practitioner quotes never reach the model"
    assert "cut first-review wait by 30%" in sent


def test_check_d_rules_without_model():
    from src.engine.check_d_support import run_check_d

    res = run_check_d(SENTS, CLAIMS, LANES, None)
    v = {i["sentence_id"]: i["verdict"] for i in res["items"]}
    assert v["s1"] == "supported" and v["s3"] == "unchecked"
    assert res["method"] == "rules"


def test_unsupported_blocks_publishing():
    from src.engine.check_d_support import apply_check_d

    result = {"status": "PUBLISH_READY", "publish_res": {"status": "PUBLISH_READY", "allowed": True, "reasons": ["ok"]}}
    apply_check_d(result, {"checked": 3, "supported": 1, "partial": 1, "unsupported": 1, "rate": 0.333, "items": []})
    assert result["status"] == "BLOCKED" and result["publish_res"]["allowed"] is False
    assert "Check D" in result["publish_res"]["reasons"][0]
    ok = {"status": "PUBLISH_READY", "publish_res": {"status": "PUBLISH_READY", "allowed": True, "reasons": ["ok"]}}
    apply_check_d(ok, {"checked": 3, "supported": 3, "partial": 0, "unsupported": 0, "rate": 1.0, "items": []})
    assert ok["status"] == "PUBLISH_READY" and ok["publish_res"]["allowed"] is True


def test_checks_tab_shows_support():
    web = Path("web_app.py").read_text(encoding="utf-8")
    tab = web[web.index("with tab_checks:"):]
    assert 'results.get("check_d")' in tab and "Citation support" in tab
    assert "Verified by me" in tab
