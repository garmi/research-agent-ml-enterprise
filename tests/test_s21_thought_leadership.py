"""Tests for Slice S21: a thought-leadership summary in an executive LinkedIn voice, and a share pack.

Requirements:
1. The summary prompt asks for a first-person executive post (hook, opening, 3-7 cited takeaways, what it means
   for leaders, the nuance, what to watch, one closing question, 3-5 hashtags), forbids invented experience,
   gives the evidence profile, and carries no topic example.
2. Rules decide what is kept:
   - a takeaway must pass the synthesis gates (cite; two or more sources or single-source wording; no figure
     absent from its claims), be at most two sentences, and invent no experience; at most 7 are kept, each
     labelled "N papers · method";
   - "I reviewed N studies" opens the post with the real N, and the model's own count is removed;
   - a hook over 20 words, or one inventing experience, is replaced; any other field inventing experience is
     dropped;
   - exactly one closing question, ending "?"; 3-5 hashtags, filled from the question's subject when short;
   - when most cited papers are not empirical, the nuance says so;
   - no takeaway passing means no summary.
3. The post text has the hook first, numbered takeaways, a "What this means for leaders" turn, the question and
   hashtags, no [P#] tags in its body, and sources as a numbered list at the end; a draft carries a draft line.
4. The image card is a 1200x1200 SVG with the hook, the diagram when there is one, and up to three takeaways;
   a draft carries a DRAFT watermark. Text is escaped.
5. The run asks for the summary after the report is checked (no separate content-ideas call); the payload
   carries "summary" (None for an extractive-fallback run).
6. A "Summary & share" tab shows the summary and the share pack (copyable post, .md/.txt/.svg downloads).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.ledger.models import Claim

PAPERS = [{"id": "s1", "key": "P1", "title": "Study one", "year": "2025", "url": "https://doi.org/10.1/1"},
          {"id": "s2", "key": "P2", "title": "Study two", "year": "2024", "url": "https://doi.org/10.1/2"},
          {"id": "s3", "key": "P3", "title": "Study three", "year": "2026", "url": "https://doi.org/10.1/3"}]
CLAIMS = {f"c{i}": Claim(id=f"c{i}", source_id=f"s{i}", text=f"Teams that adopted shared review steps scaled more smoothly in study {i}.",
                         source_excerpt=f"teams that adopted shared review steps scaled more smoothly {i}", grade="moderate")
          for i in (1, 2, 3)}
REPORT = {"answer": {"text": "Teams scale with shared review [P1][P2]."}, "sections": [
    {"index": 1, "sub_question": "Which practices help?", "sentences": [],
     "table": [{"paper": "P1", "method": "empirical"}, {"paper": "P2", "method": "conceptual"},
               {"paper": "P3", "method": "not stated"}]}]}

RAW = {
    "hook": "Shared review is the quiet habit behind teams that scale.",
    "opening": "I reviewed 40 papers on this. The pattern was clearer than I expected.",
    "takeaways": [
        "Teams that adopted shared review steps scaled more smoothly [P1][P2].",
        "One study reports that teams adopting shared review steps scaled more smoothly [P3].",
        "Teams that adopted shared review steps scaled 3x faster [P1][P2].",
        "Shared review steps help teams scale more smoothly [P3].",
        "In my team we found shared review steps helped us scale smoothly [P1][P2].",
        "Teams adopted shared review steps. They scaled. They kept it [P1][P2].",
    ],
    "for_leaders": "Make review a shared step before you scale a tool.",
    "nuance": "The evidence is promising but not settled.",
    "watch_next": "Whether the effect holds outside early adopters.",
    "question": "Where does review sit in your rollout? What would you change?",
    "hashtags": ["Leadership", "#scaling", "not a tag!"],
}


def _summary(raw=None, n=15):
    from src.score.checker import GateChecker
    from src.synth.thought_leadership import build_summary

    return build_summary(raw if raw is not None else RAW, REPORT, PAPERS, CLAIMS, GateChecker(),
                         n_reviewed=n, subject=["shared", "review", "teams"])


# ------------------------------------------------------------------------------
# Test 1: Summary prompt
# ------------------------------------------------------------------------------
def test_prompt_voice_and_profile():
    from src.prompts.research_prompts import ResearchPromptLibrary

    p = ResearchPromptLibrary.thought_leadership("What helps teams scale?", ["1. Which practices help?"],
                                                 {"papers": 3, "empirical": 1, "conceptual": 1, "not_stated": 1})
    for needed in ("first person", "hook", "takeaways", "for_leaders", "nuance", "watch_next", "question",
                   "hashtags", "3-7", "[P#]", "Never invent", "1 empirical"):
        assert needed in p, needed
    for topical in ("deployment frequency", "code", "software", "LLM"):
        assert topical not in p, topical


# ------------------------------------------------------------------------------
# Test 2: Rules
# ------------------------------------------------------------------------------
def test_takeaways_pass_synthesis_rules_and_guard():
    s = _summary()
    texts = [t["text"] for t in s["takeaways"]]
    assert texts == [RAW["takeaways"][0], RAW["takeaways"][1]], texts
    assert s["takeaways"][0]["papers"] == ["P1", "P2"]
    assert s["takeaways"][0]["basis"] == "2 papers · 1 empirical, 1 conceptual"
    assert s["takeaways"][1]["basis"] == "1 paper · method not stated"
    reasons = " ".join(s["dropped"])
    assert "invents experience" in reasons and "figure" in reasons and "one source" in reasons


def test_reviewed_count_by_rule():
    s = _summary(n=15)
    assert s["opening"].startswith("I reviewed 15 studies")
    assert "40 papers" not in s["opening"] and "clearer than I expected" in s["opening"]


def test_hook_question_hashtags():
    s = _summary()
    assert s["hook"] == RAW["hook"]
    long = dict(RAW, hook=" ".join(["word"] * 21))
    assert len(_summary(long)["hook"].split()) <= 20
    invented = dict(RAW, hook="At my company we rolled this out last year.", watch_next="We built a pilot.")
    s2 = _summary(invented)
    assert "my company" not in s2["hook"] and s2["watch_next"] == ""
    assert s["question"].endswith("?") and s["question"].count("?") == 1
    assert 3 <= len(s["hashtags"]) <= 5 and all(re.fullmatch(r"#[A-Za-z0-9]+", h) for h in s["hashtags"])
    assert "#Leadership" in s["hashtags"] and "#Scaling" in s["hashtags"]
    assert not any("[P" in s[k] for k in ("hook", "opening", "for_leaders", "nuance", "watch_next", "question"))


def test_nuance_reflects_profile():
    s = _summary()
    assert "conceptual" in s["nuance"].lower()


def test_no_passing_takeaway_no_summary():
    assert _summary(dict(RAW, takeaways=["Shared review helps teams scale [P3]."])) is None
    assert _summary("not json") is None


# ------------------------------------------------------------------------------
# Test 3: Post text
# ------------------------------------------------------------------------------
def test_post_text_format():
    from src.output.share_pack import post_text

    s = _summary()
    post = post_text(s, PAPERS, published=False)
    body, _, sources = post.partition("Sources")
    assert post.splitlines()[0].startswith("DRAFT")
    assert s["hook"] in body.splitlines()[2]
    assert "1. Teams that adopted shared review steps scaled more smoothly." in body
    assert "What this means for leaders" in body
    assert "[P" not in body
    assert body.strip().endswith(" ".join(s["hashtags"]))
    assert "1. Study one (2025) https://doi.org/10.1/1" in sources and "3. Study three" in sources
    assert not post_text(s, PAPERS, published=True).startswith("DRAFT")


# ------------------------------------------------------------------------------
# Test 4: Image card
# ------------------------------------------------------------------------------
def test_image_card_svg():
    from src.output.share_pack import image_card_svg

    s = _summary()
    s["hook"] = "Review <first> & scale"
    diagram = {"type": "pathway", "title": "T", "nodes": [{"id": "a", "label": "Pilot", "cites": ["P1"]},
                                                         {"id": "b", "label": "Scale", "cites": ["P2"]}],
               "edges": [{"from": "a", "to": "b", "label": ""}]}
    svg = image_card_svg(s, diagram, published=False)
    assert 'viewBox="0 0 1200 1200"' in svg and "Review &lt;first&gt; &amp; scale" in svg
    assert "Pilot" in svg and "DRAFT" in svg and "\n\n" not in svg
    assert "Teams that adopted shared review steps" in svg and "[P" not in svg
    assert "DRAFT" not in image_card_svg(s, None, published=True)


# ------------------------------------------------------------------------------
# Test 5: Run payload
# ------------------------------------------------------------------------------
def test_run_payload_has_summary(tmp_path, monkeypatch):
    from tests.test_s20_visuals import FakeLLM, _run, _spec

    class SummaryLLM(FakeLLM):
        def generate(self, prompt, system_prompt=None, temperature=0.3, json_mode=False):
            if "thought-leadership" in prompt.lower():
                self.prompts.append(prompt)
                return json.dumps(dict(RAW, takeaways=["Teams that adopted shared review steps reported smoother scaling [P1][P2]."]))
            return super().generate(prompt, system_prompt, temperature, json_mode)

    llm = SummaryLLM(_spec())
    res = _run(tmp_path, monkeypatch, llm)
    assert res["summary"] and res["summary"]["opening"].startswith("I reviewed 3 studies")
    assert not any("content ideas" in p.lower() or "linkedin" in p.lower() for p in llm.prompts
                   if "thought-leadership" not in p.lower())
    (tmp_path / "b").mkdir()
    assert _run(tmp_path / "b", monkeypatch, SummaryLLM(_spec()), provider="stub")["summary"] is None


# ------------------------------------------------------------------------------
# Test 6: Summary & share tab
# ------------------------------------------------------------------------------
def test_summary_tab_renders(tmp_path):
    from streamlit.testing.v1 import AppTest

    results = json.loads(Path("tests/fixtures/s18_saved_run.json").read_text(encoding="utf-8"))
    results["summary"] = _summary()
    at = AppTest.from_file("web_app.py")
    at.session_state["research_results"] = results
    at.run(timeout=30)
    assert not at.exception, at.exception
    assert any(t.label == "Summary & share" for t in at.tabs)
    text = " ".join(str(m.value) for m in at.markdown)
    assert RAW["hook"] in text
    assert any("Shared review" in str(c.value) for c in at.code), "the post is in a copyable code block"
    labels = " ".join(str(b.label) for b in at.get("download_button"))
    for needed in ("Post (.md)", "Post (.txt)", "Image card (.svg)"):
        assert needed in labels, needed
