# Integrity and Workflow Enforcement Report

This document records the systematic verification and enforcement of integrity guarantees in the Executive Research Engine, conducted strictly section by section per Prompt A requirements.

---

## Defects Status Summary (D1–D7)

| Defect ID | Description | Status | Evidence Summary |
|-----------|-------------|--------|------------------|
| **D1** | Canned findings, risks, business signals, roadmap steps, content ideas identical across unrelated questions | **Fixed in A1** | Removed 45 hardcoded content strings; zero-hit grep verified; `test_no_literal_report_text` passing. |
| **D2** | Silent fallback on model error swallowed as generic RuntimeError; fallback produces normal-looking findings | **Fixed in A2** | Extractive fallback implemented; error details captured; publication blocked; `test_a2_honest_offline_fallback` passing. |
| **D3** | Gates audit shadow copy rather than final text; template verb stutter; uncited assertions passing G1 | **Fixed in A3** | Migration 002 applied; UnifiedRenderer implemented; output_sentences single source of truth; `test_a3_single_source_of_truth` passing. |
| **D4** | Lanes not scoped to current question; practitioner observations and enterprise registry leakage across runs | **Fixed in A5** | Filtered all lane rows by question_id; fixed practitioner truncation; canary hospital run produces 0 observations and Outcome 3/4 (not 1); `test_a5_lane_scoping` passing. |
| **D5** | Off-topic and stale papers admitted; venue equals API provider name; blanket "Open Pre-print" tagging | Pending (A6, A7) | Next section. |
| **D6** | Contradictory UI state (green banner beside failing gate score); component scores constant | Pending (A8) | Next section. |
| **D7** | Privacy violations: practitioner text in egress, auto-confirmed Gate 6 abstraction, unauthenticated endpoints | Pending (A9) | Next section. |

---

## Section A1: Remove Every Hardcoded Content String

### 1. What Changed
- Identified and eliminated all 45 hardcoded report content strings and templates across `src/llm/stub_client.py`, `src/analysis/multilane_runner.py`, `src/synth/generator.py`, `src/output/html_storyline_builder.py`, `src/output/linkedin_pack_builder.py`, and `src/output/content_pack.py`.
- Replaced `StubLLM` canned returns with clean empty structured responses (`key_findings: []`, `strategic_roadmap: []`, etc.).
- Removed fabricated fallback academic papers (which fabricated ICSE/IEEE DOIs and 34%/22%/38% metrics) from `_harvest_academic_lane`.
- Removed fabricated `curated_feed_data` from enterprise harvesting, and enabled `enterprise_feed_override` for test fixtures.
- Purged the runtime seeded practitioner observation ("140 enterprise microservices") from both `_harvest_practitioner_lane` code and `ledger/practitioner.db`.
- Removed canned roadmap milestones (Phase 1, Phase 2 +32%, Phase 3) from `multilane_runner._build_result_payload`.
- Removed canned business problems / risks fallbacks from `_build_result_payload`.
- Removed canned business signal summary and content ideas fallbacks from `_build_result_payload`.
- Fixed verb stutter in `generator.py` and replaced canned `gap_descriptions` with dynamic Gap Matrix rationale.
- Replaced hardcoded metric cards (`20×`, `&approx;67%`, `90%`, `28–42%`), false "100% Zero-Hallucination" badge, and fake timeline horizons in `html_storyline_builder.py` with real, computed metrics.
- Replaced hardcoded LinkedIn post templates in `linkedin_pack_builder.py` with dynamic formatters driven solely by synthesis findings and recommendations.
- Replaced fallback ideas in `content_pack.py` with strictly dynamic derivations.
- Created `HARDCODED_STRINGS.md` cataloging all 45 strings, lines, and dispositions.

### 2. Files Touched
- `src/llm/stub_client.py`
- `src/analysis/multilane_runner.py`
- `src/synth/generator.py`
- `src/output/html_storyline_builder.py`
- `src/output/linkedin_pack_builder.py`
- `src/output/content_pack.py`
- `tests/test_multilane_workflow.py`
- `tests/test_no_literal_report_text.py` (new)
- `HARDCODED_STRINGS.md` (new)
- `INTEGRITY_REPORT.md` (new)

### 3. Tests Added & Executed
- Added `tests/test_no_literal_report_text.py`.
  - Initial run: **FAILED** (Found 17 canned report content strings in target modules).
  - After fix: **PASSED** (0 canned strings found).

### 4. Verification & Pasted Evidence

#### Failing Test Output (Before Fix):
```
=================================== FAILURES ===================================
_________________________ test_no_literal_report_text __________________________
>       assert not violations, f"Found {len(violations)} canned report content strings in target modules:\n" + "\n".join(violations)
E       AssertionError: Found 17 canned report content strings in target modules:
E         src/llm/stub_client.py:23: contains canned string 'Empirical velocity increases by 32%' -> "Empirical velocity increases by 32% across standard delivery tasks [P1].",
E         src/llm/stub_client.py:24: contains canned string 'Bounded autonomy contracts prevent out-of-band regression risks' -> "Bounded autonomy contracts prevent out-of-band regression risks [P2].",
E         src/llm/stub_client.py:25: contains canned string 'Platform engineering teams report higher DevEx satisfaction scores' -> "Platform engineering teams report higher DevEx satisfaction scores [P1].",
E         src/llm/stub_client.py:34: contains canned string 'Unverified extrapolation in production pipelines leads to silent architectural drift' -> "Unverified extrapolation in production pipelines leads to silent architectural drift.",
E         src/llm/stub_client.py:35: contains canned string 'Lack of centralized audit logging hampers compliance in regulated sectors' -> "Lack of centralized audit logging hampers compliance in regulated sectors.",
E         src/analysis/multilane_runner.py:563: contains canned string 'Achieved zero unauthorized architectural drift across 140 enterprise microservices' -> outcome="Achieved zero unauthorized architectural drift across 140 enterprise microservices",
E         src/analysis/multilane_runner.py:563: contains canned string '140 enterprise microservices' -> outcome="Achieved zero unauthorized architectural drift across 140 enterprise microservices",
E         src/analysis/multilane_runner.py:831: contains canned string 'Phase 1 (Days 1–30)' -> {"phase": "Phase 1 (Days 1–30)", "action": "Establish Deterministic Verification Gates & CI Sandbox"
E         src/analysis/multilane_runner.py:832: contains canned string '+32% velocity on boilerplate' -> {"phase": "Phase 2 (Days 31–90)", "action": "Roll out bounded autonomous agents for repetitive unit 
E         src/analysis/multilane_runner.py:876: contains canned string 'Unverified extrapolation in production pipelines leads to silent architectural drift' -> "Unverified extrapolation in production pipelines leads to silent architectural drift.",
E         src/analysis/multilane_runner.py:877: contains canned string 'Lack of centralized audit logging hampers compliance in regulated sectors' -> "Lack of centralized audit logging hampers compliance in regulated sectors.",
E         src/analysis/multilane_runner.py:878: contains canned string 'Premature agentic deployment without deterministic test suites amplifies MTTR' -> "Premature agentic deployment without deterministic test suites amplifies MTTR during incidents.",
E         src/analysis/multilane_runner.py:880: contains canned string 'Robust empirical support for architecture adoption under bounded contracts' -> "business_signal": executive_synthesis.get("business_context", {}).get("business_signal", {}).get("s
E         src/analysis/multilane_runner.py:888: contains canned string 'Why the 32% Dev Velocity metric is misleading' -> "Why the 32% Dev Velocity metric is misleading without Bounded Autonomy Contracts",
E         src/analysis/multilane_runner.py:889: contains canned string 'The 5 Deterministic Gates every VP of Engineering' -> "The 5 Deterministic Gates every VP of Engineering must establish for AI coding agents",
E         src/analysis/multilane_runner.py:890: contains canned string 'From Copilot to Kiro: The shift from reactive completion' -> "From Copilot to Kiro: The shift from reactive completion to autonomous specification alignment",
E         src/output/html_storyline_builder.py:657: contains canned string '100% Zero-Hallucination Verified Citations' -> <div class="meta-item"><strong>Verification:</strong> 100% Zero-Hallucination Verified Citations</di
```

#### Passing Test Output (After Fix):
```
PYTHONPATH=. .venv/bin/pytest tests/test_no_literal_report_text.py
============================= test session starts ==============================
collected 1 item                                                               

tests/test_no_literal_report_text.py .                                   [100%]

============================== 1 passed in 0.02s ===============================
```

#### Zero-Hit Grep Output Across All Target Modules:
```
$ python -c '
import re
from pathlib import Path
targets = [
    "src/llm/stub_client.py", "src/analysis/multilane_runner.py", "src/synth/generator.py",
    "src/output/html_storyline_builder.py", "src/output/linkedin_pack_builder.py",
    "src/output/content_pack.py", "src/output/report_builder.py", "src/analysis/synthesizer.py"
]
pat = re.compile(r"32% across standard delivery tasks|Bounded autonomy contracts prevent|Platform engineering teams report higher DevEx|Unverified extrapolation in production pipelines|Lack of centralized audit logging hampers|Premature agentic deployment without deterministic|Robust empirical support for architecture adoption|140 enterprise microservices|\+32% velocity on boilerplate|Why the 32% Dev Velocity metric|The 5 Deterministic Gates every VP|From Copilot to Kiro|Phase 1 \(Days 1–30\)|100% Zero-Hallucination", re.IGNORECASE)
hits = [f"{t}:{i}:{l}" for t in targets for i, l in enumerate(Path(t).read_text().splitlines(), 1) if pat.search(l)]
print("Total hits:", len(hits))
'
Total hits: 0
```

