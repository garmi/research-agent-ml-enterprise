"""Tests for Slice S22b: fixes from live run job_92978bf81492 (8 enterprise sources found, none cited; G4 x5).

Requirements:
1. The report prompt asks each section to use the E# practice sources that speak to its sub-question, with an
   evidence example citing [E#]; single-source wording respects the verb caps: "according to one vendor" for a
   vendor (level 2), "one organisation reports" for other practice sources (level 3).
2. A page not on the vendor list is still a vendor page when it carries sales cues (book a demo, start a free
   trial, pricing, sign up free); an independent write-up without them stays a practitioner write-up.
3. Before the gates run, a sentence whose verb is stronger than its weakest cited claim allows has that verb
   softened by rule to the strongest allowed one ("observes"/"indicates" -> "reports" for weak claims, -> "states"
   for vendor claims), keeping capitalisation; each change is recorded in checks_json["verb_softened"]. A sentence
   within its cap, or with no cited claims, is unchanged. The gates themselves are unchanged.
"""

from __future__ import annotations

from src.ledger.models import Claim


# ------------------------------------------------------------------------------
# Test 1: Prompt
# ------------------------------------------------------------------------------
def test_prompt_uses_practice_sources_within_caps():
    from src.prompts.research_prompts import ResearchPromptLibrary

    compact = [{"paper_id": "P1", "title": "T"}, {"paper_id": "E1", "title": "Acme", "source_type": "Vendor says"}]
    p = ResearchPromptLibrary.report("t", compact, ["Q1?"], question="Q?")
    assert "according to one vendor" in p and "one organisation reports" in p
    assert "one vendor reports" not in p
    assert "[E1]" in p or "[E2]" in p, "an evidence example cites an E# source"
    assert "each section" in p.lower() and "E#" in p


# ------------------------------------------------------------------------------
# Test 2: Vendor cues
# ------------------------------------------------------------------------------
def test_sales_cues_mark_a_vendor():
    from src.collectors.enterprise.grounded import classify_source

    sales = "AI code review for every pull request. Book a demo or start your free trial today. See pricing."
    assert classify_source("https://www.qodo.ai/blog/ai-review", "How to build AI PR review", sales)["label"] == "Vendor says"
    plain = "Our platform team moved code review to a two-step process and measured time to first review for a quarter."
    assert classify_source("https://engineering.example.org/review", "How we review", plain)["label"] == "Practitioner write-up"


# ------------------------------------------------------------------------------
# Test 3: Verb softening
# ------------------------------------------------------------------------------
def _claims():
    return {"w": Claim(id="w", source_id="s1", text="Teams merged faster.", source_excerpt="merged faster", grade="weak"),
            "m": Claim(id="m", source_id="s2", text="Teams merged faster.", source_excerpt="merged faster", grade="moderate"),
            "v": Claim(id="v", source_id="s3", text="Our bot finds bugs.", source_excerpt="finds bugs", grade="vendor_claim")}


def test_soften_verbs():
    from src.score.checker import GateChecker
    from src.synth.generator import soften_verbs

    ch, cl = GateChecker(), _claims()
    text, changes = soften_verbs("One study observes that teams merged faster [P1].", [cl["w"]], ch)
    assert text == "One study reports that teams merged faster [P1]." and changes == [["observes", "reports"]]
    text, _ = soften_verbs("Indicates a shift [P1].", [cl["w"]], ch)
    assert text.startswith("Reports a shift")
    text, changes = soften_verbs("One vendor shows its bot finds bugs [E1].", [cl["v"]], ch)
    assert "states" in text and "shows" not in text and "finds" not in text and len(changes) == 2
    assert soften_verbs("One study suggests teams merged faster [P2].", [cl["m"]], ch) == (
        "One study suggests teams merged faster [P2].", [])
    assert soften_verbs("No citation here shows nothing.", [], ch) == ("No citation here shows nothing.", [])


def test_field_note_sentences_softened_before_gates(tmp_path):
    from src.ledger.migrations import apply_migrations
    from src.ledger.models import Question, Run, Source
    from src.ledger.repository import LedgerRepository
    from src.synth.generator import SynthesisEngine

    db = str(tmp_path / "l.db")
    apply_migrations(db_path=db)
    repo = LedgerRepository(db_path=db)
    repo.insert_question(Question(id="q", text="Does shared review help teams merge faster?"))
    repo.insert_run(Run(id="r", question_ids=["q"]))
    repo.insert_source(Source(id="sa", lane="academic", source_type="preprint", title="Shared review study"))
    c = Claim(id="c_sa", question_id="q", source_id="sa", text="The study reports that teams with shared review merged faster.",
              source_excerpt="teams with shared review merged faster", grade="weak")
    repo.insert_claim(c)
    synth = {"executive_summary": "Shared review indicates faster merging [P1].",
             "sections": [{"sub_question": "Does shared review help?", "synthesis": [],
                           "evidence": ["One study observes that teams with shared review merged faster [P1]."]}]}
    _, sentences, summary = SynthesisEngine(db_path=db).build_field_note(
        question_id="q", run_id="r", executive_synthesis=synth, papers=[{"id": "sa"}], claims_override=[repo.get_claim("c_sa")])
    ev = next(s for s in sentences if s.type == "assertive")
    assert "observes" not in ev.text and "reports that teams" in ev.text
    assert (ev.checks_json or {}).get("verb_softened") == [["observes", "reports"]]
    g4 = (summary.get("gate_results") or {}).get("violations", {}).get("G4") or []
    assert not any("observes" in v or "indicates" in v for v in g4)
