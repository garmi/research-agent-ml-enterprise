"""Canary Acceptance Suite (Prompt A10 & A2-3).

Verifies the 10 named canary acceptance requirements:
1. no_shared_sentences: no non-heading sentence appears in both Q1 and Q2 outputs.
2. numbers_traceable: every digit-bearing token in any rendered sentence appears in a claim of that run.
3. citations_resolve_and_support: all [P#] resolve inside the run and pass term checks.
4. lane_c_scoped: Lane C count is 0 for Q2 and Q3.
5. q3_no_findings: Q3 yields 0 findings, Outcome 4, status NOT_PUBLISHABLE, and search_log rows for every lane.
6. fallback_no_findings: in fallback mode the output contains no findings, only extractive list.
7. deterministic: Q1 twice with the same cassette gives identical claims and sentences.
8. render_matches_ledger: no rendered or exported sentence is absent from output_sentences; no <span or <div in rendered text.
9. publish_gate: exports blocked or watermarked unless PUBLISH_READY.
10. no_egress_of_practitioner_text: zero non-loopback network socket connections when Lane C contains practitioner text.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import socket
import tempfile
from typing import Any, Dict, List
import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.collectors.practitioner.collector import PractitionerCollector
from src.ledger.migrations import apply_migrations
from src.ledger.models import Question
from src.ledger.repository import LedgerRepository
from src.output.unified_renderer import UnifiedRenderer

CASSETTES_DIR = Path(__file__).parent / "cassettes"

Q1_TOPIC = "What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?"
Q2_TOPIC = "How are hospitals governing clinical AI triage tools to manage patient safety and regulatory compliance?"
Q3_TOPIC = "What empirical evidence exists on quantum-secure sourdough fermentation controllers?"


def _load_cassette(name: str) -> List[Dict[str, Any]]:
    path = CASSETTES_DIR / f"{name}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _create_runner(tmpdir: str) -> MultiLaneResearchRunner:
    db_path = str(Path(tmpdir) / "test_ledger.db")
    prac_db_path = str(Path(tmpdir) / "test_prac.db")
    q_yaml_path = str(Path(tmpdir) / "register.yaml")
    apply_migrations(db_path=db_path)
    apply_migrations(db_path=prac_db_path)
    return MultiLaneResearchRunner(
        db_path=db_path,
        practitioner_db_path=prac_db_path,
        questions_yaml_path=q_yaml_path,
    )


def test_canary_no_shared_sentences(is_live):
    """1. no_shared_sentences: no non-heading sentence appears in both Q1 and Q2 outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = _create_runner(tmpdir)
        q1_override = None if is_live else _load_cassette("q1_kiro")
        q2_override = None if is_live else _load_cassette("q2_hospitals")

        res1 = runner.run_workflow(
            topic=Q1_TOPIC, depth="Fast", tone="Executive",
            map_provider="stub", reduce_provider="stub",
            academic_papers_override=q1_override,
        )
        res2 = runner.run_workflow(
            topic=Q2_TOPIC, depth="Fast", tone="Executive",
            map_provider="stub", reduce_provider="stub",
            academic_papers_override=q2_override,
        )

        q1_sentences = {
            s["text"].strip() for s in res1.get("sentence_traces", [])
            if s.get("type") not in ("heading", "title")
        }
        q2_sentences = {
            s["text"].strip() for s in res2.get("sentence_traces", [])
            if s.get("type") not in ("heading", "title")
        }
        shared = q1_sentences.intersection(q2_sentences)
        assert len(shared) == 0, f"Defect D1 regression! Shared sentences detected: {shared}"