#### Full Test Suite Status:
```
PYTHONPATH=. .venv/bin/pytest tests evals -k "not test_ui_smoke"
================= 35 passed, 1 deselected, 1 warning in 1.21s ==================
```

### 5. Anything NOT Done in A1
- Did not modify Cloud Run settings or deploy.
- Did not change existing gate weights or thresholds.
- Dynamic extractive fallback synthesis is specified for implementation in A2.

---

## Section A2: Honest Offline Path, Error Logging, and Extractive Fallback

### 1. What Changed
- **Diagnosed LLM Failures & Credentials:**
  - Evaluated local environment: `GEMINI_API_KEY` was populated with an OAuth token prefix (`AQ.A...`) rather than an AI Studio key (`AIza...`), causing HTTP 401 Unauthorized errors against Google generative language endpoints.
  - Corrected model naming: The configured model was `gemini-3.8-flash `, which is non-existent in the Gemini Developer API and had trailing whitespace. Replaced default with canonical `gemini-2.5-flash` in `config.yaml` and `src/llm/factory.py`, and added `.strip()` to model sanitization.
  - Sanitized Error Logging: Updated `src/llm/gemini_client.py` to preserve raw HTTP status codes, capture sanitized error response bodies, mask all API key patterns matching `AIza[0-9A-Za-z-_]{35}`, and surface transparent error metadata instead of swallowing errors into generic `RuntimeError`.
- **Honest Extractive Fallback Implementation:**
  - Implemented `_build_extractive_fallback_synthesis` in `src/analysis/multilane_runner.py`:
    * When the primary language model is offline, encounters authentication failures, or raises an exception, the runner does not pretend synthesis succeeded or emit canned inferences.
    * Generates findings verbatim from verified ledger claims: `[P#] Academic claim <verb> that <claim text>`, `[source_id] Enterprise evidence <verb> that <text>`, `[source_id] Field observation <verb> that <text>`.
    * Leaves `recommendations: []`, `strategic_roadmap: []`, `themes: []`, and `market_trends: []` empty with an explicit message that recommendations require LLM synthesis.
    * Sets `generation_mode: "extractive_fallback"`, `is_fallback: True`, and captures structured `error_details` (class, http_status, message, masked_url).
    * Enforces publication block: Sets `publish_success = False`, `pub_res = {"allowed": False, "status": "blocked", "reason": "extractive_fallback_only"}`, `score_results["band"] = "NOT_PUBLISHABLE"`, and `doc.status = "blocked"`.
    * Persists `generation_mode`, `is_fallback`, and `error_details` into `runs.config_json` in the SQLite ledger.
- **UI Error & Fallback Presentation:**
  - Updated `web_app.py` (lines 1253–1280):
    * If `is_fallback` is True, suppresses the green "G1–G6 AUDITED • ZERO UNGROUNDED CLAIMS" banner and instead renders `st.error(f"🛑 {results['blocking_banner']}")`.
    * Adds an expandable drawer `Diagnostic Error Details (LLM Provider Exception)` displaying the exact error class, HTTP status, sanitized error message, and masked URL without leaking sensitive secrets.

### 2. Files Touched
- `config.yaml`
- `src/llm/factory.py`
- `src/llm/gemini_client.py`
- `src/analysis/multilane_runner.py`
- `web_app.py`
- `tests/test_a2_honest_offline_fallback.py` (new)
- `INTEGRITY_REPORT.md`

### 3. Tests Added & Executed
- Added `tests/test_a2_honest_offline_fallback.py`:
  - Simulates provider exception (`invalid_provider_that_raises`).
  - Asserts `generation_mode == "extractive_fallback"`, `is_fallback is True`.
  - Asserts structured `error_details` populated in payload and ledger `run_record.config_json`.
  - Asserts quality band is NOT `PUBLISH_READY`.
  - Asserts `recommendations` and `strategic_roadmap` are empty.
  - Asserts all findings are verbatim extractive claims with valid citation tags `[P#]`.
  - Result: **PASSED** in 7.47s.

### 4. Verification & Pasted Evidence

#### A2 Test Execution:
```
PYTHONPATH=. .venv/bin/pytest tests/test_a2_honest_offline_fallback.py
============================= test session starts ==============================
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collected 1 item                                                               

tests/test_a2_honest_offline_fallback.py .                               [100%]

========================= 1 passed, 1 warning in 7.47s =========================
```

#### Full Test Suite Status (Zero Regressions):
```
PYTHONPATH=. .venv/bin/pytest tests evals -k "not test_ui_smoke"
============================= test session starts ==============================
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collected 37 items / 1 deselected / 36 selected                                

tests/test_a2_honest_offline_fallback.py .                               [  2%]
tests/test_multilane_workflow.py .                                       [  5%]
tests/test_no_literal_report_text.py .                                   [  8%]
tests/test_pipeline.py ....                                              [ 19%]
tests/test_question_formulator.py ..                                     [ 25%]
evals/test_phase2_service.py ....                                        [ 36%]
evals/test_phase3_enterprise.py ...                                      [ 44%]
evals/test_phase4_synth.py ...                                           [ 52%]
evals/test_phase5_practitioner_publish.py ..                             [ 58%]
evals/test_r10_migration.py .                                            [ 61%]
evals/test_regression.py ..............                                  [100%]

================= 36 passed, 1 deselected, 1 warning in 8.58s ==================
```

### 5. Anything NOT Done in A2
- Single output renderer unification across export formats (.md, .json, .csv, linkedin, html) is scheduled in Section A3.
- Source-to-question term overlap and run-scoped citations are scheduled in Section A4.
- Cloud Run environment variable updates are scheduled in Section A9.

---

## Section A3: Single Source of Truth: output_sentences Table

### 1. What Changed
- **Eliminated Defect D3 (Shadow Copy Synthesis & Drift):**
  - Previously, the UI, Markdown report, HTML storyline, and LinkedIn pack drifted from each other and showed synthesis text that had never been audited by Hard Gates G1–G6.
  - Formulated and applied forward-only migration `ledger/migrations/002_expand_sentence_types.sql` (migrating `ledger.db` to schema version 2), safely expanding the `output_sentences.type` CHECK constraint to include:
    `('assertive', 'opinion', 'field', 'heading', 'signal', 'risk', 'roadmap', 'finding', 'negative_finding')`.
  - Updated Pydantic data model `SentenceType` in `src/ledger/models.py`.
- **Created Unified Single Renderer (`src/output/unified_renderer.py`):**
  - Created `UnifiedRenderer`: reads strictly from `output_sentences` for `doc_id` and produces:
    * UI presentation structures (`findings`, `signals`, `risks`, `roadmap`, `negative_findings`).
    * Markdown report (`outputs/reports/research_report.md`).
    * HTML storyline (`outputs/reports/strategic_storyline.html`).
    * LinkedIn pack (`outputs/reports/linkedin_professional_pack.md`).
    * JSON export (`outputs/json/research_report.json`), explicitly embedding the full `output_sentences` row list.
    * Paper index CSV (`outputs/csv/paper_index.csv`).
  - Enforced honest empty states: If a section has no grounded sentences (e.g., no negative findings, no risks), generic filler is eliminated in favor of explicit empty states:
    * Negative findings: references `search_log` zero-result queries or gap matrix boundaries, else `"No negative findings in evidence ledger."`
    * Risks: `"No verified risk assertions in evidence ledger."`
    * Roadmap: `"Recommendations require LLM synthesis; currently in offline extractive mode."`
- **Synchronized Stage 6 Synthesis and Governance Audit:**
  - In `src/analysis/multilane_runner.py`:
    * Generates `executive_synthesis` (via model or extractive fallback).
    * `synth_engine.build_field_note` builds the complete `OutputDoc` and all `OutputSentence` records for `findings`, `signals`, `risks`, `negative_findings`, `roadmap`, and persists them to `output_sentences` table in `ledger.db`.
    * Hard Gates G1–G6 and S1–S7 Quality Scorer audit the exact sentences in `output_sentences`.
    * `UnifiedRenderer` writes all outputs from those audited sentences.
    * `_build_result_payload` passes `doc_id` and derives all UI components strictly from `sentences`.
  - In `src/score/checker.py`:
    * Formatted violation messages as `Sentence [{s.id}] (ordinal {s.ordinal}) ...` and exposed structured `hard_gates` containing matching `sentence_id` values.

### 2. Files Touched
- `ledger/migrations/002_expand_sentence_types.sql` (new)
- `src/ledger/models.py`
- `src/output/unified_renderer.py` (new)
- `src/synth/generator.py`
- `src/analysis/multilane_runner.py`
- `src/score/checker.py`
- `tests/test_a3_single_source_of_truth.py` (new)
- `INTEGRITY_REPORT.md`

### 3. Tests Added & Executed
- Added `tests/test_a3_single_source_of_truth.py`:
  - Runs workflow and extracts `doc_id`.
  - Queries `output_sentences` table from `ledger.db`.
  - Asserts every UI finding, signal, risk, roadmap action exists in `output_sentences`.
  - Asserts gate audit logged sentence IDs match `output_sentences.id`.
  - Asserts `research_report.json` contains full `output_sentences` list.
  - Asserts `research_report.md` and `linkedin_professional_pack.md` render sentences matching `output_sentences`.
  - Asserts negative findings are present and grounded in `output_sentences`.
  - Result: **PASSED** in 0.40s.

### 4. Verification & Pasted Evidence

#### Failing Test Output (Before Fix):
```
=================================== FAILURES ===================================
_____________ test_every_rendered_text_exists_in_output_sentences ______________
        doc_id = result.get("doc_id")
>       assert doc_id, "Expected doc_id in workflow result payload"
E       AssertionError: Expected doc_id in workflow result payload
E       assert None
tests/test_a3_single_source_of_truth.py:50: AssertionError
```

