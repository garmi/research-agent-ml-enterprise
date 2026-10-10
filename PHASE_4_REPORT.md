# Research Engine v2 — Phase 4 Acceptance Report (`PHASE_4_REPORT.md`)

**Date:** 2026-10-10  
**Git Branch:** `v2-phase-4`  
**Phase:** 4 — Gap Matrix, Synthesis, Scorer, Views 4, 5, 6, 8, and Remaining Regression Cases  
**Author:** AI Agent (Antigravity) & Delivery Leader  

---

## 1. Executive Summary

Phase 4 delivers the core strategic differentiator of Research Engine v2: **Gap Matrix analysis, sentence-level traceable synthesis, deterministic strength verb capping, and automated scoring against Hard Gates G1 through G6 and Quality Components S1 through S7**.

Unlike v1—which filled gaps by interpolating raw topic strings into generic templates or asserting unsubstantiated metrics—v2 synthesizes strictly from verified claims in `ledger.db`. The system honestly surfaces what is **not** known (Outcomes 2, 3, 4 in the Gap Matrix), caps claim verbs strictly by source rigour (`synth/strength_verbs.yaml`), isolates human perspective into separate un-computed opinion sentences, and blocks any output violating the six hard gates.

---

## 2. Key Deliverables & Architecture

### 2.1 Gap Matrix Builder (`src/gaps/matrix_builder.py`)
- Evaluates evidence states across three distinct lanes:
  - **Academic:** `supported` (verified peer-reviewed empirical claims), `partial` (1 empirical or moderate claim), `none found`, or `contradicted`.
  - **Enterprise:** `supported` ($\ge 2$ active enterprise claims), `partial` (1 active claim), `none found`, or `contradicted`.
  - **Practitioner:** `supported` ($\ge 2$ field observations), `partial` (1 observation), `none found`.
- Automatically maps combinations to the 4 Strategic Outcomes:
  - **Outcome 1 (Supported):** Empirical academic research is corroborated by active enterprise practice.
  - **Outcome 2 (Practice Without Evidence):** Enterprise teams are actively adopting, but peer-reviewed empirical evidence is absent.
  - **Outcome 3 (Evidence Without Practice):** Academic research demonstrates capabilities, but enterprise delivery measurement is missing.
  - **Outcome 4 (Unmeasured):** Rigorous evidence is currently lacking across both academic and enterprise lanes.
- Enforces that any `none found` lane state is substantiated by immutable `search_log` records.

### 2.2 Synthesis Engine & Strength Verb Capping (`src/synth/generator.py`)
- Reads **approved or auto-graded claims only** from the ledger.
- Generates structured Field Notes:
  1. *What the Evidence Supports* (assertive sentences linked 1:1 with claim IDs).
  2. *What the Evidence Does Not Support* (explicit evidence voids).
  3. *The Strategic Gap* (prominently disclosing the Gap Matrix outcome).
  4. *Practitioner Field Perspective* (strictly human-written, tagged `type="opinion"`, never authored by AI).
- Sentence strength verbs mapped deterministically from `synth/strength_verbs.yaml`:
  - `strong`: *demonstrates*, *shows*, *finds*
  - `moderate`: *suggests*, *indicates*
  - `weak`: *reports*, *proposes*
  - `vendor_claim`: *states*, *asserts*
  - `anecdote`: *in one case*, *observes*
- Sentences never exceed the strength verb cap of their cited claims.

### 2.3 R14 Boilerplate and Topic String Linter (`lint_output_text`)
- Scans all output sentences to prevent:
  - Raw topic string interpolation into sentences (preventing "how Kiro is being used... across teams").
  - Duplicate or repetitive boilerplate sentences.
- Violations trigger an immediate lint failure and block draft promotion.

### 2.4 Human Gates in Streamlit UI (`src/ledger/ui_views.py`, `web_app.py`)
- **Gate 4 (View 4 - Gap Matrix):** Interactive review of cross-lane states, outcome classifications, and strategic rationales with sign-off/override.
- **Gate 5 (View 5 - Draft Review):** Sentence-level verification badges (traceability, numerics, entity, language honesty). Dedicated input container for human-only practitioner opinion.
- **Gate 6 (View 6 - Publish Gate & Scorecard):** Real-time display of composite quality score (0–100), S1–S7 component breakdowns, publication band (`PUBLISH_READY`, `REVISE`, `DO_NOT_PUBLISH`), and top 3 recommended improvements. Publication is strictly disabled if any hard gate fails.
- **View 8 (Runs and Scores):** Immutable tabular view of all execution runs, code versions, model seeds, and human review audit rows.

---

## 3. Test & Regression Verification

### 3.1 Test Suite Results
All 28 unit, integration, and regression tests passed in **0.78s**:
```bash
$ PYTHONPATH=. .venv/bin/pytest tests evals
======================== 28 passed, 1 warning in 0.78s =========================
```

