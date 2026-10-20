"""Tests for Slice S20: a cited diagram drawn from a validated spec, and the evidence map in the export.

Requirements:
1. The diagram prompt asks for one spec (type pathway, architecture, comparison, cause_effect or none; at most 6
   nodes; labels of at most 40 characters; every node cites [P#]) and carries no topic example.
2. Validation is by rule and never asks the model again:
   - an unknown type, more than 6 nodes, or a label over 40 characters drops the whole spec;
   - a node whose cites resolve to no claim in this run is dropped, with its edges;
   - fewer than 2 nodes left, or an architecture whose nodes cite fewer than 2 papers, gives no diagram;
   - edges join only kept nodes.
3. The renderer draws an SVG from the spec with no new dependency: one box per node with its escaped label and
   cites, one arrow per edge, laid out in layers so a chain a -> b -> c runs left to right. No blank lines (so it
   fits one Markdown block); nothing for no diagram.
4. The run asks for the diagram after the report is checked; the payload carries "diagram" (None for an invalid
   spec, and for an extractive-fallback run, which makes no diagram call).
5. The Brief tab shows the diagram after the answer; the brief download lists its steps and the evidence map.
"""

from __future__ import annotations

import json

from src.ledger.models import Claim

PAPERS = [{"id": "s1", "key": "P1"}, {"id": "s2", "key": "P2"}, {"id": "s3", "key": "P3"}]
CLAIMS = {f"c{i}": Claim(id=f"c{i}", source_id=f"s{i}", text=f"Teams adopted shared review steps in study {i}.",
                         source_excerpt=f"teams adopted shared review steps {i}", grade="moderate") for i in (1, 2)}


def _spec(**over):
    spec = {"type": "pathway", "title": "From pilot to scale", "nodes": [
        {"id": "a", "label": "Pilot with one team", "cites": ["P1"]},
        {"id": "b", "label": "Shared review steps", "cites": ["P2"]},
        {"id": "c", "label": "Scale across teams", "cites": ["P1", "P2"]},
    ], "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c", "label": "after review"}]}
    spec.update(over)
    return spec


# ------------------------------------------------------------------------------
# Test 1: Diagram prompt
# ------------------------------------------------------------------------------
def test_diagram_prompt_is_bounded_and_domain_neutral():
    from src.prompts.research_prompts import ResearchPromptLibrary

    p = ResearchPromptLibrary.diagram("What helps teams scale?", ["1. Which practices help? One study reports X [P1]."], ["P1", "P2"])
    for needed in ("pathway", "architecture", "comparison", "cause_effect", "none", "6", "40", "[P#]", "P1, P2"):
        assert needed in p, needed
    for topical in ("deployment frequency", "code", "software", "LLM"):
        assert topical not in p, topical


# ------------------------------------------------------------------------------
# Test 2: Validation by rule
# ------------------------------------------------------------------------------
def test_valid_spec_kept():
    from src.synth.diagram import validate_diagram

    d = validate_diagram(_spec(), PAPERS, CLAIMS)
    assert d["type"] == "pathway" and [n["id"] for n in d["nodes"]] == ["a", "b", "c"]
    assert d["nodes"][2]["cites"] == ["P1", "P2"] and len(d["edges"]) == 2


def test_whole_spec_dropped_when_out_of_bounds():
    from src.synth.diagram import validate_diagram

    assert validate_diagram(_spec(type="mindmap"), PAPERS, CLAIMS) is None
    assert validate_diagram(_spec(type="none"), PAPERS, CLAIMS) is None
    many = [{"id": str(i), "label": f"Step {i}", "cites": ["P1"]} for i in range(7)]
    assert validate_diagram(_spec(nodes=many, edges=[]), PAPERS, CLAIMS) is None
    long = _spec()
    long["nodes"][0]["label"] = "x" * 41
    assert validate_diagram(long, PAPERS, CLAIMS) is None
    assert validate_diagram("not json", PAPERS, CLAIMS) is None


def test_uncited_nodes_dropped_with_their_edges():
    from src.synth.diagram import validate_diagram

    spec = _spec()
    spec["nodes"][1]["cites"] = ["P3"]  # P3 has no claims in this run
    d = validate_diagram(spec, PAPERS, CLAIMS)
    assert [n["id"] for n in d["nodes"]] == ["a", "c"]
    assert d["edges"] == []
    spec["nodes"][0]["cites"] = []
    assert validate_diagram(spec, PAPERS, CLAIMS) is None, "one node left is no diagram"


def test_architecture_needs_two_papers():
    from src.synth.diagram import validate_diagram

    spec = _spec(type="architecture")
    for n in spec["nodes"]:
        n["cites"] = ["P1"]
    assert validate_diagram(spec, PAPERS, CLAIMS) is None
    assert validate_diagram(_spec(type="architecture"), PAPERS, CLAIMS)["type"] == "architecture"


# ------------------------------------------------------------------------------
# Test 3: SVG renderer
# ------------------------------------------------------------------------------
def test_svg_layered_escaped_one_block():
    import re

    from src.synth.diagram import validate_diagram
    from src.ui.diagrams import diagram_svg

    spec = _spec()
    spec["nodes"][0]["label"] = "Pilot <one> & learn"
    svg = diagram_svg(validate_diagram(spec, PAPERS, CLAIMS))
    assert svg.startswith("<svg") and svg.count("<rect") >= 3
    assert "Pilot &lt;one&gt; &amp; learn" in svg and "<one>" not in svg
    assert "P1 · P2" in svg and svg.count("marker-end") == 2
    assert "\n\n" not in svg
    xs = [float(x) for x in re.findall(r'<rect class="dg-node" x="([\d.]+)"', svg)]
    assert xs[0] < xs[1] < xs[2], "a chain runs left to right"
    assert diagram_svg(None) == ""


