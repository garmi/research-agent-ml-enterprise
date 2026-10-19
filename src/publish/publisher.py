"""Publish Gate and Website JSON Export Engine for Research Engine v2 (Phase 5).

Enforces:
1. Hard Gates (G1 to G6): Zero violations allowed. Output is strictly BLOCKED if any gate fails.
2. Confidentiality: Complete denylist scan against gitignored denylist.txt.
3. Abstraction Check: Every cited practitioner claim must have confirmed abstraction.
4. Score Band: Must meet PUBLISH_READY band or carry explicit human sign-off.
5. Export: Produces versioned website JSON export (outputs/json/publish_export_{output_id}.json).
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import default_outputs_dir
from src.ledger.db import default_ledger_path
from src.ledger.models import Claim, OutputDoc, OutputSentence, Question, Review
from src.ledger.repository import LedgerRepository
from src.score.checker import GateCheckResult, GateChecker
from src.score.scorer import QualityScorer

logger = logging.getLogger(__name__)


class Publisher:
    def __init__(
        self,
        db_path: Optional[str] = None,
        denylist_path: Optional[str] = None,
        verbs_path: str = "synth/strength_verbs.yaml",
        scoring_path: str = "score/scoring.yaml",
        export_dir: Optional[str] = None,
    ):
        self.db_path = db_path or default_ledger_path()
        self.denylist_path = denylist_path
        if export_dir is None or export_dir == "outputs/json":
            export_dir = str(Path(default_outputs_dir()) / "json")
        self.export_dir = export_dir
        self.repo = LedgerRepository(db_path=self.db_path)
        self.checker = GateChecker(verbs_path=verbs_path, denylist_path=denylist_path)
        self.scorer = QualityScorer(scoring_cfg_path=scoring_path)
        Path(self.export_dir).mkdir(parents=True, exist_ok=True)

    def publish_output(
        self,
        output_id: str,
        reviewer: str = "human_operator",
        signoff_reason: str = "Final human review complete and approved",
        force_publish_non_band: bool = False,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Evaluate Gate 6 Publish Gate and produce website JSON export."""
        from src.engine.stub_mode import is_stub_mode
        if is_stub_mode():
            return False, {
                "published": False,
                "status": "NOT_PUBLISHABLE",
                "reason": "TEST MODE: synthetic data. Results are not real and cannot be published.",
            }

        if not str(reviewer or "").strip():
            return False, {
                "published": False,
                "status": "NOT_PUBLISHED",
                "reason": "A named reviewer is required to publish.",
            }

        doc = self.repo.get_output(output_id)
        if not doc:
            raise ValueError(f"Output document '{output_id}' not found in ledger")

        sentences = self.repo.list_output_sentences(output_id=output_id)
        if not sentences:
            raise ValueError(f"No sentences found for output '{output_id}'")

        # Gather all cited claims
        all_cited_cids = set()
        for s in sentences:
            if s.claim_ids_json:
                all_cited_cids.update(s.claim_ids_json)

        ledger_claims: Dict[str, Claim] = {}
        source_texts: Dict[str, str] = {}
        sources = {}

        for cid in all_cited_cids:
            c = self.repo.get_claim(cid)
            if c:
                ledger_claims[cid] = c
                src = self.repo.get_source(c.source_id)
                if src:
                    sources[c.source_id] = src
                    source_texts[src.id] = f"{src.title} {src.url or ''}"

        # The run's own question, so G3 can check topic fit (without it G3 has no data and fails).
        question = None
        run = self.repo.get_run(doc.run_id) if doc.run_id else None
        candidate_qids = list((run.question_ids or []) if run else [])
        # An output drafted outside a run: use the question its cited claims belong to.
        candidate_qids += [c.question_id for c in ledger_claims.values() if c.question_id]
        for qid in candidate_qids:
            question = self.repo.get_question(qid)
            if question:
                break

        # 1. Re-run Gate Checker (G1 to G6) on the stored draft, so later changes are caught
        gate_res = self.checker.check_output(
            sentences=sentences,
            ledger_claims=ledger_claims,
            source_texts=source_texts,
            sources=sources,
            question=question,
        )

        # 2. Check for Practitioner Abstraction (R12 enforcement)
        for cid, c in ledger_claims.items():
            is_practitioner = (
                getattr(c, "study_type", "") == "practitioner_observation"
                or (c.context_json and c.context_json.get("lane") == "practitioner")
            )
            if is_practitioner:
                abstraction_confirmed = bool(
                    c.context_json and c.context_json.get("abstraction_confirmed") is True
                )
                if not abstraction_confirmed:
                    gate_res.g5_pass = False
                    gate_res.g6_pass = False
                    gate_res.violations["G5"].append(
                        f"Gate 6 Abstraction Violation: Practitioner claim '{c.id}' has unconfirmed abstraction (R12)."
                    )
                    gate_res.violations["G6"].append(
                        "Gate 6: Practitioner abstraction not confirmed by operator."
                    )

        # 3. Check for Synthetic Fixtures (R28 / A3-3 enforcement)
        for cid, c in ledger_claims.items():
            src = sources.get(c.source_id)
            is_synthetic = (
                str(c.source_id).startswith("synthetic_")
                or (src and str(src.id).startswith("synthetic_"))
                or (c.context_json and c.context_json.get("fixture_type") == "SYNTHETIC FIXTURE")
                or (c.context_json and c.context_json.get("is_synthetic") is True)
            )
            if is_synthetic and os.getenv("ALLOW_SYNTHETIC_FIXTURES") != "1":
                gate_res.g6_pass = False
                gate_res.violations["G6"].append(
                    f"Gate 6 Integrity Violation: Claim '{c.id}' derives from synthetic source '{c.source_id}'. Synthetic fixtures are strictly prohibited from publication exports."
                )

        # If any gate failed, status is strictly BLOCKED
        if not gate_res.passed:
            doc.status = "blocked"
            doc.gates_json = gate_res.to_dict()
            with self.repo._conn() as conn:
                conn.execute(
                    "UPDATE outputs SET status = ?, gates_json = ? WHERE id = ?;",
                    ("blocked", json.dumps(doc.gates_json), doc.id),
                )
            not_passed = [f"{g}: {gate_res.reason_plain(g)}" for g, st in gate_res.states().items() if st != "PASS"]
            block_reason = (
                "Gate 6: Practitioner abstraction not confirmed by operator."
                if any("Gate 6" in v for v in gate_res.violations.get("G6", []))
                else "Not all gates passed. " + " ".join(not_passed)
            )
            return False, {
                "published": False,
                "status": "BLOCKED",
                "reason": block_reason,
                "gate_results": gate_res.to_dict(),
            }

        # 3. The run's audited score decides the band (it was computed with the run's papers and
        # gap outcomes); re-scoring here without them would understate it.
        score_res = dict(doc.score_json or {})
        if not score_res.get("band"):
            score_res = self.scorer.calculate_score(
                gate_result=gate_res,
                sentences=sentences,
                ledger_claims=ledger_claims,
                sources=sources,
                questions=[question] if question else [],
            )
        band = str(score_res.get("band") or "NOT_PUBLISHABLE").upper()

        # 4. Enforce band: PUBLISH_READY publishes; REVISE only with an explicit, reasoned override;
        # anything else (NOT_PUBLISHABLE, BLOCKED) is never published.
        if band not in ("PUBLISH_READY", "REVISE"):
            return False, {
                "published": False,
                "status": band,
                "reason": f"Band '{band}' cannot be published, even with an override.",
                "score_results": score_res,
                "gate_results": gate_res.to_dict(),
            }
        if band == "REVISE" and force_publish_non_band and not str(signoff_reason or "").strip():
            return False, {
                "published": False,
                "status": band,
                "reason": "Publishing a REVISE draft needs a sign-off reason, which is logged.",
                "score_results": score_res,
                "gate_results": gate_res.to_dict(),
            }
        is_band_ready = band == "PUBLISH_READY"
        if not is_band_ready and not force_publish_non_band:
            band_status = band
            doc.status = "draft"
            with self.repo._conn() as conn:
                conn.execute("UPDATE outputs SET status = ? WHERE id = ?;", (doc.status, doc.id))
            return False, {
                "published": False,
                "status": band_status,
                "reason": f"Quality score {score_res.get('total_score')} is in band '{band}'. Publishing it needs an explicit, reasoned sign-off.",
                "score_results": score_res,
                "gate_results": gate_res.to_dict(),
            }

        # 5. Transition to PUBLISHED and record audit in reviews
        doc.status = "published"
        doc.score_json = score_res
        doc.gates_json = gate_res.to_dict()
        with self.repo._conn() as conn:
            conn.execute(
                "UPDATE outputs SET status = ?, score_json = ?, gates_json = ? WHERE id = ?;",
                ("published", json.dumps(score_res), json.dumps(gate_res.to_dict()), doc.id),
            )

        self.repo.insert_review(
            Review(
                id=f"rev_{uuid.uuid4().hex[:10]}",
                gate="Gate 6",
                object_type="output",
                object_id=doc.id,
                action="publish",
                before_json={"previous_status": "draft"},
                after_json={"new_status": "published", "score": score_res.get("total_score"), "band": band},
                reason=signoff_reason,
                reviewer=reviewer,
            )
        )

        if doc.run_id:
            self.repo.set_run_status(doc.run_id, "PUBLISHED", f"Published by {reviewer} (band {band}): {signoff_reason}")

        # 6. Generate Versioned Website JSON Export
        export_payload = {
            "schema_version": "2.0",
            "output_id": doc.id,
            "kind": doc.kind,
            "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "reviewer": reviewer,
            "scorecard": score_res,
            "gates": gate_res.to_dict(),
            "sentences": [
                {
                    "ordinal": s.ordinal,
                    "type": s.type,
                    "text": s.text,
                    "strength_verb": s.strength_verb,
                    "claim_ids": s.claim_ids_json or [],
                }
                for s in sentences
            ],
            "evidence_base": [
                {
                    "claim_id": c.id,
                    "text": c.text,
                    "source_excerpt": c.source_excerpt,
                    "grade": c.grade,
                    "entity": c.entity,
                    "source_id": c.source_id,
                    "source_title": sources.get(c.source_id).title if sources.get(c.source_id) else None,
                    "source_venue": sources.get(c.source_id).venue if sources.get(c.source_id) else None,
                    "venue_tier": sources.get(c.source_id).venue_tier if sources.get(c.source_id) else None,
                }
                for c in ledger_claims.values()
            ],
        }

        export_path = Path(self.export_dir) / f"publish_export_{doc.id}.json"
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(export_payload, f, indent=2)

        # Also write canonical field_note_export.json for website
        canonical_path = Path(self.export_dir) / "field_note_export.json"
        with open(canonical_path, "w", encoding="utf-8") as f:
            json.dump(export_payload, f, indent=2)

        logger.info(f"Published output {doc.id} to {export_path}")
        return True, {
            "published": True,
            "status": "PUBLISHED",
            "export_path": str(export_path),
            "canonical_path": str(canonical_path),
            "score_results": score_res,
            "gate_results": gate_res.to_dict(),
        }
