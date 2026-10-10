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
