"""Test A9: Privacy, Egress Controls, Gate 6 Human Confirmation, and Hosted Safety.

Verifies:
1. Default active engine is local (Ollama if running, offline deterministic engine if not), remote is opt-in.
2. Hosted demo mode (HOSTED_DEMO=1) disables session API key override.
3. Network spy test: when Lane C contains custom practitioner text, zero bytes/connections leave the process to remote hosts unless explicitly permitted.
4. Gate 6 strictly requires human confirmation step for custom practitioner notes.
"""

from __future__ import annotations

import os
import socket
import tempfile
from pathlib import Path
from typing import Any, Dict, List
import pytest
import yaml

from src.analysis.multilane_runner import MultiLaneResearchRunner, get_default_local_provider
from src.ledger.migrations import apply_migrations
from src.ledger.models import Question
from src.score.checker import GateChecker


def test_default_active_engine_is_local_in_config_and_runner():
    """Verify default engine is local-first, remote models are strictly opt-in."""
    # 1. Check config.yaml
    cfg_path = Path("config.yaml")
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        llm_cfg = cfg.get("llm", {})
        assert llm_cfg.get("map_provider") in ("ollama", "stub"), (
            f"Default map_provider in config.yaml must be local ('ollama' or 'stub'), got '{llm_cfg.get('map_provider')}'"
        )
        assert llm_cfg.get("allow_remote_synthesis") is False, (
            "config.yaml must have allow_remote_synthesis: false by default"
        )

    # 2. Check get_default_local_provider helper
    local_provider = get_default_local_provider()
    assert local_provider in ("ollama", "stub"), f"Default provider must be local, got {local_provider}"


def test_gate_6_blocks_unconfirmed_custom_practitioner_notes():
    """Verify run with custom practitioner notes cannot be marked Gate 6 confirmed without human sign-off."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "ledger.db")
        prac_db_path = str(Path(tmpdir) / "practitioner.db")
        q_yaml_path = str(Path(tmpdir) / "register.yaml")
        apply_migrations(db_path=db_path)
        apply_migrations(db_path=prac_db_path)

        runner = MultiLaneResearchRunner(
            db_path=db_path,
            practitioner_db_path=prac_db_path,
            questions_yaml_path=q_yaml_path,
        )

        custom_notes = [
            "Incident note: Production latency regression on checkout service due to un-abstracted memory leak"
        ]

        # Case 1: Human confirmation is FALSE (operator did not confirm abstraction)
        res_unconfirmed = runner.run_workflow(
            topic="How do engineering teams prevent latency regressions?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            custom_prac_urls=custom_notes,
            practitioner_abstraction_confirmed=False,
            academic_papers_override=[],
        )

        # Must be strictly BLOCKED with exact reason
        assert res_unconfirmed["publish_res"]["status"] == "BLOCKED"
        assert "Gate 6: Practitioner abstraction not confirmed by operator." in (
            res_unconfirmed["publish_res"].get("reason", "")
            + " "
            + str(res_unconfirmed["publish_res"].get("gate_results", {}).get("violations", {}))
        )

        # Case 2: Human confirmation is TRUE (operator confirmed abstraction)
        res_confirmed = runner.run_workflow(
            topic="How do engineering teams prevent latency regressions?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            custom_prac_urls=custom_notes,
            practitioner_abstraction_confirmed=True,
            academic_papers_override=[],
        )
        g6_res = res_confirmed["publish_res"].get("gate_results", {}).get("G6", {})
        assert "Gate 6: Practitioner abstraction not confirmed by operator." not in str(
            res_confirmed["publish_res"].get("gate_results", {}).get("violations", {})
        )


def test_network_spy_asserts_zero_remote_egress_when_lane_c_contains_custom_practitioner_text(monkeypatch):
    """Network Spy Test: Assert zero bytes/connections leave the process to remote hosts during synthesis of custom practitioner notes."""
    connected_hosts: List[str] = []

    real_connect = socket.socket.connect

    def spy_connect(sock_self, address):
        host = address[0] if isinstance(address, tuple) and len(address) > 0 else str(address)
        connected_hosts.append(str(host))
        # Allow localhost / loopback addresses only
        if str(host) in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
            return real_connect(sock_self, address)
        raise ConnectionRefusedError(
            f"SPY DETECTED OUT-OF-BOUNDARY NETWORK EGRESS TO REMOTE HOST: {host} (Practitioner privacy violation!)"
        )

    monkeypatch.setattr(socket.socket, "connect", spy_connect)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "ledger.db")
        prac_db_path = str(Path(tmpdir) / "practitioner.db")
        q_yaml_path = str(Path(tmpdir) / "register.yaml")
        apply_migrations(db_path=db_path)
        apply_migrations(db_path=prac_db_path)

        runner = MultiLaneResearchRunner(
            db_path=db_path,
            practitioner_db_path=prac_db_path,
            questions_yaml_path=q_yaml_path,
        )

        custom_notes = [
            "Confidential incident note: Customer data isolation breach in microservice auth pipeline."
        ]

        # Case A: User has NOT checked 'Allow remote synthesis of practitioner data' (default False)
        # Even if map_provider is requested as 'gemini', it must not connect to remote googleapis.com!
        res = runner.run_workflow(
            topic="How do microservices maintain strict data isolation?",
            depth="Fast",
            tone="Executive",
            map_provider="gemini",
            reduce_provider="gemini",
            custom_prac_urls=custom_notes,
            allow_remote_practitioner_synthesis=False,
            practitioner_abstraction_confirmed=True,
            academic_papers_override=[],
        )

        # Assert no remote hosts were contacted
        remote_hosts = [h for h in connected_hosts if h not in ("127.0.0.1", "localhost", "::1")]
        assert len(remote_hosts) == 0, f"Privacy failure! Remote hosts were contacted: {remote_hosts}"


def test_hosted_demo_mode_disables_api_key_override(monkeypatch):
    """Verify that in hosted demo mode (HOSTED_DEMO=1), API key override is disabled."""
    monkeypatch.setenv("HOSTED_DEMO", "1")
    with open("web_app.py", "r", encoding="utf-8") as f:
        src = f.read()
    assert "HOSTED_DEMO" in src
    assert "API key override disabled on shared instance." in src