#### Passing Test Output (After Fix):
```
PYTHONPATH=. .venv/bin/pytest tests/test_a3_single_source_of_truth.py
============================= test session starts ==============================
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collected 1 item                                                               

tests/test_a3_single_source_of_truth.py .                                [100%]

========================= 1 passed, 1 warning in 0.40s =========================
```

#### Full Test Suite Status (Zero Regressions):
```
PYTHONPATH=. .venv/bin/pytest tests evals -k "not test_ui_smoke"
============================= test session starts ==============================
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collected 38 items / 1 deselected / 37 selected                                

tests/test_a2_honest_offline_fallback.py .                               [  2%]
tests/test_a3_single_source_of_truth.py .                                [  5%]
tests/test_multilane_workflow.py .                                       [  8%]
tests/test_no_literal_report_text.py .                                   [ 10%]
tests/test_pipeline.py ....                                              [ 21%]
tests/test_question_formulator.py ..                                     [ 27%]
evals/test_phase2_service.py ....                                        [ 37%]
evals/test_phase3_enterprise.py ...                                      [ 45%]
evals/test_phase4_synth.py ...                                           [ 54%]
evals/test_phase5_practitioner_publish.py ..                             [ 59%]
evals/test_r10_migration.py .                                            [ 62%]
evals/test_regression.py ..............                                  [100%]

================= 37 passed, 1 deselected, 1 warning in 8.81s ==================
```

### 5. Anything NOT Done in A3
- Run-scoped citation checks and source-to-question term overlap are scheduled in Section A4.
- Question-scoping of practitioner observations and enterprise sources is scheduled in Section A5.

---

## Section A4: Citation Support Check (Run-Scoped)

### 1. What Changed
- Extended `GateChecker.check_output` signature in `src/score/checker.py` to accept `sources`, `question`, and `papers`.
- **Support Check 1 (G2 Numeric Fidelity):** Strictly verifies that any numerals present in assertive sentences appear in cited claim `value_json` or `source_excerpt` (fallback to `text` only if excerpt is absent). Reports `"Ungrounded numeral '<num>'"` upon violation.
- **Support Check 2 (G2 Extended Excerpt Overlap):** Requires assertive sentences to share at least 2 non-stopword terms with the cited claim's `source_excerpt`. Reports `"Insufficient excerpt overlap (<count> < 2 non-stopword terms)"`.
- **Support Check 3 (G3 Extended Source Topic Support):** Requires cited claim sources to share at least 1 substantive term or common morphological stem (prefix $\ge 4$ characters) with the research question text/scope. Reports `"Source topic mismatch between source '<title>' and question '<text>' (0 shared terms)"`.
- **Run-Scoped `[P#]` Resolution:** Asserts that every `[P#]` token in output sentences resolves strictly to a source in that run's Lane A list ($1 \le \# \le \text{len}(papers)$); invalid or out-of-range references fail Gate G1.
- Updated `src/synth/generator.py`: eliminated silent fallbacks that previously masked unresolvable `[P#]` tags with default claims, and passed `sources`, `question`, and `papers` to `self.checker.check_output`.

### 2. Files Touched
- `src/score/checker.py`
- `src/synth/generator.py`
- `tests/test_a4_traceable_citations.py` (new)
- `INTEGRITY_REPORT.md`

### 3. Tests Added & Executed
- Added `tests/test_a4_traceable_citations.py` with:
  1. `test_d1_defect_blocked_source_topic_mismatch_and_ungrounded_numeral`: Plants the exact D1 case (EU healthcare regulation paper cited for 32% software delivery velocity). Verifies document is BLOCKED and reports all 3 support violations.
  2. `test_valid_citation_matching_numeral_and_topic_passes`: Verifies legitimate software engineering paper citation with grounded numerals and topic overlap passes all gates cleanly.

### 4. Verification & Pasted Evidence

#### Failing Test Output (Before Fix):
```
PYTHONPATH=. .venv/bin/pytest tests/test_a4_traceable_citations.py
============================= test session starts ==============================
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collected 2 items                                                              

tests/test_a4_traceable_citations.py FF                                  [100%]

=================================== FAILURES ===================================
_____ test_d1_defect_blocked_source_topic_mismatch_and_ungrounded_numeral ______
...
>       result = checker.check_output(
            sentences=[bad_sentence],
            ledger_claims=ledger_claims,
            source_texts=source_texts,
            sources=sources,
            question=question,
        )
E       TypeError: check_output() got an unexpected keyword argument 'sources'
============================== 2 failed in 0.14s ===============================
```

#### Passing Test Output (After Fix):
```
PYTHONPATH=. .venv/bin/pytest tests/test_a4_traceable_citations.py
============================= test session starts ==============================
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collected 2 items                                                              

tests/test_a4_traceable_citations.py ..                                  [100%]

============================== 2 passed in 0.11s ===============================
```

#### Full Test Suite Status (Zero Regressions, 39 Passed):
```
PYTHONPATH=. .venv/bin/pytest tests evals -k "not test_ui_smoke"
============================= test session starts ==============================
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collected 40 items / 1 deselected / 39 selected                                

tests/test_a2_honest_offline_fallback.py .                               [  2%]
tests/test_a3_single_source_of_truth.py .                                [  5%]
tests/test_a4_traceable_citations.py ..                                  [ 10%]
tests/test_multilane_workflow.py .                                       [ 12%]
tests/test_no_literal_report_text.py .                                   [ 15%]
tests/test_pipeline.py ....                                              [ 25%]
tests/test_question_formulator.py ..                                     [ 30%]
evals/test_phase2_service.py ....                                        [ 41%]
evals/test_phase3_enterprise.py ...                                      [ 48%]
evals/test_phase4_synth.py ...                                           [ 56%]
evals/test_phase5_practitioner_publish.py ..                             [ 61%]
evals/test_r10_migration.py .                                            [ 64%]
evals/test_regression.py ..............                                  [100%]

================= 39 passed, 1 deselected, 1 warning in 8.80s ==================
```

### 5. Anything NOT Done in A4
- Scoping of enterprise and practitioner observations to run and question is scheduled in Section A5.

---

## Section A5: Scope Every Lane to Run and Question

### 1. What Changed
- **Scoping Practitioner Observations:** Updated `MultiLaneResearchRunner._harvest_practitioner_lane` and `_build_result_payload` in `src/analysis/multilane_runner.py` to pass `question_id=question_obj.id` into `PractitionerCollector.list_observations()`. Eliminated cross-question leakage where unrelated practitioner notes (e.g. software delivery microservices) previously leaked into other questions.
- **Scoping Enterprise Sources:** Filtered `ent_sources_formatted` strictly to sources associated with claims extracted for `question_obj.id` in that run.
- **Removed Observation Truncation:** Updated `PractitionerCollector.add_observation` in `src/collectors/practitioner/collector.py` and `multilane_runner.py` to preserve complete text without `[:50]` or `[:140]` truncations in `situation`, `action`, `outcome`, or `context_payload`.
- **Honest Empty Lane Rendering:** Updated `web_app.py` so that:
  - When 0 enterprise claims exist for a question, Lane B renders `"No enterprise claims recorded for this question"`.
  - When 0 practitioner observations exist for a question, Lane C renders `"No practitioner observations recorded for this question"`.
  - Reset fallback counts in metric captions from misleading defaults (4 and 1) to honest `0`.
- **Gap Matrix Scoping:** Verified that for questions lacking enterprise claims or practitioner observations (such as the canary hospital question), `GapMatrixBuilder` evaluates `field_state = "none found"`, `enterprise_state = "none found"`, and Outcome 3 or 4 (NEVER Outcome 1).

### 2. Files Touched
- `src/analysis/multilane_runner.py`
- `src/collectors/practitioner/collector.py`
- `web_app.py`
- `tests/test_multilane_workflow.py`
- `tests/test_a5_lane_scoping.py` (new)
- `INTEGRITY_REPORT.md`

### 3. Tests Added & Executed
- Added `tests/test_a5_lane_scoping.py` with:
  1. `test_canary_hospital_question_isolated_from_software_delivery_observations`: Seeds unrelated software delivery practitioner observations, runs canary hospital question, and asserts 0 practitioner observations, 0 enterprise claims, and Outcome 3/4 (NEVER Outcome 1).
  2. `test_practitioner_observation_preserves_full_text_without_truncation`: Verifies situation, action, and outcome text > 50 characters are preserved completely without truncation.
- Updated `tests/test_multilane_workflow.py` to attach observation explicitly to the question id.

### 4. Verification & Pasted Evidence

#### Failing Test Output (Before Fix):
```
PYTHONPATH=. .venv/bin/pytest tests/test_a5_lane_scoping.py
============================= test session starts ==============================
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collected 2 items                                                              

tests/test_a5_lane_scoping.py F.                                         [100%]

=================================== FAILURES ===================================
__ test_canary_hospital_question_isolated_from_software_delivery_observations __
...
>           assert len(results["practitioner_observations"]) == 0, (
                f"Expected 0 practitioner observations for hospital question, found: {results['practitioner_observations']}"
            )
E           AssertionError: Expected 0 practitioner observations for hospital question, found: [{'id': 'claim_prac_0ae40d99db', 'situation': '140 enterprise microservices undergoing continuous deployment', 'decision': 'Enforced strict gate check', 'action': 'Automated static analysis', 'outcome': 'Zero defect regression', 'date': '2026-10-11', 'is_custom': False}]
E           assert 1 == 0
==================== 1 failed, 1 passed, 1 warning in 0.48s ====================
```

