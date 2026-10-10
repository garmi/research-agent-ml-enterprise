"""Offline smoke tests with a fake LLM (no network, no Ollama)."""
import json

from src.analysis.synthesizer import SynthesisEngine
from src.app import merge_papers
from src.output.content_pack import ContentPackBuilder
from src.output.report_builder import ReportBuilder


class FakeLLM:
    def generate(self, prompt, system_prompt=None, temperature=0.3, json_mode=False):
        if "compact summaries of research papers" in prompt:
            return json.dumps({
                "executive_summary": "S", "objective": "O",
                "key_findings": ["Finding one [P1]", "Bogus [P9]"],
                "themes": [{"name": "t", "description": "d"}],
                "business_problems": [{"problem": "p"}],
            })
        if "actionable recommendations" in prompt:
            return json.dumps({"recommendations": [
                {"action": "Run a pilot.", "owner": "CTO", "why": "Because.", "evidence": ["P1"]}]})
        if "execution roadmap" in prompt:
            return json.dumps({"strategic_roadmap": [
                {"stage": "0-6 months", "objective": "o", "actions": [{"a": "x"}], "kpis": ["k"]}]})
        if "LinkedIn" in prompt:
            return json.dumps({"content_ideas": ["hook"]})
        return "```json\n" + json.dumps({"problem_statement": ["x", "y"], "key_findings": "kf", "confidence_score": 8}) + "\n```"


def test_dedupe():
    a = [{"title": "Hello, World!", "doi": "10.1/x"}]
    b = [{"title": "hello world", "arxiv_id": "1"}, {"title": "Other", "doi": "10.1/X"}]
    assert len(merge_papers([a, b])) == 1


def test_pipeline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    papers = [{"title": "P", "abstract": "a" * 100, "year": 2024, "source": "arXiv", "url": "http://x"}]
    out = SynthesisEngine(FakeLLM(), on_progress=lambda m: None).analyze("topic", papers)
    assert out["paper_summaries"][0]["confidence_score"] == 0.8
    assert out["executive_summary"] == "S"
    assert out["recommendations"][0] == "Run a pilot (Owner: CTO) - Because. [P1]"
    assert out["strategic_roadmap"][0]["actions"] == ["x"]
    assert out["content_ideas"] == ["hook"]
    assert out["citation_check"]["invalid_ids"] == ["P9"]
    assert out["references"][0].startswith("[P1] P (2024)")
    out["papers"] = papers
    out["content_pack"] = ContentPackBuilder("topic").build(out)
    assert out["content_pack"]["linkedin_post_ideas"] == ["hook"]
    assert "Research Brief" in ReportBuilder().build_markdown("topic", out)


def test_build_topic_queries():
    from src.app import build_topic_queries
    queries = build_topic_queries("how Kiro is being used for development by engineering teams")
    assert any("kiro" in q.lower() for q in queries)
    assert any("spec driven" in q.lower() for q in queries)


def test_openalex_abstract_reconstruction():
    from src.fetchers.openalex_client import OpenAlexClient
    inverted = {"Hello": [0], "world": [1], "again": [2]}
    assert OpenAlexClient._reconstruct_abstract(inverted) == "Hello world again"
    assert OpenAlexClient._reconstruct_abstract(None) == ""
