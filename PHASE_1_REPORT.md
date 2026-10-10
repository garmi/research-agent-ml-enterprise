# Phase 1 Report: Evidence Ledger, Claim Extraction, and Hard Gate Checker

**Date:** 2026-10-10  
**Branch:** `v2-phase-1`  
**Status:** Completed & Validated — **STOPPING FOR HUMAN REVIEW**  

---

## 1. Executive Summary

Phase 1 establishes the deterministic foundation of Research Engine v2:
1. **Durability-First Ledger (`ledger/`):** Implemented SQLite schema with `schema_version` tracking, forward-only migrations (`001_initial_schema.sql`), automated pre-migration timestamped backups with retention in `ledger/backups/`, SQLite WAL mode, and startup integrity checks.
2. **Atomic Claim Extraction (`src/extract/`):** Implemented Pydantic-validated extraction producing atomic claims with source excerpts capped at $\le 25$ words, paraphrased text, entity match classification (`exact`, `family`, `topic_level`, `mismatch`), study type taxonomy, and term integrity verification (protecting against "vibrate coding").
3. **Deterministic Grading (`src/grade/`):** Implemented rule-based grading driven by `grade/rules.yaml` and `grade/venue_tiers.yaml`. Enforces caps: unverified venues cap at `weak`, abstract-only depth caps at `moderate`, unresolved contradictions cap at `weak`, and vendor commercial stakes cap at `vendor_claim`.
4. **Hard Gate Checker & Scorer (`src/score/`):** Implemented non-negotiable gates G1 through G6 and quality scoring components S1 through S7 with publish readiness bands.
5. **Adversarial & Regression Suite (`evals/`):** Planted regression cases R1 to R7 and migration test R10 all pass at 100%.
6. **Kiro Benchmark Execution:** Extracted and graded 60 atomic claims across the 8 historical Kiro papers. Evaluated the sample v1 draft, proving that the engine detects and blocks all three v1 failure modes (misattribution, ungrounded numbers, and uncited sentences).

---

## 2. Test Execution and Results

All test suites were executed in the project virtual environment (`.venv`):

```bash
PYTHONPATH=. .venv/bin/pytest tests evals
```

### Summary: 13 passed in 0.31s (100% Pass Rate)

| Test ID | File | Target Behavior | Result |
|---|---|---|---|
| **R1** | `evals/test_regression.py` | Citing 2023 generic AI paper for Kiro-specific claim triggers G3 Entity Fidelity failure | **PASS** |
| **R2** | `evals/test_regression.py` | Fabricated numbers (e.g. 67%, 20x) absent from ledger trigger G2 Numeric Fidelity failure | **PASS** |
| **R3** | `evals/test_regression.py` | Vendor claim written as proven fact using strong verb ("demonstrates") triggers G4 Language Honesty failure | **PASS** |
| **R4** | `evals/test_regression.py` | Empirical study published in unverified venue (`WJARR`) is strictly capped at `weak` grade | **PASS** |
| **R5** | `evals/test_regression.py` | Text containing confidential name from `denylist.txt` triggers G5 Confidentiality failure | **PASS** |
| **R6** | `evals/test_regression.py` | Verbatim run $\ge 8$ consecutive words outside marked quotes triggers G6 Copyright failure | **PASS** |
| **R7** | `evals/test_regression.py` | Assertive sentence without claim citation triggers G1 Traceability failure | **PASS** |
| **R10** | `evals/test_r10_migration.py` | Forward migration on populated legacy DB preserves 100% of data, generates backup, enables WAL | **PASS** |
| **Compliant** | `evals/test_regression.py` | Fully cited, exact-entity, honest-verb sentence passes all gates G1 through G6 cleanly | **PASS** |
| **Baseline** | `tests/test_pipeline.py` | Pipeline components, relevance scoring, and synthesizer interfaces remain backward-compatible | **PASS** (4/4) |

---

## 3. Benchmark Evaluation on the 8 Kiro Papers

The 8 papers from the prior Kiro run (`outputs/csv/paper_index.csv` and `outputs/json/research_report.json`) were ingested into `ledger/ledger.db`, extracted into atomic claims, and graded against `q-kiro-empirical`:

### Paper & Venue Distribution (8 Papers)
- **Verified Venues (2):** ACM (Collaborative LLM Agents), IEEE/SE
- **Reputable Preprints (2):** arXiv (SDAD: Spec-Driven Agentic Development, arXiv:2608.20341; SDD: Human-Agent Teamwork, arXiv:2609.00252)
- **Unverified / Low-Refereeing (4):** WJARR (2 papers), ISJEM (1 paper), EAJIT (1 paper)

### Claim Extraction & Entity Match Distribution (60 Claims Extracted)
- **Exact Match (`exact`):** 7 claims (11.7%) — *Only Paper 8 (Amazon Kiro: Transforming Software Development) was actually about Kiro!*
- **Family Match (`family`):** 7 claims (11.7%) — Coding assistant peers (Copilot, Cursor)
- **Topic Level (`topic_level`):** 46 claims (76.7%) — General AI-assisted software engineering and dev productivity