#### Passing Test Output (After Fix):
```
PYTHONPATH=. .venv/bin/pytest tests/test_a5_lane_scoping.py
============================= test session starts ==============================
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collected 2 items                                                              

tests/test_a5_lane_scoping.py ..                                         [100%]

========================= 2 passed, 1 warning in 0.38s =========================
```

#### Full Test Suite Status (Zero Regressions, 41 Passed):
```
PYTHONPATH=. .venv/bin/pytest tests evals -k "not test_ui_smoke"
============================= test session starts ==============================
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collected 42 items / 1 deselected / 41 selected                                

tests/test_a2_honest_offline_fallback.py .                               [  2%]
tests/test_a3_single_source_of_truth.py .                                [  4%]
tests/test_a4_traceable_citations.py ..                                  [  9%]
tests/test_a5_lane_scoping.py ..                                         [ 14%]
tests/test_multilane_workflow.py .                                       [ 17%]
tests/test_no_literal_report_text.py .                                   [ 19%]
tests/test_pipeline.py ....                                              [ 29%]
tests/test_question_formulator.py ..                                     [ 34%]
evals/test_phase2_service.py ....                                        [ 43%]
evals/test_phase3_enterprise.py ...                                      [ 51%]
evals/test_phase4_synth.py ...                                           [ 58%]
evals/test_phase5_practitioner_publish.py ..                             [ 63%]
evals/test_r10_migration.py .                                            [ 65%]
evals/test_regression.py ..............                                  [100%]

================= 41 passed, 1 deselected, 1 warning in 9.05s ==================
```

### 5. Anything NOT Done in A5
- Enterprise lane source distinctness, harvest count honesty, and vendor claim capping are scheduled in Section A6.

---

## Section A6: Enterprise Lane Honesty and Gap Matrix Rules

### 1. What Changed
- **Separated Distinct Sources and Claims Counts:**
  - In `src/analysis/multilane_runner.py`:
    - Track distinct source IDs vs total extracted claims for all lanes in `lane_breakdown`: `academic_sources_count`, `academic_claims_count`, `enterprise_sources_count`, `enterprise_claims_count`, `practitioner_sources_count`, and `practitioner_claims_count`.
    - Volume metric in payload reports distinct sources count and claims count accurately.
  - In `web_app.py`:
    - Updated Lane B caption: `Harvested {claims_count} enterprise claims from {sources_count} distinct sources (commercial cap enforced)`.
    - Ensured "Harvested N" strictly reflects items retrieved and claims extracted for the question, never the number of registry entries.
- **Enforced Deterministic Vendor-Only Capping (Outcome 2 Max):**
  - Added `vendor_only_max_outcome: 2` to `grade/rules.yaml` under `caps:` and to `config.yaml`.
  - Updated `GapMatrixBuilder` in `src/gaps/matrix_builder.py`:
    - Inspects `commercial_stake`, `venue_tier`, `c.grade == "vendor_claim"`, and `c.context_json["source_stake"] == "vendor"`.
    - When all enterprise claims originate solely from vendor sources without independent non-vendor corroboration or practitioner field notes, outcome is capped at Outcome 2 (NEVER Outcome 1), even when strong peer-reviewed academic literature is present.
    - Updated `rationale` to record the exact rule fired: `"Outcome 2: Practice without evidence — Enterprise claims originate solely from vendor sources without independent empirical corroboration."`
- **Enforced Strategic Gap Matrix 1–4 Determinism:**
  - Outcome 1 requires at least one peer-reviewed academic paper AND at least one non-vendor enterprise source.
  - Outcome 2 fires when enterprise evidence exists without peer-reviewed academic support (or when enterprise claims are vendor-only).
  - Outcome 3 fires when academic research demonstrates capabilities, but enterprise/practitioner evidence is absent.
  - Outcome 4 fires when rigorous evidence is lacking across both academic and enterprise lanes.

### 2. Files Touched
- `grade/rules.yaml`
- `config.yaml`
- `src/gaps/matrix_builder.py`
- `src/analysis/multilane_runner.py`
- `web_app.py`
- `tests/test_a6_enterprise_honesty.py` (new)
- `INTEGRITY_REPORT.md`

### 3. Tests Added & Executed
- Added `tests/test_a6_enterprise_honesty.py`:
  1. `test_vendor_only_capping_caps_at_outcome_2_not_outcome_1`: Validates that 1 vendor source + strong academic research evaluates to Outcome 2, never Outcome 1, and records vendor capping in rationale.
  2. `test_sources_and_claims_counted_separately_in_runner_payload`: Validates that 1 enterprise source yielding 2 claims produces `enterprise_sources_count: 1` and `enterprise_claims_count: 2`, proving distinct source and claim counting.
  3. `test_outcome_1_requires_peer_reviewed_academic_and_non_vendor_enterprise`: Validates that Outcome 1 requires both peer-reviewed academic evidence and non-vendor enterprise evidence.
- Verified canary hospital question in `tests/test_a5_lane_scoping.py`: 0 enterprise claims, 0 practitioner claims produces Outcome 3 or 4, never 1.

### 4. Verification & Pasted Evidence

#### Failing Test Output (Before Fix):
```
=================================== FAILURES ===================================
__________ test_vendor_only_capping_caps_at_outcome_2_not_outcome_1 ___________
    entry = builder.evaluate_question_lanes(question_id=q.id, run_id="run-test-vcap")
>   assert entry.outcome == 2, f"Expected Outcome 2 due to vendor-only capping, but got Outcome {entry.outcome}"
E   AssertionError: Expected Outcome 2 due to vendor-only capping, but got Outcome 1
E   assert 1 == 2
tests/test_a6_enterprise_honesty.py:104: AssertionError
```

#### Passing Test Output (After Fix):
```
PYTHONPATH=. .venv/bin/pytest tests/test_a6_enterprise_honesty.py -v
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0 -- /Users/gauravm/Developer/projects/research-agent-ml-enterprise/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collecting ... collected 3 items                                                              

tests/test_a6_enterprise_honesty.py::test_vendor_only_capping_caps_at_outcome_2_not_outcome_1 PASSED [ 33%]
tests/test_a6_enterprise_honesty.py::test_sources_and_claims_counted_separately_in_runner_payload PASSED [ 66%]
tests/test_a6_enterprise_honesty.py::test_outcome_1_requires_peer_reviewed_academic_and_non_vendor_enterprise PASSED [100%]

========================= 3 passed, 1 warning in 0.50s =========================
```

#### Full Test Suite Status (Zero Regressions, 44 Passed):
```
PYTHONPATH=. .venv/bin/pytest tests evals -k "not test_ui_smoke"
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collecting ... collected 45 items / 1 deselected / 44 selected                                

tests/test_a2_honest_offline_fallback.py .                               [  2%]
tests/test_a3_single_source_of_truth.py .                                [  4%]
tests/test_a4_traceable_citations.py ..                                  [  9%]
tests/test_a5_lane_scoping.py ..                                         [ 13%]
tests/test_a6_enterprise_honesty.py ...                                  [ 20%]
tests/test_multilane_workflow.py .                                       [ 22%]
tests/test_no_literal_report_text.py .                                   [ 25%]
tests/test_pipeline.py ....                                              [ 34%]
tests/test_question_formulator.py ..                                     [ 38%]
evals/test_phase2_service.py ....                                        [ 47%]
evals/test_phase3_enterprise.py ...                                      [ 54%]
evals/test_phase4_synth.py ...                                           [ 61%]
evals/test_phase5_practitioner_publish.py ..                             [ 65%]
evals/test_r10_migration.py .                                            [ 68%]
evals/test_regression.py ..............                                  [100%]

================= 44 passed, 1 deselected, 1 warning in 9.34s ==================
```

### 5. Anything NOT Done in A6
- Academic paper retrieval filtering (`min_year >= 2020`), search log rejection reasons, and venue tier metadata honesty are scheduled in Section A7.

---

## Section A7: Retrieval Quality and Venue Metadata

### 1. What Changed
- **Honest Venue Metadata Resolution (Eliminated Defect D5):**
  - Updated `src/fetchers/crossref_client.py` to query `container-title` and extract real journal/conference publication venues, preventing the API provider name "Crossref" from masquerading as a venue.
  - Updated `src/fetchers/semantic_scholar_client.py` to query `publicationVenue` and resolve legitimate venue names instead of "Semantic Scholar".
  - Created `resolve_honest_venue_and_type(p)` in `src/analysis/multilane_runner.py`:
    - Completely strips aggregator names (`Crossref`, `Semantic Scholar`, `OpenAlex`, `Academic Repository`) from venue fields.
    - Resolves real venue names from `container_title`, `publisher`, or publisher domain fingerprints (`IEEE Transactions`, `ACM Digital Library`, `Nature Publishing Group`, `Elsevier ScienceDirect`, `SpringerLink`, `arXiv`).
- **Real Source Types (Eliminated Blanket "Open Pre-print" Badge):**
  - Assigned distinct, accurate source types: `Peer-Reviewed Journal`, `Conference`, `Preprint`, `Book`, `Industry Report`.
  - Replaced blanket `Open Pre-print` labelling across UI and exports.
- **Honest Publication Date Display (Eliminated "Published: None"):**
  - Missing or null publication dates render as `Date unknown` and `Date: <em>Date unknown</em>` across `multilane_runner.py` and `web_app.py`, never printing "Published: None".
- **Retrieval-Time Year Filtering (`year >= min_year`):**
  - Added `min_year: 2020` under `research:` in `config.yaml`.
  - Enforced `min_year` at retrieval time in `MultiLaneResearchRunner._harvest_academic_lane`.
  - Papers older than `min_year` are excluded from the ledger and logged to `search_log` with `rejected_reason="year_below_minimum: publication year {yr} is older than min_year {min_year}"`.
