# Research Engine v2 — Architectural Decisions & Deviations Log (`DECISIONS.md`)

This log records all design choices, trade-offs, and deviations where prompt assumptions or naming conventions were adapted to match the existing repository conventions, in accordance with Section 1 of the v2 prompt (*"The repo is the source of truth, not this document"*).

---

## Decision Index

| ID | Date | Category | Decision Summary | Status |
|---|---|---|---|---|
| DEC-001 | 2026-10-10 | Architecture | Module namespace preservation under `src/` | Approved |
| DEC-002 | 2026-10-10 | Frontend | Streamlit in-process service binding on `127.0.0.1` | Approved |
| DEC-003 | 2026-10-10 | Fetchers | Retain and extend OpenAlex as primary academic source | Approved |
| DEC-004 | 2026-10-10 | Privacy & LLM | Local-first Ollama default; remote synthesis gated OFF | Approved |
| DEC-005 | 2026-10-10 | Durability | Forward-only migrations, WAL mode & timestamped backups | Approved |
| DEC-006 | 2026-10-10 | Governance | Legacy output isolation (`legacy-ungraded`) | Approved |

---

### DEC-001: Module Namespace Preservation under `src/`
- **Context:** The v2 prompt target architecture suggests placing folders at the repository root (`extract/`, `ledger/`, `grade/`, `gaps/`, `synth/`, `score/`, `publish/`).
- **Repo Convention:** The repository organizes all engine logic under the `src/` Python package (`src/analysis/`, `src/fetchers/`, `src/llm/`, `src/output/`, `src/publishing/`).
- **Decision:** Place new v2 engine modules under `src/` (e.g. `src/ledger/`, `src/extract/`, `src/grade/`, `src/gaps/`, `src/synth/`, `src/score/`), while keeping `questions/` (YAML register) and `evals/` (regression fixtures) at the root level.
- **Rationale:** Prevents polluting the root namespace, keeps `PYTHONPATH=.` package imports clean, and guarantees backward compatibility with existing CLI commands and test suites.

---

### DEC-002: Streamlit Local Service Binding on `127.0.0.1`
- **Context:** The v2 prompt suggests adding a minimal local-only API bound to `127.0.0.1` if the frontend has no API.
- **Repo Convention:** The existing frontend is a native Streamlit application (`web_app.py`) running in a local Python process. Streamlit interacts with Python libraries directly in memory without requiring an HTTP proxy layer.
- **Decision:** Implement a clean, decoupled service layer (`src/ledger/service.py`) that encapsulates all SQLite reads, writes, reviews, and gate checks. The Streamlit application will call this service directly on `127.0.0.1`. Every user review action writes an immutable, append-only row to the `reviews` audit table.
- **Rationale:** Avoids adding a separate web framework (e.g. FastAPI/Uvicorn), which would add port management overhead, inter-process communication latency, and serialization vulnerabilities, while achieving 100% of the human review gate requirements.

---

### DEC-003: Retaining and Extending OpenAlex as Primary Academic Source
- **Context:** The v2 prompt mentions arXiv, Semantic Scholar, and Crossref as initial academic APIs.
- **Repo Convention:** OpenAlex was integrated during recent runs and proved to be the most reliable source (250M+ open-access papers, no IP rate-limiting blocks, returned 7 of the 8 papers in the Kiro benchmark).
- **Decision:** Keep `OpenAlexClient` alongside `ArxivClient`, `CrossrefClient`, and `SemanticScholarClient`. Extend all four clients with `extraction_depth` (abstract_only vs full_text), `venue_tier` resolution, and study-type tagging.
- **Rationale:** Relying solely on Semantic Scholar (which throttles unauthenticated requests with HTTP 429) or arXiv (which has a 3-second delay and predominantly preprints) would cripple retrieval speed and coverage. OpenAlex provides fast, authoritative peer-reviewed metadata.

---

### DEC-004: Local-First Ollama Default with Gated Remote Synthesis
- **Context:** Hard Constraint 1 mandates local-first execution. Ollama must handle extraction and triage. A remote model may be used ONLY for public synthesis, behind a config flag that defaults OFF.
- **Repo State:** The previous session set `map_provider: "gemini"` in `config.yaml` when local Ollama was paused.
- **Decision:** Revert `config.yaml` defaults:
  - `llm.map_provider: "ollama"`
  - `llm.allow_remote_synthesis: false`
  - Extraction runs strictly through local models. Remote models are strictly forbidden from receiving any claim originating from the practitioner lane (`practitioner.db`).
- **Rationale:** Guarantees zero cost, total data sovereignty, and prevents confidential operational facts from leaving the machine.

---