### Claim Grade Distribution
- **`strong`:** 0 claims (0%) — Abstract-only extraction is properly capped at `moderate` by rule; full-text extraction or multi-source corroboration required for `strong`.
- **`moderate`:** 28 claims (46.7%) — From reputable preprints and verified venues.
- **`weak`:** 32 claims (53.3%) — From unverified venues (`WJARR`, `ISJEM`, etc.) and position papers.

---

## 4. Scorecard: Evaluating Sample v1 Output

Evaluating the v1 draft report sentences against the new v2 Ledger and Gate Checker demonstrates why v2 is essential:

### 4.1 Hard Gate Results: BLOCKED

| Gate | Status | Diagnostic Violations Detected |
|---|---|---|
| **G1 Traceability** | **FAIL** | Sentence 3 lacks citation: *"Spec-driven governance models are essential for enterprise compliance."* |
| **G2 Numeric Fidelity** | **FAIL** | Sentence 1 contains ungrounded numerals `25%` and `35%` relative to Kiro; Sentence 2 contains fabricated numerals `67%` and `20x`. |
| **G3 Entity Fidelity** | **FAIL** | Sentence 1 asserts specific Kiro productivity gains but cites generic Paper 4 claim tagged `topic_level`. |
| **G4 Language Honesty** | **PASS** | Verbs within acceptable range for cited draft sentences. |
| **G5 Confidentiality** | **PASS** | Zero denylist matches in benchmark draft. |
| **G6 Copyright** | **PASS** | No verbatim runs $\ge 8$ words outside quotes in tested sentences. |

### 4.2 Quality Components & Score

```
Total Score: 53.0 / 100
Status:      BLOCKED (Hard gates G1, G2, G3 failed)
Band:        BLOCKED (Must pass all hard gates to be eligible for publication)
```

| Component | Weight | Achieved | Basis / Inputs |
|---|---|---|---|
| **S1 Evidence Strength** | 30 | 8.0 | Mean grade value of cited claims normalized to question benchmark. |
| **S2 Corroboration & Diversity** | 15 | 0.0 | Findings relied on single uncorroborated sources without multi-lane backing. |
| **S3 Question Coverage** | 15 | 15.0 | In-scope question `q-kiro-empirical` is represented. |
| **S4 Gap Disclosure** | 10 | 10.0 | Ledger records the thin evidence base. |
| **S5 Freshness & Scope** | 10 | 10.0 | Ingested literature is within 36-month window (2023–2026). |
| **S6 Human Review** | 10 | 0.0 | No Gate 3 human reviews or Gate 1–6 sign-offs completed yet. |
| **S7 Reproducibility** | 10 | 10.0 | Deterministic extraction and grading achieves 100% cache agreement. |

### Top 3 Actions to Raise the Score:
1. **Resolve hard gate violations (G1–G3):** Ensure every assertive sentence cites exact-entity claims with verified numeric fidelity.
2. **Upgrade claim evidence base:** Discard unverified-venue sources (`WJARR`, etc.) and extract empirical claims from verified venues.
3. **Increase corroboration:** Cross-corroborate key findings across 2+ independent sources or across academic & enterprise lanes.

---

## 5. Architectural Decisions & Deviations

The following decisions were logged in `DECISIONS.md`:
- **DEC-007:** Term integrity verification (`src/extract/term_normalizer.py`) flags corrupted terms (e.g. "vibrate coding") and caps confidence.
- **DEC-008:** Deterministic venue tiering (`grade/venue_tiers.yaml`) caps unverified publications at `weak`.
- **DEC-009:** Strict entity matching tags generic AI assistant literature as `topic_level`, preventing misattributions like Kiro productivity claims.

---

## 6. Open Questions & Risks for Human Review

1. **Venue Tier Overrides:** Currently, 4 of the 8 Kiro papers are in `unverified` venues (`WJARR`, `ISJEM`, `EAJIT`, `IJSR`). In Phase 2, the human reviewer can tier unknown venues via the frontend (Gate 2). Should the default policy strictly drop unverified papers or retain them at `weak`?
2. **Exact vs Topic-Level Policy:** Since only 1 of 8 papers actually named Amazon Kiro, an output answering "How is Kiro used?" honestly discloses that *empirical Kiro literature is currently near-zero (Outcome 4: Unmeasured)*. Is this transparent gap presentation aligned with your thought-leadership strategy?
3. **Frontend Review Queue (Phase 2):** Phase 2 will construct Views 1, 2, and 3 in the Streamlit frontend. Should the Claim Review Queue default to sorting by lowest extraction confidence or unverified venue tier?

---

## 7. Phase Acceptance & Hard Stop

All Phase 1 requirements and acceptance criteria from Section 12 of the prompt are complete:
- [x] Schema migrations and state durability pass with zero data loss (`evals/test_r10_migration.py`).
- [x] Regression suite R1 to R7 behaves exactly as specified (`evals/test_regression.py`).
- [x] Atomic claim extraction and deterministic grading executed on all 8 Kiro papers.
- [x] Output scorecard and gate diagnostic report generated.

**HARD STOP:** Awaiting your review and approval before proceeding to Phase 2 (Question register, grading rules UI, venue tiers, and Claim Review Queue).
