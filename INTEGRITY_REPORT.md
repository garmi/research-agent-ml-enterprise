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