### 3.2 Regression Suite Status (evals/test_regression.py & evals/test_phase4_synth.py)
| ID | Regression Case | Target Gate / Scorer | Result |
|---|---|---|---|
| **R1** | Kiro misattribution (generic assistant claim cited as Kiro) | Gate G3 Entity Fidelity | **PASSED** (G3 fails, blocked) |
| **R2** | Fabricated figure not in the ledger | Gate G2 Numeric Fidelity | **PASSED** (G2 fails, blocked) |
| **R3** | Vendor claim written as established fact | Gate G4 Language Honesty | **PASSED** (G4 fails, blocked) |
| **R4** | Unverified-venue source reliance | Venue Tiering / Grader | **PASSED** (Capped at `weak`) |
| **R6** | Long verbatim source copy ($\ge 8$ words) | Gate G6 Copyright | **PASSED** (G6 fails, blocked) |
| **R7** | Uncited assertive sentence | Gate G1 Traceability | **PASSED** (G1 fails, blocked) |
| **R8** | Stale source outside time window | Scorer S5 Freshness | **PASSED** (S5 drops from 10 to 0) |
| **R9** | Known contradiction omitted from output | Scorer S4 Gap Disclosure | **PASSED** (S4 drops from 10 to 5) |
| **R10**| Schema migration on populated old DB | Migration Manager | **PASSED** (Zero data loss, WAL verified) |
| **R11**| Re-run reproducibility on cached inputs | Scorer S7 Reproducibility | **PASSED** (Jaccard $\ge 0.90$) |
| **R13**| Corrupted term of art ("vibrate coding") | Term Normalizer | **PASSED** (Confidence drops to 0.50, flagged) |
| **R14**| Raw topic string interpolated into boilerplate | R14 Linter | **PASSED** (Lint failure triggered) |

---

## 4. Benchmark Field Note Scorecard

Running `build_field_note` on question `q-kiro-empirical` with verified ICSE empirical data and AWS vendor disclosure:

| Gate | Status | Violations |
|---|---|---|
| **G1 Traceability** | **PASS** | 0 uncited sentences |
| **G2 Numeric Fidelity** | **PASS** | 0 fabricated numerals; 21.0% verified in ledger |
| **G3 Entity Fidelity** | **PASS** | 0 entity mismatches; target entity "Kiro" exact |
| **G4 Language Honesty** | **PASS** | 0 verb cap violations ("demonstrates" on strong, "states" on vendor) |
| **G5 Confidentiality** | **PASS** | 0 denylist matches |
| **G6 Copyright** | **PASS** | 0 verbatim runs $\ge 8$ words; excerpts $\le 25$ words |
| **Composite Gate Status**| **PASS** | **Eligible for Quality Scoring** |

### Quality Score Components (0 to 100):
| Component | Metric | Score / Max |
|---|---|---|
| **S1 Evidence Strength** | Normalised grade value of cited claims | **30.0 / 30.0** |
| **S2 Corroboration & Diversity**| Multi-source & cross-lane corroboration | **0.0 / 15.0** *(Single peer-reviewed study)* |
| **S3 Question Coverage** | Lane coverage backed by ledger / search_log | **15.0 / 15.0** |
| **S4 Gap Disclosure** | Strategic Outcome disclosed in prose | **10.0 / 10.0** |
| **S5 Freshness & Scope** | Citations inside 24/36 month window | **10.0 / 10.0** |
| **S6 Human Review** | Gate reviews completed at Gate 3 | **4.0 / 10.0** |
| **S7 Reproducibility** | Deterministic extraction and grading agreement | **10.0 / 10.0** |
| **Total Composite Score** | **79.0 / 100** | **Band: REVISE** |

**Top 3 Recommended Improvements Identified by Scorer:**
1. Ingest an independent corroborating study to raise S2 corroboration score (+10.5 pts).
2. Complete human review sign-offs at Gate 3 to increase S6 (+6.0 pts).
3. Connect multi-lane practitioner evidence to reach the 85+ `PUBLISH_READY` threshold.

---

## 5. Deviations & Decisions Recorded
- **DEC-012:** Documented in `DECISIONS.md`. Fully details the Gap Matrix builder, strength-capped synthesis engine, S1–S7 quality scoring formulas, and Streamlit navigation updates.

---

## 6. Phase 4 Acceptance Status
- [x] Gap matrix evaluates Academic, Enterprise, and Field lanes with Outcomes 1 to 4.
- [x] Traceable synthesis generates Field Notes with 100% claim-backed assertive sentences.
- [x] Strength verbs capped deterministically by `strength_verbs.yaml`.
- [x] Scorer computes S1 to S7 components and hard gate evaluations.
- [x] Streamlit Views 4, 5, 6, 8 wired into `web_app.py`.
- [x] All 28 tests passing.

Phase 4 is complete. Ready to proceed to **Phase 5** (Practitioner Lane, Abstraction Gate, Denylist Scanner, Publish Gate, and JSON Export).
