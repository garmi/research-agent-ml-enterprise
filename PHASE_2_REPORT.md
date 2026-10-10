# Phase 2 Report: Question Register, Venue Tiers, and Claim Review Queue

**Date:** 2026-10-10  
**Branch:** `v2-phase-2`  
**Status:** Completed & Validated — **STOPPING FOR HUMAN REVIEW**  

---

## 1. Executive Summary

Phase 2 implements the core human-in-the-loop review architecture on top of the local SQLite evidence ledger:
1. **Question Register (Gate 1, View 3):**
   - Bi-directional synchronization between `questions/register.yaml` and SQLite `questions` table via [`src/ledger/service.py`](file:///Users/gauravm/Developer/projects/research-agent-ml-enterprise/src/ledger/service.py).
   - Lifecycle management (create, update, retire) with scope and time-window filtering.
   - All mutations write append-only audit entries to `reviews` (`gate="G1"`).
2. **Venue and Source Tiering (Gate 2, View 2):**
   - Authoritative venue tier management persisted to `grade/venue_tiers.yaml`.
   - Human tier assignments trigger automatic re-grading across all attached claims in SQLite.
   - All tier changes write audit entries to `reviews` (`gate="G2"`).
3. **Claim Review Queue (Gate 3, View 1):**
   - Dynamic prioritization by **uncertainty score**: low extraction confidence (<0.80), corrupted term warnings, unverified venues, and auto-extracted claims surfaced first.
   - Full side-by-side view: paraphrased atomic assertion on the left, verbatim source excerpt ($\le 25$ words) in context on the right.
   - Supported actions: approve, reject (mandatory reason), edit assertion text, override grade (mandatory reason), override entity match (mandatory reason).
   - **Bulk approval validation:** Strictly enforces that claims can only be bulk-approved if they share identical `source_id + grade + study_type`.
   - 100% of actions generate immutable rows in `reviews` (`gate="G3"`).
4. **Local Streamlit Frontend Integration ([`web_app.py`](file:///Users/gauravm/Developer/projects/research-agent-ml-enterprise/web_app.py) & [`src/ledger/ui_views.py`](file:///Users/gauravm/Developer/projects/research-agent-ml-enterprise/src/ledger/ui_views.py)):**
   - Seamless sidebar navigation switching between the Pipeline Runner, Gate 3 Claim Review Queue, Gate 2 Venue Tiering, and Gate 1 Question Register.
   - 100% local-first on `127.0.0.1`, zero external CDN calls, zero telemetry.
5. **Adversarial & Regression Test Coverage:**
   - Regression cases R4 (unverified venue cap) and R13 (corrupted term of art detection) validated.
   - Service operations suite ([`evals/test_phase2_service.py`](file:///Users/gauravm/Developer/projects/research-agent-ml-enterprise/evals/test_phase2_service.py)) verifying queue sorting, actions, bulk approval rules, and audit logging.

---

## 2. Test Execution and Results

All test suites were executed in the project virtual environment (`.venv`):

```bash
PYTHONPATH=. .venv/bin/pytest tests evals
```

### Summary: 18 passed in 0.54s (100% Pass Rate)

| Test Suite / ID | Test File | Target Functionality | Result |
|---|---|---|---|
| **Gate 1 Register** | `evals/test_phase2_service.py` | Sync YAML, create question, update status, verify G1 audit rows | **PASS** |
| **Gate 2 Tiering** | `evals/test_phase2_service.py` | Tier unverified venue to verified, update YAML, re-grade claims, verify G2 audit rows | **PASS** |
| **Gate 3 Queue** | `evals/test_phase2_service.py` | Uncertainty sorting, approve, edit, reject with reason, grade change, verify G3 audit rows | **PASS** |
| **Gate 3 Bulk** | `evals/test_phase2_service.py` | Bulk approve homogeneous claims succeeds; heterogeneous batch raises ValueError | **PASS** |
| **R4 Unverified Cap** | `evals/test_regression.py` | Empirical study in unverified venue capped at `weak` | **PASS** |
| **R13 Term Integrity** | `evals/test_regression.py` | Corrupted term ("vibrate coding") triggers term integrity warning and 50% confidence penalty | **PASS** |
| **R1–R3, R5–R7** | `evals/test_regression.py` | All hard gate failure modes (G1, G2, G3, G4, G5, G6) | **PASS** (6/6) |
| **R10 Durability** | `evals/test_r10_migration.py` | Forward migration, pre-migration backup, WAL mode, zero data loss | **PASS** |
| **Baseline Tests** | `tests/test_pipeline.py` | Pipeline components, relevance ranking, synthesis interfaces | **PASS** (4/4) |

---

## 3. Human Audit Trail Verification (`reviews` Table)

Every review action executed through `LedgerService` generates an immutable row:

```sql
SELECT gate, object_type, action, reviewer, reason, ts FROM reviews ORDER BY ts DESC LIMIT 5;
```

Example verified audit records:
- `G1 | question | create_question | human_operator | Strategic thought-leadership priority`
- `G2 | venue    | tier_venue      | senior_editor  | Peer-reviewed by recognized committee`
- `G3 | claim    | approve_claim   | qa_lead        | Verified by human`
- `G3 | claim    | change_grade    | qa_lead        | Verified method in text`
- `G3 | claim    | reject_claim    | qa_lead        | Hallucinated extrapolation`

---

## 4. Architectural Decisions & Deviations

The following decisions were logged in `DECISIONS.md`:
- **DEC-010:** Local Human Gates Architecture and Audit Protocol (Views 1, 2, 3 integrated via in-process service layer `src/ledger/service.py`, persisting all decisions to `reviews` table and enforcing homogeneous bulk approval constraints).

---

## 5. Acceptance Criteria Checklist (Section 12)

- [x] Question Register (Gate 1, View 3) complete and synchronized with YAML.
- [x] Grading rules and venue tiers (Gate 2, View 2) complete with automatic re-grading.
- [x] Claim Review Queue (Gate 3, View 1) complete with uncertainty sorting and side-by-side view.
- [x] R4 and R13 pass 100%.
- [x] Human can review full queue in local frontend; every action is written to `reviews`.

**HARD STOP:** Awaiting your review and approval before proceeding to Phase 3 (Enterprise Lane with 5 Sources, `search_log`, and source terms verification).
