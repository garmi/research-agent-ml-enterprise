"""Tests for Slice S16: figures are grounded in the source sentence, and single-source figures say so.

Run job_89dfdbd56a81 failed G2 ten times, e.g. "contains ungrounded numeral '0.61'" for a finding whose
paper reports "from 0.61 to 0.97". The claim's full source sentence held the figure, but G2 only looked
at the 25-word quote (a copyright cap) and the first number in the claim's value. The same finding stated
a single preprint's self-reported figures as general fact.

Requirements:
1. G2 accepts a figure that appears in the claim's full source sentence (claim text), as well as its
   value or quote; a figure in none of them still fails. The citation binder uses the same rule.
2. A grounded sentence that states a figure and cites claims from only one source must say it rests on
   one study (configured phrases, e.g. "one study reports", "a single preprint"); otherwise G4 fails
   with that reason. Figures from two or more sources, and sentences without figures, are unaffected.
3. The analysis prompt asks for that wording, and its example finding no longer uses an intensifier.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.ledger.models import Claim, OutputSentence
from src.score.checker import GateChecker, claim_has_numeral

SENTENCE = "The study reports that EA-GKS raises the determinism coefficient from 0.61 to 0.97 and cuts audit effort by 74%."
QUOTE = "EA-GKS raises the determinism coefficient across TOGAF ADM, COBIT APO03 and EU AI Act standards in enterprise pilots"


def _claim(cid="c1", source="s9", text=SENTENCE, excerpt=QUOTE, grade="weak", value=None):
    return Claim(id=cid, source_id=source, text=text, source_excerpt=excerpt, grade=grade, value_json=value)


def _check(text, claims):
    s = OutputSentence(id="s1", output_id="o", ordinal=1, text=text, type="assertive", claim_ids_json=[c.id for c in claims])
    return GateChecker().check_output(sentences=[s], ledger_claims={c.id: c for c in claims})


# ------------------------------------------------------------------------------
# Test 1: Figures in the full source sentence are grounded
# ------------------------------------------------------------------------------
def test_figure_in_source_sentence_is_grounded():
    c = _claim()
    assert claim_has_numeral(c, "0.61") and claim_has_numeral(c, "0.97")
    assert not claim_has_numeral(c, "0.42")
    res = _check("One study reports that EA-GKS raises the determinism coefficient from 0.61 to 0.97 [P9].", [c])
    assert not any("ungrounded numeral" in v for v in res.violations["G2"])
    res = _check("One study reports that EA-GKS raises the determinism coefficient to 0.99 [P9].", [c])
    assert any("ungrounded numeral '0.99'" in v for v in res.violations["G2"])


def test_binder_prefers_claim_whose_sentence_has_the_figure():
    from src.synth.generator import resolve_citations

    with_fig = _claim("c_s9_1")
    without = _claim("c_s9_2", text="The study reports that EA-GKS raises the determinism coefficient in pilots.",
                     excerpt="EA-GKS raises the determinism coefficient in enterprise pilots across standards")
    claims = [without, with_fig]
    by_id = {c.id: c for c in claims}
    cids = resolve_citations("EA-GKS raises the determinism coefficient from 0.61 to 0.97 [P1].", [{"id": "s9"}], claims, by_id)
    assert cids[0] == "c_s9_1"


# ------------------------------------------------------------------------------
# Test 2: Single-source figures must say so
# ------------------------------------------------------------------------------
def test_single_source_figure_needs_one_study_wording():
    c = _claim()
    res = _check("EA-GKS raises the determinism coefficient from 0.61 to 0.97 [P9].", [c])
    assert res.state("G4") == "FAIL" and any("one study" in v for v in res.violations["G4"])
    for ok in ("One study reports that EA-GKS raises the determinism coefficient from 0.61 to 0.97 [P9].",
               "One early enterprise study reports that EA-GKS raises the determinism coefficient from 0.61 to 0.97 [P9].",
               "A single preprint reports that EA-GKS raises the determinism coefficient from 0.61 to 0.97 [P9]."):
        assert not any("one study" in v for v in _check(ok, [c]).violations["G4"]), ok


def test_multi_source_and_no_figure_unaffected():
    a = _claim("c_a", source="s1", text="The study reports that audit effort fell 74% with EA-GKS.",
               excerpt="audit effort fell 74% with EA-GKS determinism coefficient")
    b = _claim("c_b", source="s2", text="The study reports that audit effort fell 74% under architecture guidance.",
               excerpt="audit effort fell 74% under architecture guidance determinism coefficient")
    res = _check("Audit effort fell 74% with EA-GKS and the determinism coefficient [P1][P2].", [a, b])
    assert not any("one study" in v for v in res.violations["G4"])
    res = _check("EA-GKS raises the determinism coefficient in enterprise pilots [P9].", [_claim()])
    assert not any("one study" in v for v in res.violations["G4"])


def test_single_source_phrases_configured():
    cfg = yaml.safe_load(Path("synth/strength_verbs.yaml").read_text(encoding="utf-8"))
    phrases = cfg["single_source_phrases"]
    assert "one study" in phrases and "a single preprint" in phrases


# ------------------------------------------------------------------------------
# Test 3: The prompt asks for it
# ------------------------------------------------------------------------------
def test_prompt_asks_for_single_source_wording():
    from src.prompts.research_prompts import ResearchPromptLibrary as L

    text = L.analysis("t", [{"paper_id": "P1"}])
    assert "rests on one paper" in text and '"One study reports' in text
    assert "increased significantly" not in text