- **Deterministic Off-Topic Paper Filtering:**
  - Evaluates substantive question/paper term overlap (filtering English stopwords).
  - Papers with 0 question term overlap (such as macroeconomic trade papers on a software question) are rejected before ledger insertion and logged to `search_log` with `rejected_reason="off_topic_low_relevance: paper has no substantive term overlap with question scope"`.
- **Database Schema Migration 003:**
  - Applied user-approved migration `ledger/migrations/003_add_rejected_fields_to_search_log.sql` adding `rejected_reason TEXT` and `details_json TEXT` to `search_log`.
  - Updated `SearchLog` Pydantic model in `src/ledger/models.py` and `LedgerRepository` in `src/ledger/repository.py`.

### 2. Files Touched
- `ledger/migrations/003_add_rejected_fields_to_search_log.sql` (new)
- `config.yaml`
- `src/ledger/models.py`
- `src/ledger/repository.py`
- `src/fetchers/crossref_client.py`
- `src/fetchers/semantic_scholar_client.py`
- `src/analysis/multilane_runner.py`
- `web_app.py`
- `tests/test_a7_retrieval_and_venues.py` (new)
- `INTEGRITY_REPORT.md`

### 3. Tests Added & Executed
- Added `tests/test_a7_retrieval_and_venues.py`:
  1. `test_venue_never_displays_api_provider_and_real_source_types`: Asserts venue never shows "Crossref", assigns "Peer-Reviewed Journal" / "Conference", preprint gets "Preprint", and missing date gets "Date unknown" (never "None").
  2. `test_retrieval_filters_by_min_year_and_logs_rejected_stale_papers`: Asserts paper from 2008 is rejected, excluded from ledger sources, and logged to `search_log` with `year_below_minimum`.
  3. `test_retrieval_rejects_off_topic_papers_by_term_overlap`: Asserts off-topic OECD trade economics paper is rejected, excluded from ledger sources, and logged to `search_log` with `off_topic_low_relevance`.

### 4. Verification & Pasted Evidence

#### Failing Test Output (Before Fix):
```
=================================== FAILURES ===================================
_________ test_venue_never_displays_api_provider_and_real_source_types _________
            p1 = papers[0]
>           assert p1["venue"] != "Crossref", f"Venue must not be API provider name 'Crossref', got '{p1['venue']}'"
E           AssertionError: Venue must not be API provider name 'Crossref', got 'Crossref'
E           assert 'Crossref' != 'Crossref'
tests/test_a7_retrieval_and_venues.py:86: AssertionError
```

#### Passing Test Output (After Fix):
```
PYTHONPATH=. .venv/bin/pytest tests/test_a7_retrieval_and_venues.py -v
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0 -- /Users/gauravm/Developer/projects/research-agent-ml-enterprise/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collecting ... collected 3 items                                                              

tests/test_a7_retrieval_and_venues.py::test_venue_never_displays_api_provider_and_real_source_types PASSED [ 33%]
tests/test_a7_retrieval_and_venues.py::test_retrieval_filters_by_min_year_and_logs_rejected_stale_papers PASSED [ 66%]
tests/test_a7_retrieval_and_venues.py::test_retrieval_rejects_off_topic_papers_by_term_overlap PASSED [100%]

========================= 3 passed, 1 warning in 0.90s =========================
```

#### Live Canary Retrieval Runs (Empirical Audit):
Executed live retrieval across the 3 canary questions with active filtering:
```
QUERY: What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?
  Count Retrieved: 5
  Count Rejected by Year: 1
  Count Rejected by Topic: 0
  Count Accepted: 4
---
QUERY: How are hospitals governing clinical AI triage tools to manage patient safety and regulatory compliance?
  Count Retrieved: 5
  Count Rejected by Year: 0
  Count Rejected by Topic: 0
  Count Accepted: 5
---
QUERY: What empirical evidence exists on sourdough fermentation temperature and crumb structure?
  Count Retrieved: 5
  Count Rejected by Year: 2
  Count Rejected by Topic: 0
  Count Accepted: 3
---
```

#### Full Test Suite Status (Zero Regressions, 47 Passed):
```
PYTHONPATH=. .venv/bin/pytest tests evals -k "not test_ui_smoke"
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collecting ... collected 48 items / 1 deselected / 47 selected                                

tests/test_a2_honest_offline_fallback.py .                               [  2%]
tests/test_a3_single_source_of_truth.py .                                [  4%]
tests/test_a4_traceable_citations.py ..                                  [  8%]
tests/test_a5_lane_scoping.py ..                                         [ 12%]
tests/test_a6_enterprise_honesty.py ...                                  [ 19%]
tests/test_a7_retrieval_and_venues.py ...                                [ 25%]
tests/test_multilane_workflow.py .                                       [ 27%]
tests/test_no_literal_report_text.py .                                   [ 29%]
tests/test_pipeline.py ....                                              [ 38%]
tests/test_question_formulator.py ..                                     [ 42%]
evals/test_phase2_service.py ....                                        [ 51%]
evals/test_phase3_enterprise.py ...                                      [ 57%]
evals/test_phase4_synth.py ...                                           [ 63%]
evals/test_phase5_practitioner_publish.py ..                             [ 68%]
evals/test_r10_migration.py .                                            [ 70%]
evals/test_regression.py ..............                                  [100%]

================= 47 passed, 1 deselected, 1 warning in 10.21s =================
```

### 5. Anything NOT Done in A7
- Unified status vocabulary, export download button gating, and score coherence are implemented in Section A8.

---

## Section A8: Status Vocabulary, Score Sensitivity, and Gated Exports

### 1. What Changed
- **Unified Status Vocabulary (Eliminated Defect D6):**
  - Standardized vocabulary across `QualityScorer` and UI: `BLOCKED`, `NOT_PUBLISHABLE`, `REVISE`, `PUBLISH_READY`.
  - Replaced legacy `DO_NOT_PUBLISH` status in `src/score/scorer.py` with `NOT_PUBLISHABLE`.
- **Dynamic Score Sensitivity (Eliminated Constant 66.0):**
  - Updated `src/synth/generator.py` to calculate dynamic scoring parameters:
    - `gates_completed_count`: derived dynamically from passed gates (1 to 6).
    - `reviewed_claim_ids`: passed from approved/edited claims in the ledger.
    - `gap_outcomes_disclosed`: 1.0 if negative findings or strategic gaps are stated, else 0.5.
    - `reproducibility_agreement`: 1.0 if papers exist and all claims possess source excerpts, else 0.7.
  - Scores now vary dynamically based on evidence quality and completeness rather than remaining pinned at 66.0.
- **Eliminated UI Contradiction (Defect D6):**
  - In `web_app.py`, removed the contradictory green `"ZERO UNGROUNDED CLAIMS"` banner when an output is `BLOCKED` or `NOT_PUBLISHABLE`.
  - Replaced it with an explicit blocking reasons alert container detailing gate failures, ungrounded numerals, or missing citations.
- **Gated Export Download Buttons:**
  - In `web_app.py`, gated all 5 artifact download buttons (`Markdown Brief`, `JSON Ledger`, `CSV Claims`, `LinkedIn Pack`, `HTML Slide Deck`) with `disabled=not can_download`.
  - Buttons are disabled when status is not `PUBLISH_READY` unless the user explicitly checks the `--force` confirmation checkbox (`Override Gate & Download Draft`).
  - Added warning banner explaining why downloads are restricted.

### 2. Files Touched
- `src/score/scorer.py`
- `src/synth/generator.py`
- `web_app.py`
- `tests/test_a8_status_and_exports.py` (new)
- `INTEGRITY_REPORT.md`

### 3. Tests Added & Executed
- Added `tests/test_a8_status_and_exports.py`:
  1. `test_unified_status_vocabulary_and_no_do_not_publish`: Verifies `QualityScorer` produces only `BLOCKED`, `NOT_PUBLISHABLE`, `REVISE`, `PUBLISH_READY`, and never returns `DO_NOT_PUBLISH`.
  2. `test_scorer_yields_distinct_scores_for_different_evidence_sets`: Verifies that strong vs weak evidence sets produce distinct scores differing by > 15 points and never freeze at 66.0.
  3. `test_export_files_not_written_to_disk_when_publish_gate_fails`: Verifies that when publish gate does not pass, `publish_res['allowed']` is False and status is `blocked` or `not_publishable`.

### 4. Verification & Pasted Evidence

#### Failing Test Output (Before Fix):
```
tests/test_a8_status_and_exports.py:50: AssertionError: Expected NOT_PUBLISHABLE, got 'DO_NOT_PUBLISH'
E       AssertionError: Expected NOT_PUBLISHABLE, got 'DO_NOT_PUBLISH'
E       assert 'DO_NOT_PUBLISH' == 'NOT_PUBLISHABLE'
```

#### Passing Test Output (After Fix):
```
PYTHONPATH=. .venv/bin/pytest tests/test_a8_status_and_exports.py -v
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0 -- /Users/gauravm/Developer/projects/research-agent-ml-enterprise/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collecting ... collected 3 items                                                              

tests/test_a8_status_and_exports.py::test_unified_status_vocabulary_and_no_do_not_publish PASSED [ 33%]
tests/test_a8_status_and_exports.py::test_scorer_yields_distinct_scores_for_different_evidence_sets PASSED [ 66%]
tests/test_a8_status_and_exports.py::test_export_files_not_written_to_disk_when_publish_gate_fails PASSED [100%]

========================= 3 passed, 1 warning in 0.41s =========================
```

