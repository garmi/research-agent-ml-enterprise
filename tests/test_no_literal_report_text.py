"""Test that no literal report content strings exist in synthesis, render, export, and offline modules (A1)."""

from pathlib import Path
import re
import pytest

D1_CANARY_STRINGS = [
    "Empirical velocity increases by 32%",
    "Bounded autonomy contracts prevent out-of-band regression risks",
    "Platform engineering teams report higher DevEx satisfaction scores",
    "Unverified extrapolation in production pipelines leads to silent architectural drift",
    "Lack of centralized audit logging hampers compliance in regulated sectors",
    "Premature agentic deployment without deterministic test suites amplifies MTTR",
    "Robust empirical support for architecture adoption under bounded contracts",
    "Achieved zero unauthorized architectural drift across 140 enterprise microservices",
    "+32% velocity on boilerplate",
    "Why the 32% Dev Velocity metric is misleading",
    "The 5 Deterministic Gates every VP of Engineering",
    "From Copilot to Kiro: The shift from reactive completion",
    "Phase 1 (Days 1–30)",
    "140 enterprise microservices",
    "100% Zero-Hallucination Verified Citations",
]

TARGET_MODULES = [
    "src/llm/stub_client.py",
    "src/analysis/multilane_runner.py",
    "src/synth/generator.py",
    "src/output/html_storyline_builder.py",
    "src/output/linkedin_pack_builder.py",
    "src/output/content_pack.py",
    "src/output/report_builder.py",
    "src/analysis/synthesizer.py",
]


def test_no_literal_report_text():
    """Verify that no D1 canned strings or fabricated content constants exist in target modules."""
    violations = []
    repo_root = Path(__file__).resolve().parent.parent

    for rel_path in TARGET_MODULES:
        file_path = repo_root / rel_path
        if not file_path.exists():
            continue
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        for idx, line in enumerate(lines, start=1):
            for canary in D1_CANARY_STRINGS:
                if canary.lower() in line.lower():
                    violations.append(f"{rel_path}:{idx}: contains canned string '{canary}' -> {line.strip()[:100]}")

    assert not violations, f"Found {len(violations)} canned report content strings in target modules:\n" + "\n".join(violations)