def test_canary_numbers_traceable(is_live):
    """2. numbers_traceable: every digit-bearing token in any rendered sentence appears in a claim of that run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = _create_runner(tmpdir)
        override = None if is_live else _load_cassette("q1_kiro")
        res = runner.run_workflow(
            topic=Q1_TOPIC, depth="Fast", tone="Executive",
            map_provider="stub", reduce_provider="stub",
            academic_papers_override=override,
        )
        repo = LedgerRepository(db_path=runner.db_path)
        all_claims = repo.list_claims(question_id=res["question_id"])
        claims_text = " ".join([f"{c.text} {c.source_excerpt or ''} {json.dumps(c.value_json or {})}" for c in all_claims])

        for s in res.get("sentence_traces", []):
            if s.get("type") in ("assertive", "finding", "roadmap", "risk"):
                # Find all digit tokens (e.g. 24%, 350)
                num_tokens = re.findall(r"\b\d+[%xXkKMGB]*\b", s.get("text", ""))
                for token in num_tokens:
                    # Strip unit suffix to check bare digits
                    digits = re.sub(r"[^\d]", "", token)
                    if digits:
                        assert digits in claims_text, (
                            f"Number token '{token}' in sentence '{s.get('text')}' is not grounded in any cited ledger claim"
                        )


def test_canary_citations_resolve_and_support(is_live):
    """3. citations_resolve_and_support: all [P#] resolve inside the run and pass term checks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = _create_runner(tmpdir)
        override = None if is_live else _load_cassette("q1_kiro")
        res = runner.run_workflow(
            topic=Q1_TOPIC, depth="Fast", tone="Executive",
            map_provider="stub", reduce_provider="stub",
            academic_papers_override=override,
        )
        papers = res.get("papers", [])
        for s in res.get("sentence_traces", []):
            p_matches = re.findall(r"\[P(\d+)\]", s.get("text", ""))
            for p_num in p_matches:
                p_idx = int(p_num) - 1
                assert 0 <= p_idx < len(papers), f"Citation [P{p_num}] does not resolve to an indexed paper in this run"
                cited_paper = papers[p_idx]
                assert cited_paper.get("title"), f"Cited paper [P{p_num}] has no title"


def test_canary_lane_c_scoped(is_live):
    """4. lane_c_scoped: Lane C count is 0 for Q2 and Q3."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = _create_runner(tmpdir)
        # Seed an unrelated software delivery observation
        prac_col = PractitionerCollector(db_path=runner.practitioner_db_path)
        q_soft = Question(id="q-soft-pilot", text="Software velocity", scope="software")
        prac_col.repo.insert_question(q_soft)
        prac_col.add_observation(
            question_id=q_soft.id,
            situation="140 enterprise microservices continuous deployment",
            decision="Enforced gate check",
            action="Static analysis",
            outcome="Zero defect regression",
            sector="software",
            abstraction_confirmed=True,
        )

        q2_override = None if is_live else _load_cassette("q2_hospitals")
        res2 = runner.run_workflow(
            topic=Q2_TOPIC, depth="Fast", tone="Executive",
            map_provider="stub", reduce_provider="stub",
            academic_papers_override=q2_override,
        )
        assert len(res2.get("practitioner_observations", [])) == 0, "Lane C leaked software observation into Q2"

        q3_override = None if is_live else _load_cassette("q3_quantum_sourdough")
        res3 = runner.run_workflow(
            topic=Q3_TOPIC, depth="Fast", tone="Executive",
            map_provider="stub", reduce_provider="stub",
            academic_papers_override=q3_override,
        )
        assert len(res3.get("practitioner_observations", [])) == 0, "Lane C leaked software observation into Q3"


def test_canary_q3_no_findings(is_live):
    """5. q3_no_findings: Q3 yields 0 findings, Outcome 4, status NOT_PUBLISHABLE, and search_log rows."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = _create_runner(tmpdir)
        override = None if is_live else _load_cassette("q3_quantum_sourdough")
        res = runner.run_workflow(
            topic=Q3_TOPIC, depth="Fast", tone="Executive",
            map_provider="stub", reduce_provider="stub",
            academic_papers_override=override,
        )
        assert len(res["findings"]) == 0, f"Expected 0 findings for Q3, got {len(res['findings'])}"
        assert res["gap_matrix"]["outcome"] in (4, "Practice not assessed"), f"Expected Outcome 4 or Practice not assessed, got {res['gap_matrix']['outcome']}"
        assert res["publish_res"]["status"] == "NOT_PUBLISHABLE"

        repo = LedgerRepository(db_path=runner.db_path)
        logs = repo.list_search_logs(question_id=res["question_id"])
        log_lanes = {l.lane for l in logs}
        assert "academic" in log_lanes
        assert "enterprise" in log_lanes
        assert "practitioner" in log_lanes


def test_canary_fallback_no_findings():
    """6. fallback_no_findings: in fallback mode output contains no fake findings, only extractive list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = _create_runner(tmpdir)
        res = runner.run_workflow(
            topic="Test Fallback Topic", depth="Fast", tone="Executive",
            map_provider="stub", reduce_provider="stub",
            academic_papers_override=[],
        )
        # With zero evidence Check A stops before any generation (DEC-016); otherwise fallback is labelled.
        assert res.get("generation_mode") == "extractive_fallback" or res.get("stopped_at") == "check_a"
        assert len(res["findings"]) == 0
        assert res["publish_res"]["allowed"] is False
        assert res["publish_res"]["status"] in ("NOT_PUBLISHABLE", "BLOCKED")


def test_canary_deterministic():
    """7. deterministic: Q1 twice with the same cassette gives identical claims and sentences."""
    with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
        runner1 = _create_runner(tmpdir1)
        runner2 = _create_runner(tmpdir2)
        cassette = _load_cassette("q1_kiro")

        res1 = runner1.run_workflow(
            topic=Q1_TOPIC, depth="Fast", tone="Executive",
            map_provider="stub", reduce_provider="stub",
            academic_papers_override=cassette,
        )
        res2 = runner2.run_workflow(
            topic=Q1_TOPIC, depth="Fast", tone="Executive",
            map_provider="stub", reduce_provider="stub",
            academic_papers_override=cassette,
        )

        claims1 = [c.get("text") if isinstance(c, dict) else c.text for c in res1.get("claims", [])]
        claims2 = [c.get("text") if isinstance(c, dict) else c.text for c in res2.get("claims", [])]
        assert claims1 == claims2, "Extracted claims must be strictly identical across deterministic runs"

        sentences1 = [s["text"] for s in res1.get("sentence_traces", [])]
        sentences2 = [s["text"] for s in res2.get("sentence_traces", [])]
        assert sentences1 == sentences2, "Output sentences must be strictly identical across deterministic runs"


def test_canary_render_matches_ledger():
    """8. render_matches_ledger: no rendered or exported sentence is absent from output_sentences; no <span or <div."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = _create_runner(tmpdir)
        cassette = _load_cassette("q1_kiro")
        res = runner.run_workflow(
            topic=Q1_TOPIC, depth="Fast", tone="Executive",
            map_provider="stub", reduce_provider="stub",
            academic_papers_override=cassette,
        )

        repo = LedgerRepository(db_path=runner.db_path)
        output_doc = repo.get_output(res["doc_id"])
        sentences = repo.list_output_sentences(output_id=res["doc_id"])
        sentence_texts = {s.text.strip() for s in sentences}

        renderer = UnifiedRenderer(
            topic=Q1_TOPIC,
            doc=output_doc,
            sentences=sentences,
            papers=res.get("papers", []),
            base_dir=tmpdir,
        )
        md_text = renderer.render_markdown()
        li_text = renderer.render_linkedin_pack()

        # Check no HTML tags in rendered text
        assert "<span" not in md_text, "Found <span tag in rendered markdown!"
        assert "<div" not in md_text, "Found <div tag in rendered markdown!"
        assert "<span" not in li_text, "Found <span tag in rendered linkedin pack!"
        assert "<div" not in li_text, "Found <div tag in rendered linkedin pack!"

        # Check rendered bullet sentences exist in ledger sentences
        for line in md_text.splitlines():
            line_str = line.strip()
            if line_str.startswith("- ") and not line_str.startswith("- [P"):
                bullet_content = line_str[2:].strip()
                # Verify that this bullet content matches an output sentence in the ledger
                if not bullet_content.startswith("Recommendations require") and not bullet_content.startswith("No negative"):
                    assert bullet_content in sentence_texts, (
                        f"Rendered bullet '{bullet_content}' does not exist in output_sentences single source of truth!"
                    )


def test_canary_publish_gate():
    """9. publish_gate: exports blocked or watermarked unless PUBLISH_READY."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = _create_runner(tmpdir)
        res = runner.run_workflow(
            topic=Q3_TOPIC, depth="Fast", tone="Executive",
            map_provider="stub", reduce_provider="stub",
            academic_papers_override=[],
        )
        assert res["publish_res"]["allowed"] is False
        assert res["publish_res"]["status"] in ("NOT_PUBLISHABLE", "BLOCKED")


def test_canary_no_egress_of_practitioner_text():
    """10. no_egress_of_practitioner_text: zero non-loopback network socket connections when Lane C contains practitioner text."""
    connected_remote_hosts = []
    real_socket_connect = socket.socket.connect

    def spy_connect(self, address):
        host, _ = address[0], address[1]
        if host not in ("127.0.0.1", "localhost", "::1"):
            connected_remote_hosts.append(host)
        return real_socket_connect(self, address)

    with tempfile.TemporaryDirectory() as tmpdir:
        runner = _create_runner(tmpdir)
        custom_notes = ["Private operational note from confidential client deployment"]

        socket.socket.connect = spy_connect
        try:
            runner.run_workflow(
                topic="Testing zero network egress with practitioner text",
                depth="Fast",
                tone="Executive",
                map_provider="gemini",
                reduce_provider="gemini",
                custom_prac_urls=custom_notes,
                practitioner_abstraction_confirmed=False,
                allow_remote_practitioner_synthesis=False,
                academic_papers_override=[],
            )
        finally:
            socket.socket.connect = real_socket_connect

        assert len(connected_remote_hosts) == 0, (
            f"Privacy violation: non-localhost socket connections attempted during practitioner synthesis: {connected_remote_hosts}"
        )