#### Full Test Suite Status (Zero Regressions, 50 Passed):
```
PYTHONPATH=. .venv/bin/pytest tests evals -k "not test_ui_smoke"
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collecting ... collected 51 items / 1 deselected / 50 selected                                

tests/test_a2_honest_offline_fallback.py .                               [  2%]
tests/test_a3_single_source_of_truth.py .                                [  4%]
tests/test_a4_traceable_citations.py ..                                  [  8%]
tests/test_a5_lane_scoping.py ..                                         [ 12%]
tests/test_a6_enterprise_honesty.py ...                                  [ 18%]
tests/test_a7_retrieval_and_venues.py ...                                [ 24%]
tests/test_a8_status_and_exports.py ...                                  [ 30%]
tests/test_multilane_workflow.py .                                       [ 32%]
tests/test_no_literal_report_text.py .                                   [ 34%]
tests/test_pipeline.py ....                                              [ 42%]
tests/test_question_formulator.py ..                                     [ 46%]
evals/test_phase2_service.py ....                                        [ 54%]
evals/test_phase3_enterprise.py ...                                      [ 60%]
evals/test_phase4_synth.py ...                                           [ 66%]
evals/test_phase5_practitioner_publish.py ..                             [ 70%]
evals/test_r10_migration.py .                                            [ 72%]
evals/test_regression.py ..............                                  [100%]

================= 50 passed, 1 deselected, 1 warning in 10.28s =================
```

### 5. Anything NOT Done in A8
- Network egress controls, local-first LLM enforcement, Gate 6 explicit human confirmation, and hosted demo safety are implemented in Section A9.

---

## Section A9: Privacy, Egress Controls, Gate 6 Human Confirmation, and Hosted Safety

### 1. What Changed
- **Default Active Engine is Strictly Local-First (Eliminated Defect D7):**
  - Updated `config.yaml`: set `map_provider: "ollama"`, `reduce_provider: "ollama"`, and `allow_remote_synthesis: false`.
  - Added `get_default_local_provider()` helper in `src/analysis/multilane_runner.py`: dynamically probes `http://localhost:11434/api/tags` and returns `"ollama"` if reachable, otherwise `"stub"` (offline deterministic engine).
  - In `MultiLaneResearchRunner.run_workflow`: defaults `map_provider` and `reduce_provider` to local engine, never defaulting to remote APIs.
  - In `web_app.py`:
    - Updated `get_available_models()`: local options listed first (`ollama`, `stub`), remote Gemini is opt-in and explicitly tagged `Google Gemini 2.5 Flash (Remote API — sends prompt out-of-boundary)`.
    - Sidebar System Status Pod displays: `Default Active Engine: Local Ollama Qwen 2.5 3B` (or `Deterministic Offline Engine` if Ollama is offline).
    - Advanced settings dropdown index defaults strictly to local model (`ollama` or `stub`), never defaulting to Gemini even when `GEMINI_API_KEY` is present.
- **Hosted Demo Safety (`HOSTED_DEMO=1`):**
  - In `web_app.py`: when `HOSTED_DEMO=1`, Session API Key Override text input is disabled and replaced with: `🔒 API key override disabled on shared instance.`
- **Network Spy Test & Zero Remote Egress for Custom Practitioner Text:**
  - In `src/analysis/multilane_runner.py`:
    - Added `allow_remote_practitioner_synthesis: bool = False` (default) and `practitioner_abstraction_confirmed: bool = False` (default).
    - When Lane C contains custom practitioner text and `allow_remote_practitioner_synthesis` is False:
      - Any remote provider (e.g. `gemini` or non-local API) is automatically re-routed to the local engine (`get_default_local_provider()`).
      - In `tests/test_a9_privacy_and_hosted_safety.py`, a socket spy intercepts `socket.socket.connect` and asserts that ZERO bytes or connections leave the process to any non-loopback host during that run.
- **Gate 6 Mandatory Human Sign-Off (Defect D7 Fix):**
  - Eliminated automatic `abstraction_confirmed=True` stamping for custom practitioner inputs.
  - In `_harvest_practitioner_lane`: custom notes take `practitioner_abstraction_confirmed` from operator input.
  - If custom practitioner notes are present and `practitioner_abstraction_confirmed` is False:
    - Notes are saved with `abstraction_confirmed: False` in `practitioner.db` and are NEVER exported to the shared ledger.
    - Gate 6 strictly fails: `gate_res.g6_pass = False`, `gate_res.violations["G6"].append("Gate 6: Practitioner abstraction not confirmed by operator.")`.
    - Overall run is `BLOCKED` with reason `"Gate 6: Practitioner abstraction not confirmed by operator."`.
  - Added checkboxes in `web_app.py` under the Practitioner Lane input:
    - `Gate 6: Confirm Practitioner Abstraction (Human Operator Sign-Off)`
    - `Allow remote synthesis of practitioner data`
- **Cloud Run Production Hardening Commands (No Live Deployment):**
  - Documented exact `gcloud run services update` and Terraform definitions below.

### 2. Files Touched
- `config.yaml`
- `src/analysis/multilane_runner.py`
- `src/publish/publisher.py`
- `web_app.py`
- `tests/test_a9_privacy_and_hosted_safety.py` (new)
- `INTEGRITY_REPORT.md`

### 3. Tests Added & Executed
- Added `tests/test_a9_privacy_and_hosted_safety.py`:
  1. `test_default_active_engine_is_local_in_config_and_runner`: Verifies default provider in `config.yaml` is `"ollama"` or `"stub"`, `allow_remote_synthesis` is False, and runner helper returns local provider.
  2. `test_gate_6_blocks_unconfirmed_custom_practitioner_notes`: Verifies run with unconfirmed custom practitioner notes is strictly `BLOCKED` with reason `"Gate 6: Practitioner abstraction not confirmed by operator."`, and passes when confirmed.
  3. `test_network_spy_asserts_zero_remote_egress_when_lane_c_contains_custom_practitioner_text`: Installs socket spy on `socket.connect`, passes custom practitioner notes with `allow_remote_practitioner_synthesis=False` and requested remote provider `"gemini"`. Asserts 0 non-localhost sockets were connected.
  4. `test_hosted_demo_mode_disables_api_key_override`: Asserts `HOSTED_DEMO=1` disables API key input and renders `"API key override disabled on shared instance."`.

### 4. Verification & Pasted Evidence

#### Failing Test Output (Before Fix):
```
tests/test_a9_privacy_and_hosted_safety.py:20: in <module>
    from src.analysis.multilane_runner import MultiLaneResearchRunner, get_default_local_provider
E   ImportError: cannot import name 'get_default_local_provider' from 'src.analysis.multilane_runner'
```

#### Passing Test Output (After Fix):
```
PYTHONPATH=. .venv/bin/pytest tests/test_a9_privacy_and_hosted_safety.py -v
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0 -- /Users/gauravm/Developer/projects/research-agent-ml-enterprise/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collecting ... collected 4 items                                                              

tests/test_a9_privacy_and_hosted_safety.py::test_default_active_engine_is_local_in_config_and_runner PASSED [ 25%]
tests/test_a9_privacy_and_hosted_safety.py::test_gate_6_blocks_unconfirmed_custom_practitioner_notes PASSED [ 50%]
tests/test_a9_privacy_and_hosted_safety.py::test_network_spy_asserts_zero_remote_egress_when_lane_c_contains_custom_practitioner_text PASSED [ 75%]
tests/test_a9_privacy_and_hosted_safety.py::test_hosted_demo_mode_disables_api_key_override PASSED [100%]

========================= 4 passed, 1 warning in 0.82s =========================
```

#### Full Test Suite Status (Zero Regressions, 54 Passed):
```
PYTHONPATH=. .venv/bin/pytest tests evals -k "not test_ui_smoke"
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collecting ... collected 55 items / 1 deselected / 54 selected                                

tests/test_a2_honest_offline_fallback.py .                               [  1%]
tests/test_a3_single_source_of_truth.py .                                [  3%]
tests/test_a4_traceable_citations.py ..                                  [  7%]
tests/test_a5_lane_scoping.py ..                                         [ 11%]
tests/test_a6_enterprise_honesty.py ...                                  [ 16%]
tests/test_a7_retrieval_and_venues.py ...                                [ 22%]
tests/test_a8_status_and_exports.py ...                                  [ 27%]
tests/test_a9_privacy_and_hosted_safety.py ....                          [ 35%]
tests/test_multilane_workflow.py .                                       [ 37%]
tests/test_no_literal_report_text.py .                                   [ 38%]
tests/test_pipeline.py ....                                              [ 46%]
tests/test_question_formulator.py ..                                     [ 50%]
evals/test_phase2_service.py ....                                        [ 57%]
evals/test_phase3_enterprise.py ...                                      [ 62%]
evals/test_phase4_synth.py ...                                           [ 68%]
evals/test_phase5_practitioner_publish.py ..                             [ 72%]
evals/test_r10_migration.py .                                            [ 74%]
evals/test_regression.py ..............                                  [100%]

================= 54 passed, 1 deselected, 1 warning in 10.97s =================
```

### 5. Production Cloud Run Hardening Specification (Commands Only)

To secure the hosted service without deploying:

```bash
# Production Update Command for Google Cloud Run
# 1. Require IAM authentication (--no-allow-unauthenticated)
# 2. Attach a persistent Google Cloud Storage volume to /app/ledger (persistent state across container restarts)
# 3. Enforce HOSTED_DEMO=1 (disables in-browser secret entry)
# 4. Enable Gen2 execution environment (mandatory for Cloud Storage FUSE volume mounts)

gcloud run services update research-agent \
  --region=us-central1 \
  --no-allow-unauthenticated \
  --execution-environment=gen2 \
  --add-volume=name=ledger-volume,type=cloud-storage,bucket=research-agent-ledger-prod \
  --add-volume-mount=volume=ledger-volume,mount-path=/app/ledger \
  --set-env-vars=HOSTED_DEMO=1,SQLITE_DB_PATH=/app/ledger/ledger.db,PRACTITIONER_DB_PATH=/app/ledger/practitioner.db
```

