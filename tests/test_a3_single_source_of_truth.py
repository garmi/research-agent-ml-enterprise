"""Test A3: Single Source of Truth from output_sentences table.

Enforces that every piece of user-facing synthesis text in UI Findings, Signals,
Risks, Roadmap, and export files (.md, .json, .html, linkedin .md) is rendered
strictly from the output_sentences table in the ledger.
"""

import json
import os
from pathlib import Path
import tempfile
import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner


def test_every_rendered_text_exists_in_output_sentences():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_db = str(Path(tmpdir) / "test_ledger.db")
        prac_db = str(Path(tmpdir) / "test_prac.db")
        yaml_reg = str(Path(tmpdir) / "register.yaml")

        runner = MultiLaneResearchRunner(
            db_path=ledger_db,
            practitioner_db_path=prac_db,
            questions_yaml_path=yaml_reg,
        )

        dummy_papers = [
            {
                "id": "p-01",
                "title": "Empirical Verification of AI Code",
                "abstract": "We observe that contract testing reduces defects by 30% across repositories.",
                "year": 2024,
                "venue": "ICSE",
                "url": "https://doi.org/10.1145/test",
                "relevance_score": 0.95,
            }
        ]

        result = runner.run_workflow(
            topic="How do automated verification gates affect software defects?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=dummy_papers,
        )

        doc_id = result.get("doc_id")
        assert doc_id, "Expected doc_id in workflow result payload"

        # Query all sentences stored in the ledger for this document
        stored_sentences = runner.repo.list_output_sentences(doc_id)
        assert len(stored_sentences) > 0, "Expected output_sentences to be populated in ledger"

        stored_texts = {s.text.strip() for s in stored_sentences}
        stored_ids = {s.id for s in stored_sentences}

        # 1. UI Findings must all exist in output_sentences
        findings = result.get("findings", [])
        assert len(findings) > 0, "Expected findings in result"
        for f in findings:
            f_text = f.get("text", "").strip()
            assert f_text in stored_texts, (
                f"UI Finding '{f_text}' was NOT found in output_sentences table!"
            )

        # 2. UI Signals must all exist in output_sentences
        signals = result.get("signals", [])
        for s in signals:
            s_text = s.get("text", "").strip()
            assert s_text in stored_texts, (
                f"UI Signal '{s_text}' was NOT found in output_sentences table!"
            )

        # 3. UI Risks must all exist in output_sentences
        risks = result.get("risks", [])
        for r in risks:
            r_text = (r if isinstance(r, str) else r.get("text", "")).strip()
            assert r_text in stored_texts, (
                f"UI Risk '{r_text}' was NOT found in output_sentences table!"
            )

        # 4. UI Roadmap actions must all exist in output_sentences
        roadmap = result.get("roadmap", [])
        for item in roadmap:
            action_text = item.get("action", "").strip()
            if action_text:
                assert action_text in stored_texts, (
                    f"UI Roadmap action '{action_text}' was NOT found in output_sentences table!"
                )

        # 5. Gate audit sentence IDs must match output_sentences.id
        gates_audit = result.get("gates_audit", {})
        hard_gates = gates_audit.get("hard_gates", {})
        for g_name, g_info in hard_gates.items():
            violations = g_info.get("violations", [])
            for v in violations:
                sent_id = v.get("sentence_id")
                if sent_id:
                    assert sent_id in stored_ids, (
                        f"Gate audit logged sentence_id '{sent_id}' not found in output_sentences table!"
                    )

        # 6. JSON export must contain the exact output_sentences list
        out_base = Path(os.getenv("OUTPUT_DIR", "outputs"))
        json_path = out_base / "json" / "research_report.json"
        assert json_path.exists(), f"{json_path} must exist"
        json_data = json.loads(json_path.read_text())
        assert "output_sentences" in json_data, "research_report.json must include output_sentences"
        exported_sentences = json_data["output_sentences"]
        assert len(exported_sentences) == len(stored_sentences)

        # 7. Markdown report must render sentences from output_sentences
        md_path = out_base / "reports" / "research_report.md"
        assert md_path.exists(), f"{md_path} must exist"
        md_text = md_path.read_text()
        for f in findings:
            assert f["text"] in md_text, f"Finding '{f['text']}' missing from markdown report"
        for r in risks:
            assert r in md_text, f"Risk '{r}' missing from markdown report"

        # 8. LinkedIn pack must render sentences from output_sentences
        li_path = out_base / "reports" / "linkedin_professional_pack.md"
        assert li_path.exists(), f"{li_path} must exist"
        li_text = li_path.read_text()
        for f in findings:
            assert f["text"] in li_text, f"Finding '{f['text']}' missing from LinkedIn pack"

        # 9. Negative findings check
        neg_findings = result.get("negative_findings", [])
        assert len(neg_findings) > 0, "Expected negative findings in result"
        for nf in neg_findings:
            assert nf in stored_texts, f"Negative finding '{nf}' not found in output_sentences table"