### DEC-005: SQLite Durability Protocol (Day One)
- **Context:** Hard Constraint 5 requires `schema_version`, forward-only migrations, WAL mode, automatic timestamped backups before migrations and bulk writes, and an old-version DB migration test.
- **Decision:** Implement `src/ledger/migrations.py` with:
  1. `PRAGMA journal_mode=WAL;` and `PRAGMA foreign_keys=ON;` on every connection.
  2. Sequential migration scripts (`001_initial_schema.sql`, `002_...`).
  3. Pre-migration backup handler creating timestamped copies in `ledger/backups/ledger_backup_YYYYMMDD_HHMMSS.db` (retaining last 10 backups).
  4. Automatic integrity check (`PRAGMA integrity_check;`) run on engine startup.
  5. Dedicated test case verifying migration of populated older database versions without data loss.
- **Rationale:** Protects historical evidence, prevents corruption from concurrent reads/writes, and ensures painless schema evolution.

---

### DEC-006: Isolation of Legacy Ungraded Artifacts
- **Context:** Hard Constraint 6 states that old outputs must be marked `legacy-ungraded` and can never be published.
- **Decision:** Tag all pre-v2 outputs (such as `outputs/reports/*.md`, `outputs/reports/*.html`) with metadata header `status: legacy-ungraded`. Enforce in the Publish Gate (Gate 6) that any output with `status: legacy-ungraded` or missing Gate 1–5 sign-offs is strictly blocked from publication or website export.
- **Rationale:** Protects author credibility by ensuring that unverified, hallucinated, or un-graded v1 outputs cannot inadvertently be exported or published.

---

### DEC-007: Term Integrity Verification and Normalization (R13)
- **Context:** Previous v1 runs produced corrupted terms of art (e.g., "vibrate coding" instead of "vibe coding").
- **Decision:** Implement `src/extract/term_normalizer.py` verifying that key technical domain terms appear in the source excerpt before accepting a claim. Any corrupted variation lowers extraction confidence to 0.50 and flags the claim for human review at Gate 3.
- **Rationale:** Prevents corrupted or hallucinated terminology from entering the evidence ledger.

---

### DEC-008: Deterministic Venue Tiering and Unverified Venue Cap (R4)
- **Context:** V1 outputs mixed high-rigour venues (ACM, IEEE) with unverified or predatory journals (WJARR, IJSR, EAJIT, ISJEM) without distinction.
- **Decision:** Implement substring-matched venue tiers in `grade/venue_tiers.yaml`. Any venue not explicitly verified or recognised as a reputable preprint defaults to `unverified`. Claims from unverified venues are strictly capped at `weak`.
- **Rationale:** Prevents weak, unrefereed publications from masquerading as authoritative empirical evidence.

---

### DEC-009: Strict Entity Fidelity and Grounded Numerics (R1, R2, G2, G3)
- **Context:** V1 brief cited a generic 2023 paper on AI assistants to claim "up to 35%" productivity for Amazon Kiro, presenting an evidence gap as an answer.
- **Decision:** Claims are tagged with `entity_match` (`exact`, `family`, `topic_level`, `mismatch`). Only sources explicitly evaluating the target entity qualify for `exact`. At Gate 3 / Gate 5, any assertive sentence naming an entity while citing non-exact claims fails Gate G3. All numerals must be present in cited claims or tagged `[DERIVED]` to satisfy G2.
- **Rationale:** Guarantees that evidence gaps remain visible and prevents misleading attributions.

---

### DEC-010: Local Human Gates Architecture and Audit Protocol (Views 1, 2, 3)
- **Context:** Hard Constraint 1 and Section 9 mandate local-first operation, human-in-the-loop gates (Gate 1 Question Register, Gate 2 Venue Tiering, Gate 3 Claim Review Queue), and an append-only audit trail in `reviews`.
- **Decision:** Implemented `src/ledger/service.py` and `src/ledger/ui_views.py` integrated into `web_app.py`. Enforces:
  1. Queue sorting by uncertainty (low extraction confidence <0.80, corrupted term warnings, grade boundaries).
  2. Mandatory reviewer rationale for rejections, grade overrides, and entity match changes.
  3. Strict bulk-approval validation requiring identical source, grade, and study type across the batch.
  4. 100% of human review actions generate immutable audit rows in `reviews`.
- **Rationale:** Provides high usability for the human reviewer while maintaining an uncompromised audit trail for every strategic claim in the knowledge base.

---

| DEC-011 | 2026-10-10 | Architecture | Enterprise Lane Registry, Stake Tagging, & Search Log | Approved |
| DEC-012 | 2026-10-10 | Synthesis | Gap Matrix, Strength-Capped Synthesis, & S1-S7 Scorer | Approved |
| DEC-013 | 2026-10-10 | Governance | Practitioner Isolation, Abstraction Gate, & JSON Export | Approved |