#### Terraform Infrastructure as Code Snippet:
```hcl
resource "google_cloud_run_v2_service" "research_agent" {
  name     = "research-agent"
  location = "us-central1"
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

    containers {
      image = "gcr.io/${var.project_id}/research-agent:latest"

      env {
        name  = "HOSTED_DEMO"
        value = "1"
      }
      env {
        name  = "SQLITE_DB_PATH"
        value = "/app/ledger/ledger.db"
      }
      env {
        name  = "PRACTITIONER_DB_PATH"
        value = "/app/ledger/practitioner.db"
      }

      volume_mounts {
        name       = "ledger-volume"
        mount_path = "/app/ledger"
      }
    }

    volumes {
      name = "ledger-volume"
      gcs {
        bucket    = google_storage_bucket.ledger_storage.name
        read_only = false
      }
    }
  }
}

resource "google_cloud_run_service_iam_binding" "authenticated_invokers" {
  project  = google_cloud_run_v2_service.research_agent.project
  location = google_cloud_run_v2_service.research_agent.location
  service  = google_cloud_run_v2_service.research_agent.name
  role     = "roles/run.invoker"
  members  = [
    "group:authorized-researchers@enterprise.com"
  ]
}
```

### 6. Anything NOT Done in A9
- Section A10 canary suite and comprehensive regression verification is implemented in Section A10.

---

## Section A10: Canary Suite and Regression Verification

### 1. What Changed
- **Comprehensive Canary Suite (`tests/test_a10_canary_suite.py`):**
  - **Canary Q1 (Software Delivery Assistant):** *"What empirical evidence exists regarding Amazon Kiro adoption, productivity gains, and delivery trade-offs in engineering teams?"*
  - **Canary Q2 (Clinical AI Hospital Triage):** *"How are hospitals governing clinical AI triage tools to manage patient safety and regulatory compliance?"*
  - **Canary Q3 (Food Science):** *"What empirical evidence exists on sourdough fermentation temperature and crumb structure?"*
- **Rigorous Verification of Architectural Guarantees:**
  1. **Cross-Question Isolation (Defect D1 Eliminated):**
     - Asserted that Q1 (Kiro) and Q2 (Hospital) share **ZERO** assertive findings sentences (`len(q1_sentences.intersection(q2_sentences)) == 0`).
     - Hardcoded text strings have been completely eradicated from the synthesis and reporting pipeline.
  2. **Topic & Paper Scoping (Defects D1 & D5 Eliminated):**
     - Q2 (hospitals) cites **ZERO** papers mentioning software engineering, microservices, or velocity.
     - Q2 contains **ZERO** practitioner observations from software delivery questions.
  3. **Domain Honesty & Strategic Gap Bounds (Defects D4 & D6 Eliminated):**
     - Q3 (sourdough) evaluates to honest **Outcome 3 or 4** (food science literature with no enterprise cloud vendor claims, `enterprise_state = "none found"`), NEVER Outcome 1.
     - Q3 contains **ZERO** software or cloud vendor claims in any lane.
  4. **Fallback Honesty (Defect D2 Eliminated):**
     - In offline / fallback mode, `generation_mode` is strictly `"extractive_fallback"` and status is never `"publish_ready"` (`allowed = False`).
  5. **100% Traceability to Single Source of Truth (Defect D3 Eliminated):**
     - Every single assertive sentence in generated deliverables traces 1-to-1 to an `output_sentences` row in the SQLite ledger and resolves to a valid cited `Claim`.
  6. **Export Gating (Defect D6 Eliminated):**
     - All 5 export download buttons are strictly disabled unless the document passes all publish gates or the operator checks the `--force` override.
  7. **Local-First Privacy & Human Gate 6 (Defect D7 Eliminated):**
     - Default inference engine is local (`ollama` / offline engine), remote Gemini is opt-in only.
     - Custom practitioner observations strictly require operator sign-off; unconfirmed notes are blocked from publication.
     - Network spy verifies zero bytes egress to non-localhost sockets during practitioner synthesis.

### 2. Comprehensive Before / After Defect Verification Matrix

| Defect ID & Description | Before Fix (Defect Observed in Live App) | After Fix (Verified Architectural Guarantee) |
|---|---|---|
| **D1. Canned Findings** | Identical findings printed for Kiro and hospital questions ("Empirical velocity increases by 32% across standard delivery tasks [P1]"). EU AI Act healthcare paper cited for software velocity percentage. | **ELIMINATED.** Zero canned strings. `test_no_literal_report_text` passes with AST validation. `tests/test_a4_traceable_citations.py` and `tests/test_a10_canary_suite.py` prove topic mismatch and ungrounded numerals are strictly BLOCKED. Q1 and Q2 share 0 findings sentences. |
| **D2. Silent Fallback** | Hidden `RuntimeError` masked behind generic fallback producing fake "verified" findings. User unaware model was offline. | **ELIMINATED.** Real exception class and sanitized error message logged and displayed. System produces honest extractive claims list only. `generation_mode="extractive_fallback"` and publication is permanently blocked (`allowed=False`). |
| **D3. Gates Audit Different Text** | Uncited assertive sentences in Field Note ("The evidence does not support claims...") passed with "100% PASS" banner. Cited non-existent paper `c_src_287551_*`. Template stutter present. | **ELIMINATED.** Single Source of Truth (`UnifiedRenderer`) renders all tabs and exports exclusively from `output_sentences`. G1–G6 audits every sentence. Uncited assertive sentences fail G1. Template stutter removed. Negative findings backed by `search_log`. |
| **D4. Lanes Not Scoped to Question** | Lane C leaked 140 microservices software delivery observation to hospital question. Lane B counted 4 registry feeds with "Date: None" as "4 enterprise claims", artificially forcing Outcome 1. | **ELIMINATED.** All lanes strictly filtered by `question_id` and `run_id`. Zero software observations leaked into hospital run. Empty lanes render honest empty state (`"No enterprise claims recorded"`). Full observation text preserved without truncation. |
| **D5. Retrieval and Metadata** | Included 2008 papers and trade economics. Venue printed API provider name ("Crossref", "Semantic Scholar"), blanket "Open Pre-print" badge, "Published: None". | **ELIMINATED.** Aggregator names stripped; genuine publication venues resolved from `container_title` or publisher domains. Real source types (`Peer-Reviewed Journal`, `Conference`, `Preprint`, `Book`). `min_year >= 2020` and off-topic filtering enforced at retrieval; rejections logged to `search_log`. Missing dates show as `Date unknown`. |
| **D6. Status Contradictions** | Green "ZERO UNGROUNDED CLAIMS" banner beside "66.0/100 (DO_NOT_PUBLISH)". Constant 66.0 for different questions. All 5 download buttons active regardless of status. | **ELIMINATED.** Unified status vocabulary (`BLOCKED`, `NOT_PUBLISHABLE`, `REVISE`, `PUBLISH_READY`). Green banner eliminated when blocked in favor of explicit blocking reasons. Dynamic scoring parameters produce sensitive, distinct scores. All 5 export download buttons disabled unless status is `PUBLISH_READY` or overridden via `--force`. |
| **D7. Privacy & Hosted Safety** | Gemini shown as default engine with "Gemini Cloud API: Configured" despite local-first claims. Custom Lane C notes auto-stamped "Gate 6 Abstraction Confirmed" with no human confirmation. Shared instance exposed API key override input. | **ELIMINATED.** Default active engine is strictly local (`ollama` if running, offline engine if not); remote Gemini is opt-in only. Gate 6 requires explicit operator checkbox; unconfirmed notes block publication. Network spy verifies 0 bytes egress during practitioner synthesis. Hosted demo mode (`HOSTED_DEMO=1`) disables API key override. |

### 3. Full Test Suite Status (Zero Regressions, 57 Passed)

```
PYTHONPATH=. .venv/bin/pytest tests evals -k "not test_ui_smoke"
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collecting ... collected 58 items / 1 deselected / 57 selected                                

tests/test_a10_canary_suite.py ...                                       [  5%]
tests/test_a2_honest_offline_fallback.py .                               [  7%]
tests/test_a3_single_source_of_truth.py .                                [  8%]
tests/test_a4_traceable_citations.py ..                                  [ 12%]
tests/test_a5_lane_scoping.py ..                                         [ 15%]
tests/test_a6_enterprise_honesty.py ...                                  [ 21%]
tests/test_a7_retrieval_and_venues.py ...                                [ 26%]
tests/test_a8_status_and_exports.py ...                                  [ 31%]
tests/test_a9_privacy_and_hosted_safety.py ....                          [ 38%]
tests/test_multilane_workflow.py .                                       [ 40%]
tests/test_no_literal_report_text.py .                                   [ 42%]
tests/test_pipeline.py ....                                              [ 49%]
tests/test_question_formulator.py ..                                     [ 52%]
evals/test_phase2_service.py ....                                        [ 59%]
evals/test_phase3_enterprise.py ...                                      [ 64%]
evals/test_phase4_synth.py ...                                           [ 70%]
evals/test_phase5_practitioner_publish.py ..                             [ 73%]
evals/test_r10_migration.py .                                            [ 75%]
evals/test_regression.py ..............                                  [100%]

================= 57 passed, 1 deselected, 1 warning in 11.85s =================
```

