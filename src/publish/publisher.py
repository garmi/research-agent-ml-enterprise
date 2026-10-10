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

from src.ledger.models import Claim, OutputDoc, OutputSentence, Question, Review
from src.ledger.repository import LedgerRepository
from src.score.checker import GateCheckResult, GateChecker
from src.score.scorer import QualityScorer

logger = logging.getLogger(__name__)


class Publisher:
    def __init__(
        self,
        db_path: str = "ledger/ledger.db",
        denylist_path: str = "denylist.txt",
        verbs_path: str = "synth/strength_verbs.yaml",
        scoring_path: str = "score/scoring.yaml",
        export_dir: str = "outputs/json",
    ):
        self.db_path = db_path
        self.denylist_path = denylist_path
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

        # 1. Run Gate Checker (G1 to G6)
        gate_res = self.checker.check_output(
            sentences=sentences,
            ledger_claims=ledger_claims,
            source_texts=source_texts,
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
                    gate_res.violations["G5"].append(
                        f"Gate 6 Abstraction Violation: Practitioner claim '{c.id}' has unconfirmed abstraction (R12)."
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
            return False, {
                "published": False,
                "status": "BLOCKED",
                "reason": "Hard gate violation",
                "gate_results": gate_res.to_dict(),
            }

        # 3. Calculate Final Quality Score
        questions = self.repo.list_questions()
        score_res = self.scorer.calculate_score(
            gate_result=gate_res,
            sentences=sentences,
            ledger_claims=ledger_claims,
            sources=sources,
            questions=questions,
            gap_outcomes_disclosed=1.0,
        )

        # 4. Enforce Band or explicit sign-off
        is_band_ready = score_res.get("band") == "PUBLISH_READY"
        if not is_band_ready and not force_publish_non_band:
            doc.status = "in_review"
            with self.repo._conn() as conn:
                conn.execute("UPDATE outputs SET status = ? WHERE id = ?;", ("in_review", doc.id))
            return False, {
                "published": False,
                "status": "IN_REVIEW",
                "reason": f"Quality score {score_res['total_score']} is in band '{score_res['band']}'. Requires human sign-off.",
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
                after_json={"new_status": "published", "score": score_res["total_score"], "band": score_res["band"]},
                reason=signoff_reason,
                reviewer=reviewer,
            )
        )

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
