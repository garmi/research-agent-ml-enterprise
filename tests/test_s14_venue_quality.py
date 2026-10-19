"""Tests for Slice S14: sources are tiered, labelled and ranked by venue quality; G4 catches unsupported intensifiers.

Run job_58abf30b95bc kept 10 papers, most from low-tier journals, yet each was labelled "Peer-Reviewed
Journal", and the tier matcher used substrings: "science" matched "Journal of Computer Science and
Technology Studies", "chi" matched "machine", "ase" matched "database". The brief also said
"significantly enhance" and "substantially enhances" on weak evidence, and G4 checks verbs only.

Requirements:
1. Venue tiers match whole words; patterns starting with "=" must equal the whole venue name. Known
   low-tier names are checked before the verified list, so an explicit unverified entry always wins.
2. A journal or conference whose venue is not verified is labelled "Journal (venue not verified)" or
   "Conference (venue not verified)", on the Evidence tab and in the ledger (peer_reviewed only when verified).
3. Ranking weighs relevance by venue tier (configured weights): among equally relevant papers, verified
   venues come first; a clearly more relevant paper is not pushed out by an irrelevant verified one.
4. G4 flags intensifiers ("significantly", "substantially", ...) that the cited quotes do not themselves
   use; the configured list lives in synth/strength_verbs.yaml.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.grade.grader import Grader
from src.ledger.models import Claim, OutputSentence


# ------------------------------------------------------------------------------
# Test 1: Whole-word tiers
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("venue,tier", [
    ("International Journal of Scientific Research in Science Engineering and Technology", "unverified"),
    ("Journal of Computer Science and Technology Studies", "unverified"),
    ("European journal of computer science and information technology", "unverified"),
    ("Machine Learning with Applications", "unverified"),
    ("Database Systems Review", "unverified"),
    ("International Journal of Science and Research", "unverified"),
    ("Science", "verified"),
    ("Nature Communications", "verified"),
    ("IEEE Transactions on Software Engineering", "verified"),
    ("Proceedings of the ACM on Software Engineering", "verified"),
    ("CHI Conference on Human Factors in Computing Systems", "verified"),
    ("2024 39th IEEE/ACM International Conference on Automated Software Engineering (ASE)", "verified"),
    ("Empirical Software Engineering", "verified"),
    ("arXiv (Cornell University)", "reputable_preprint"),
])
def test_tiers_match_whole_words(venue, tier):
    assert Grader().resolve_venue_tier(venue, "Peer-Reviewed Journal") == tier


# ------------------------------------------------------------------------------
# Test 2: Labels follow the tier
# ------------------------------------------------------------------------------
def test_labels_follow_the_tier():
    from src.analysis.multilane_runner import labelled_venue

    g = Grader()
    venue, label, tier = labelled_venue({"venue": "Journal of Computer Science and Technology Studies", "doi": "10.32996/x"}, g)
    assert (label, tier) == ("Journal (venue not verified)", "unverified")
    _, label, tier = labelled_venue({"venue": "IEEE Transactions on Software Engineering", "doi": "10.1109/TSE.1"}, g)
    assert (label, tier) == ("Peer-Reviewed Journal", "verified")
    _, label, _ = labelled_venue({"venue": "International Conference on Smart Things", "doi": "10.1/x"}, g)
    assert label == "Conference (venue not verified)"
    _, label, tier = labelled_venue({"doi": "10.2139/ssrn.1", "venue": "Elsevier BV"}, g)
    assert (label, tier) == ("Preprint", "reputable_preprint")
    src = Path("src/analysis/multilane_runner.py").read_text(encoding="utf-8")
    assert src.count("labelled_venue(p, self.grader)") >= 2
    assert 'source_type="peer_reviewed" if venue_tier == "verified" else "preprint"' in src


# ------------------------------------------------------------------------------
# Test 3: Ranking prefers verified venues
# ------------------------------------------------------------------------------
def test_ranking_weighs_relevance_by_tier():
    from src.analysis.relevance import rank_papers_by_tier

    weights = {"verified": 1.0, "reputable_preprint": 0.9, "unverified": 0.6}
    topic = "AI code generation in platform engineering teams"
    same = "AI code generation in platform engineering teams: a study"
    papers = [
        {"title": same, "abstract": "AI code generation platform engineering teams adoption.", "venue": "Mill Journal"},
        {"title": same + " (b)", "abstract": "AI code generation platform engineering teams adoption.", "venue": "Empirical Software Engineering"},
        {"title": "Irrigation pumps", "abstract": "Solar irrigation in farms.", "venue": "Nature Communications"},
    ]
    tier_of = {"Mill Journal": "unverified", "Empirical Software Engineering": "verified", "Nature Communications": "verified"}
    ranked = rank_papers_by_tier(papers, topic, lambda p: tier_of[p["venue"]], weights)
    assert [p["venue"] for p in ranked] == ["Empirical Software Engineering", "Mill Journal", "Nature Communications"]
    assert ranked[0]["venue_tier"] == "verified" and ranked[1]["tier_weight"] == 0.6

    cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    assert cfg["research"]["venue_tier_weights"]["verified"] > cfg["research"]["venue_tier_weights"]["unverified"]
    assert "rank_papers_by_tier(" in Path("src/analysis/multilane_runner.py").read_text(encoding="utf-8")


# ------------------------------------------------------------------------------
# Test 4: Unsupported intensifiers fail G4
# ------------------------------------------------------------------------------
def _g4(text, excerpt, grade="moderate"):
    from src.score.checker import GateChecker

    c = Claim(id="c1", source_id="s", text=excerpt, source_excerpt=excerpt, grade=grade)
    s = OutputSentence(id="s1", output_id="o", ordinal=1, text=text, type="assertive", claim_ids_json=["c1"])
    res = GateChecker().check_output(sentences=[s], ledger_claims={"c1": c})
    return res.state("G4"), " ".join(res.violations["G4"])


def test_unsupported_intensifier_fails_g4():
    state, why = _g4("Multi-agent frameworks significantly enhance test generation [P1].",
                     "multi-agent frameworks enhance test generation in ERP projects")
    assert state == "FAIL" and "significantly" in why
    assert _g4("Multi-agent frameworks significantly enhance test generation [P1].",
               "a statistically significant improvement in test generation")[0] == "PASS"
    assert _g4("Pipelines substantially reduce rework [P1].", "pipelines reduce rework")[0] == "FAIL"
    assert _g4("Pipelines reduce rework [P1].", "pipelines reduce rework")[0] == "PASS"
    cfg = yaml.safe_load(Path("synth/strength_verbs.yaml").read_text(encoding="utf-8"))
    assert {"significantly", "substantially", "dramatically"} <= set(cfg["intensifiers"])