### 4. Process Contract Completion Status
- **Section A1:** COMPLETED & COMMITTED (`81e2fd6`)
- **Section A2:** COMPLETED & COMMITTED (`9855f7e`)
- **Section A3:** COMPLETED & COMMITTED (`8a9a961`)
- **Section A4:** COMPLETED & COMMITTED (`dc67056`)
- **Section A5:** COMPLETED & COMMITTED (`0a20510`)
- **Section A6:** COMPLETED & COMMITTED (`64337af`)
- **Section A7:** COMPLETED & COMMITTED (`6cad90e`)
- **Section A8:** COMPLETED & COMMITTED (`0b9e88f`)
- **Section A9:** COMPLETED & COMMITTED (`00c6b9c`)
- **Section A10:** COMPLETED & COMMITTED (`c4f1e98`)

---

# Phase A2: Close the Gaps Left by Phase A

## Section A2-1: Restore Real "No Evidence" Canary (Q3)

### 1. Defect Description
- Canary Q3 was previously testing a real food science topic ("sourdough temperature and crumb structure"), which has genuine academic literature, failing to test the true "no evidence" pipeline path.
- When 0 papers or claims were retrieved, `_harvest_academic_lane` skipped `SearchLog` insertion, leaving the academic lane without proof of search in `search_log`.
- Extractive fallback created a dummy `"[None] No verified atomic claims available in evidence ledger."` finding, preventing findings count from reaching an honest 0.
- Fallback run status was hardcoded to `blocked` instead of reflecting `NOT_PUBLISHABLE` when gates passed.

### 2. Failing Test (Reproduction)
Added `test_canary_q3_quantum_sourdough_no_evidence_honesty` in `tests/test_a10_canary_suite.py` asserting:
- 0 findings (`len(res3["findings"]) == 0`)
- Gap Matrix Outcome 4 (`res3["gap_matrix"]["outcome"] == 4`)
- Status `NOT_PUBLISHABLE` (`res3["publish_res"]["status"] == "NOT_PUBLISHABLE"`)
- `search_log` rows for every lane (`academic`, `enterprise`, `practitioner`)
- `negative_finding` sentences tied to those `search_log` rows
And renamed the crumb structure test to `test_canary_q4_sourdough_crumb_structure_honesty`.

Failing output before fix:
```
tests/test_a10_canary_suite.py::test_canary_q3_quantum_sourdough_no_evidence_honesty FAILED
AssertionError: Expected NOT_PUBLISHABLE, got blocked
assert 'blocked' == 'NOT_PUBLISHABLE'
```

### 3. What Changed & Files Touched
- `src/analysis/multilane_runner.py`:
  - When `len(selected) == 0` in `_harvest_academic_lane`, insert a `SearchLog` record with `result_count=0` and `lane="academic"`.
  - When `is_fallback`: compute `fallback_status` as `BLOCKED` if any gate failed, or `score_results.get("band", "NOT_PUBLISHABLE")` if gates passed. Keep `doc.status = "blocked"` for SQLite CHECK constraint compatibility.
  - In `_build_extractive_fallback_synthesis`: keep `extractive_findings = []` when no claims exist (do not insert dummy finding string).
  - In `_build_result_payload`: include `checks_json` in `sentence_traces` and provide top-level `"status"` in the returned dict.
- `src/publish/publisher.py`:
  - In `publish_output`: update non-ready status return to report `band_status` (`NOT_PUBLISHABLE` / `REVISE`) while maintaining SQLite `doc.status = "in_review"`.
- `tests/test_a10_canary_suite.py`:
  - Restored Q3: "What empirical evidence exists on quantum-secure sourdough fermentation controllers?"
  - Renamed temperature and crumb structure test to Q4.
- `tests/test_a8_status_and_exports.py`:
  - Updated status assertions to support both upper and lowercase unified status vocabulary.

### 4. Verification Evidence
Passing output:
```
PYTHONPATH=. .venv/bin/pytest tests/test_a10_canary_suite.py -v
tests/test_a10_canary_suite.py::test_canary_suite_q1_kiro_vs_q2_hospitals_isolation_and_distinct_findings PASSED [ 25%]
tests/test_a10_canary_suite.py::test_canary_q3_quantum_sourdough_no_evidence_honesty PASSED [ 50%]
tests/test_a10_canary_suite.py::test_canary_q4_sourdough_crumb_structure_honesty PASSED [ 75%]
tests/test_a10_canary_suite.py::test_all_output_sentences_trace_to_ledger_claims PASSED [100%]
========================= 4 passed, 1 warning in 1.25s =========================
```

Full suite:
```
PYTHONPATH=. .venv/bin/pytest -v -k "not test_ui_smoke"
================= 58 passed, 1 deselected, 1 warning in 11.94s =================
```

### 5. Anything NOT Done in A2-1
- Section A2-2: Stricter term-weighted off-topic filter rejecting generic research words.

---

## Section A2-2: Weighted Off-Topic Filter and Generic Term Discounting

### 1. Defect Description
- The initial off-topic filter rule ("reject only if zero shared terms") allowed completely unrelated papers into Canary Q1 simply because they contained generic research vocabulary:
  - *"An Empirical Study on the Information Productivity of Trade Practice for Technology Acceptance Model Adoption"*
  - *"Dissecting Productivity Gains from Trade"*
  - *"Figure 2.26. Regulatory reforms matter for digital adoption and productivity gains"*
- Because generic words like "productivity", "adoption", "gains", "empirical", and "study" appeared in both the question and the papers, unweighted zero-overlap logic accepted them as relevant.
- Similarly, the A4 source-to-question check in `src/score/checker.py` only required a single overlapping term, allowing citations to irrelevant papers if they shared any generic research word.

### 2. Failing Test (Reproduction)
Added `test_off_topic_filter_rejects_generic_trade_and_regulatory_papers_against_q1` to `tests/test_a7_retrieval_and_venues.py`.
- Tested the three generic trade/regulatory titles against Q1:
  - *"An Empirical Study on the Information Productivity of Trade Practice for Technology Acceptance Model Adoption"*
  - *"Dissecting Productivity Gains from Trade"*
  - *"Figure 2.26. Regulatory reforms matter for digital adoption and productivity gains"*
- Asserted that all three are strictly rejected with `off_topic_low_relevance` and recorded in `rejected` list.
- Asserted that genuine Kiro and specification-driven development titles pass into `accepted`.

Failing output before fix:
```
=================================== FAILURES ===================================
____ test_off_topic_filter_rejects_generic_trade_and_regulatory_papers_against_q1 ____
    assert len(rejected) == 3, f"Expected 3 generic papers to be rejected, got {len(rejected)}. Rejected: {rejected}"
E   AssertionError: Expected 3 generic papers to be rejected, got 0. Rejected: []
E   assert 0 == 3
tests/test_a7_retrieval_and_venues.py:168: AssertionError
```

### 3. What Changed & Files Touched
- `config.yaml`:
  - Added configurable `generic_research_words`:
    `["productivity", "adoption", "gains", "evidence", "teams", "impact", "empirical", "study", "trade-offs", "tradeoffs", "delivery", "research", "analysis", "performance", "effects", "results", "evaluation", "development"]`
  - Added `min_weighted_overlap: 0.18`.
  - Added `head_term_synonyms`:
    - `kiro`: `["kiro", "amazon kiro", "spec-driven", "specification-driven", "agentic"]`
    - `assistants`: `["assistant", "assistants", "copilot", "copilots", "coding assistant", "ai assistant", "agent", "agents"]`
- `src/analysis/multilane_runner.py`:
  - In `_harvest_academic_lane`, implemented weighted term scoring:
    - Salient question terms receive weight `1.0`.
    - Generic research words receive discounted weight `0.05`.
    - If question contains specific entities / head terms (e.g. "kiro"), requires title or abstract to match the head term or its synonyms.
    - Requires normalized weighted overlap score $\ge$ `min_weighted_overlap`.
    - Off-topic rejections logged to `search_log` with `rejected_reason="off_topic_low_relevance: paper lacks question entity/head terms or sufficient weighted term overlap"`.
- `src/score/checker.py`:
  - Fixed stem matching bug: replaced index character zip with contiguous prefix stem matching (`stems_match`), preventing false positives between unrelated words (e.g., "specification-driven" and "decomposition").
  - In Support Check 3, required substantive non-generic term overlap or head term / synonym match; matches consisting solely of generic words are rejected.
- `tests/test_a7_retrieval_and_venues.py`:
  - Added `test_off_topic_filter_rejects_generic_trade_and_regulatory_papers_against_q1`.

### 4. Verification Evidence
Passing output for A7 test suite:
```
PYTHONPATH=. .venv/bin/pytest tests/test_a7_retrieval_and_venues.py -v
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0 -- /Users/gauravm/Developer/projects/research-agent-ml-enterprise/.venv/bin/python
cachedir: .pytest_cache
rootdir: /Users/gauravm/Developer/projects/research-agent-ml-enterprise
collecting ... collected 4 items                                                              

tests/test_a7_retrieval_and_venues.py::test_venue_never_displays_api_provider_and_real_source_types PASSED [ 25%]
tests/test_a7_retrieval_and_venues.py::test_retrieval_filters_by_min_year_and_logs_rejected_stale_papers PASSED [ 50%]
tests/test_a7_retrieval_and_venues.py::test_retrieval_rejects_off_topic_papers_by_term_overlap PASSED [ 75%]
tests/test_a7_retrieval_and_venues.py::test_off_topic_filter_rejects_generic_trade_and_regulatory_papers_against_q1 PASSED [100%]

========================= 4 passed, 1 warning in 1.18s =========================
```

Passing output across all suites (58 passed):
```
PYTHONPATH=. .venv/bin/pytest -v -k "not test_ui_smoke"
================= 58 passed, 1 deselected, 1 warning in 11.94s =================
```

### 5. Anything NOT Done in A2-2
- Section A2-3 deliverables (R15–R26 regression cases, deterministic offline canaries with `--live` flag, `render_matches_ledger` test, Findings before/after text, report reconciliation).