# ------------------------------------------------------------------------------
# Test 4: Run payload
# ------------------------------------------------------------------------------
Q = "Which practices help teams scale shared review?"
PKG = {"refined_question": Q, "sub_questions": ["Which practices help teams scale shared review?",
                                                 "What slows teams adopting shared review?"]}


class FakeLLM:
    model = "fake"

    def __init__(self, diagram):
        self.diagram = diagram
        self.prompts = []

    def generate(self, prompt, system_prompt=None, temperature=0.3, json_mode=False):
        self.prompts.append(prompt)
        if "Evaluate the following paper" in prompt:
            return json.dumps({"title": "T", "key_findings": "Teams adopted shared review steps.", "research_method": "survey of teams"})
        if "Answer each sub-question" in prompt:
            return json.dumps({
                "answer": ["Teams that adopted shared review steps reported smoother scaling [P1][P2]."],
                "sections": [
                    {"sub_question": PKG["sub_questions"][0], "synthesis": [],
                     "evidence": ["One study reports that teams adopted shared review steps [P1].",
                                  "One study reports that teams adopted shared review steps [P2]."]},
                    {"sub_question": PKG["sub_questions"][1], "synthesis": [], "evidence": []},
                ],
                "tensions": [], "gaps": [], "implications": [],
            })
        if "diagram" in prompt.lower() and "nodes" in prompt:
            return json.dumps(self.diagram)
        return "{}"


def _run(tmp_path, monkeypatch, llm, provider="gemini"):
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.ledger.migrations import apply_migrations
    import src.llm.factory as factory

    monkeypatch.setattr(factory, "build_llm", lambda p, cfg: llm)
    db, prac = str(tmp_path / "l.db"), str(tmp_path / "p.db")
    apply_migrations(db_path=db)
    apply_migrations(db_path=prac)
    r = MultiLaneResearchRunner(db_path=db, practitioner_db_path=prac, questions_yaml_path=str(tmp_path / "q.yaml"))
    r._harvest_enterprise_lane = lambda **kwargs: []
    r._build_check_llm = lambda provider: None
    r.config.setdefault("checks", {})["check_b"] = {"min_claims": 1, "min_sources": 1}
    papers = [{"id": f"p{i}", "title": f"Teams adopting shared review steps to scale, study {i}",
               "abstract": "Teams adopted shared review steps. Teams that adopted shared review steps reported smoother scaling.",
               "year": 2025, "venue": "Empirical Software Engineering", "url": f"https://doi.org/10.1/{i}"} for i in range(3)]
    return r.run_workflow(topic=Q, approved_question=Q, approved_package=PKG, map_provider=provider,
                          reduce_provider=provider, academic_papers_override=papers)


def test_run_payload_has_validated_diagram(tmp_path, monkeypatch):
    llm = FakeLLM(_spec())
    res = _run(tmp_path, monkeypatch, llm)
    assert res["is_fallback"] is False
    assert res["diagram"] and len(res["diagram"]["nodes"]) == 3
    prompt = next(p for p in llm.prompts if "diagram" in p.lower() and "nodes" in p)
    assert "One study reports" in prompt, "the diagram is drawn from the checked report sentences"


def test_invalid_spec_gives_no_diagram(tmp_path, monkeypatch):
    res = _run(tmp_path, monkeypatch, FakeLLM(_spec(type="mindmap")))
    assert res["diagram"] is None


def test_fallback_run_makes_no_diagram_call(tmp_path, monkeypatch):
    llm = FakeLLM(_spec())
    res = _run(tmp_path, monkeypatch, llm, provider="stub")
    assert res["diagram"] is None


# ------------------------------------------------------------------------------
# Test 5: Brief tab and export
# ------------------------------------------------------------------------------
REPORT = {"answer": {"text": "Teams scale with shared review [P1][P2].", "confidence": {}},
          "sections": [{"index": 1, "sub_question": "Which practices help?", "sentences": [],
                        "table": [{"paper": "P1", "method": "empirical"}, {"paper": "P2", "method": "conceptual"}],
                        "confidence": {}}],
          "tensions": [], "gaps": [], "implications": []}


def test_brief_shows_diagram_after_answer():
    from src.synth.diagram import validate_diagram
    from src.ui.brief_view import report_blocks

    blocks = report_blocks(REPORT, {}, {}, diagram=validate_diagram(_spec(), PAPERS, CLAIMS))
    assert "Answer in brief" in blocks[0]
    assert "<svg" in blocks[1] and "From pilot to scale" in blocks[1]
    assert not any("<svg" in b for b in report_blocks(REPORT, {}, {}))


def test_export_lists_diagram_and_evidence_map():
    from src.synth.diagram import validate_diagram
    from src.ui.brief_view import report_markdown

    md = report_markdown(REPORT, question="Q?", diagram=validate_diagram(_spec(), PAPERS, CLAIMS),
                         papers=[{"key": "P1", "title": "One"}, {"key": "P2", "title": "Two"}])
    assert "## From pilot to scale" in md
    assert "Pilot with one team [P1] → Shared review steps [P2]" in md
    assert "## Evidence map" in md and "| P1 | One | empirical | ● |" in md
