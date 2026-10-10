# Research Engine v2 — Phase 0 Report

**Date:** 2026-10-10  
**Phase:** 0 — Audit  
**Branch:** `v2-phase-0`  
**Status:** Completed & Ready for Human Review (Hard STOP)

---

## 1. What Changed

- **Code Changes:** Zero behaviour changes were made. No production code was modified.
- **Artifacts Created:**
  1. [`AUDIT.md`](file:///Users/gauravm/Developer/projects/research-agent-ml-enterprise/AUDIT.md) — Comprehensive technical audit covering existing architecture, fetchers, APIs (including OpenAlex), the Streamlit frontend, current outputs, test coverage gaps, and risks.
  2. [`DECISIONS.md`](file:///Users/gauravm/Developer/projects/research-agent-ml-enterprise/DECISIONS.md) — Design trade-offs, conventions, and architectural choices log (DEC-001 through DEC-006).
  3. [`PHASE_0_REPORT.md`](file:///Users/gauravm/Developer/projects/research-agent-ml-enterprise/PHASE_0_REPORT.md) — Phase 0 closeout report.
- **Git Branch:** Switched to dedicated branch `v2-phase-0`.

---

## 2. Tests Run & Baseline Results

The existing test suite was executed to confirm a pristine baseline:

```bash
PYTHONPATH=. .venv/bin/pytest tests
```

**Results:**
- `tests/test_pipeline.py::test_dedupe` — PASSED
- `tests/test_pipeline.py::test_pipeline` — PASSED
- `tests/test_pipeline.py::test_build_topic_queries` — PASSED
- `tests/test_pipeline.py::test_openalex_abstract_reconstruction` — PASSED
- **Summary:** 4 passed, 1 warning (OpenSSL warning from urllib3) in 0.22 seconds.
- **Pass Rate:** 100%

---

## 3. Scores Achieved

- **Per-Output Quality Score:** N/A (Phase 0 is the audit baseline; no outputs generated).
- **Hard Gates:** All legacy outputs in `outputs/` are flagged `status: legacy-ungraded` and blocked from publication.

---

## 4. Deviations from Prompt Logged in `DECISIONS.md`

In accordance with Section 1 (*"The repo is the source of truth, not this document"*):

1. **Namespace Organization (DEC-001):**
   - New engine modules will reside cleanly under `src/` (`src/ledger/`, `src/extract/`, `src/grade/`, `src/gaps/`, `src/synth/`, `src/score/`) to prevent root directory pollution and preserve backward compatibility with existing CLI commands and package imports. `questions/` and `evals/` remain at the project root.
2. **Frontend Architecture (DEC-002):**
   - The existing frontend is a native **Streamlit** application (`web_app.py`). Rather than introducing an unnecessary secondary REST framework (e.g. FastAPI/Uvicorn), Streamlit will interact directly with an atomic, local SQLite service module bound to `127.0.0.1`. Every human action will write append-only records to the `reviews` table.
3. **Primary Academic Fetcher (DEC-003):**
   - `OpenAlexClient` is retained as a primary academic literature client alongside Crossref, arXiv, and Semantic Scholar, because it provides 250M+ open-access works with high reliability and zero rate-limiting throttling.

---

## 5. Open Questions for Human Review

Before proceeding to **Phase 1** (Ledger with durability, claim extraction, sentence checker, regression cases R1–R7, R10):

1. **Frontend Review Approach:**
   - Does extending the existing Streamlit dashboard (`web_app.py`) with the 8 human review views (Claim Review Queue, Venue Tiering, Question Register, Gap Matrix, Draft Review, Publish Gate, Practitioner Entry, Runs/Scores) backed by the local SQLite service meet your workflow expectations?
2. **Benchmark Fixture Dataset:**
   - Are you aligned with using the 8 papers from the recent Kiro run (stored in `outputs/csv/paper_index.csv`) as the initial human-labelled calibration set for testing claim extraction precision and grading agreement in Phase 1?

---

## 6. Phase Acceptance Checklist

- [x] `AUDIT.md` complete and verified against Section 3 of prompt.
- [x] `DECISIONS.md` created and updated.
- [x] Zero behaviour or runtime code changes introduced.
- [x] Baseline test suite passes 100%.
- [x] Execution halted for human sign-off per Section 12.

**STOPPING HERE FOR HUMAN REVIEW BEFORE STARTING PHASE 1.**