---

### DEC-011: Enterprise Lane Registry, Stake Tagging, and Search Log Protocol (Phase 3)
- **Context:** Section 6 mandates a curated `sources_registry.yaml` of five verified enterprise sources, speaker/stake tagging on all claims, and immutable `search_log` logging to prove "searched, nothing found".
- **Decision:** Implemented `collectors/enterprise/sources_registry.yaml` with AWS Dev Blog, Microsoft Engineering Blog, Google Cloud Blog, SEC EDGAR filings (requiring declared User-Agent), and DORA Developer Survey. In `EnterpriseCollector`, every query writes to `search_log` with result counts. Commercial stake maps strictly to schema (`vendor`, `none`, `sponsored`, `unknown`) and speaker persona is recorded in claim context. Vendor assertions default to `vendor_claim`.
- **Honesty Correction (Prompt A3-1):** Correcting the historical record: Phase 3 ("Enterprise Lane, 5 curated sources, Accepted") delivered the source registry, terms verification, and search logging infrastructure, but did *not* deliver working automated fetchers for those 5 sources. Queries executed in Phase 3 without feed overrides returned an empty item list without making real HTTP requests. Under A3-1, sources without live fetchers log `status="not_implemented"`, and real RSS/Atom, SEC EDGAR, and curated vendor fetchers are delivered in A3-2.
- **Rationale:** Ensures enterprise evidence is transparently differentiated between vendor marketing, regulatory disclosures, and independent surveys without Web scraping paywalls.

---

### DEC-012: Gap Matrix, Strength-Capped Synthesis, and S1–S7 Scorer (Phase 4)
- **Context:** Section 8 and 10 mandate a cross-lane Gap Matrix (Outcomes 1 to 4 across Academic, Enterprise, Field lanes), sentence-level traceable synthesis reading ledger claims only, strength verbs capped by `synth/strength_verbs.yaml`, linting against raw topic interpolation/boilerplate (R14), and an S1–S7 quality scorer with publication bands.
- **Decision:**
  1. Implemented `GapMatrixBuilder` (`src/gaps/matrix_builder.py`) evaluating lane states (`supported`, `partial`, `none found`, `contradicted`) and assigning strategic Outcomes 1 to 4. "None found" is validated against `search_log`.
  2. Implemented `SynthesisEngine` (`src/synth/generator.py`) generating structured Field Notes. Every assertive sentence is bound to eligible claims with strength verbs capped by claim grades. Human opinion is isolated into `type="opinion"` and never generated by the engine.
  3. Implemented `lint_output_text` catching raw topic string interpolation and repeated boilerplate sentences (R14).
  4. Wired Streamlit Views 4 (Gap Matrix), 5 (Draft Review), 6 (Publish Gate), and 8 (Runs & Audit Trail) into `web_app.py`.
- **Rationale:** Eliminates hallucinated assertions and invented acronyms while giving executive readers transparent visibility into literature voids.

---

### DEC-013: Practitioner Lane Isolation, Abstraction Gate, and Website JSON Export (Phase 5)
- **Context:** Section 2 (Hard Constraints), Section 6.C, Section 9 (View 7), and Section 10 mandate that confidential practitioner data live strictly in an isolated SQLite database (`practitioner.db`, gitignored), never reach any remote model, and be strictly blocked from export or publication unless verified through confirmed abstraction and clean denylist scanning.
- **Decision:**
  1. Implemented `PractitionerCollector` (`src/collectors/practitioner/collector.py`) operating strictly on `ledger/practitioner.db` with identical durable migrations and WAL mode. Observations default to `anecdote` grade.
  2. Implemented Gate 6 Abstraction Protocol: `export_abstracted_claim_to_ledger` and `Publisher.publish_output` strictly block promotion or publication if `abstraction_confirmed` is False (R12).
  3. Implemented automated scanner for `denylist.txt` (client, vendor, programme, and person names) blocking any output containing confidential terms (R5).
  4. Implemented `Publisher` (`src/publish/publisher.py`) generating versioned website JSON exports (`outputs/json/publish_export_{output_id}.json` and `field_note_export.json`) upon 100% hard gate passage and human review sign-off.
  5. Wired Streamlit View 7 (Practitioner Field Notes Entry) and enhanced View 6 (Publish Gate) in `web_app.py`.
- **Rationale:** Guarantees absolute data sovereignty and client confidentiality for senior delivery leadership while allowing sanitized operational experience to enrich published thought leadership.



