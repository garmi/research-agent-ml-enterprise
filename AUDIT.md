# Research Engine v2 — Comprehensive Codebase Audit (Phase 0)

**Date:** 2026-10-10  
**Branch:** `v2-phase-0`  
**Auditor:** Antigravity Coding Agent  
**Status:** Complete — No behaviour changes introduced in this phase.

---

## 1. Executive Summary

This audit establishes the baseline for **Research Engine v2**. The existing v1 engine is a functional map-reduce pipeline that searches public literature APIs, extracts findings via an LLM, and generates markdown reports, JSON graphs, and static HTML deliverables.

However, forensic inspection of recent runs (particularly on "how Kiro is being used for development by engineering teams") confirms the critical issues identified in the v2 specification:
1. **Evidence Gaps Disguised as Assertions:** A generic 2023 paper on AI assistants was cited for a Kiro-specific productivity figure ("25-35%"), even though only 1 of the 8 papers retrieved was actually about Amazon Kiro.
2. **Ungraded Venue Conflation:** High-rigour peer-reviewed venues and unverified vanity journals/preprints were treated with equal weight.
3. **Phonetic/Semantic Term Corruption:** The term "vibe coding" was corrupted into "vibrate coding" in the output (`outputs/reports/how_kiro_is_being_used_for_development_b.md:51`) due to ungrounded LLM token generation.
4. **Invented Branding & Uncited Metrics:** A secondary sample report (`outputs/reports/gemini-research.html`) presented headline numbers ("20x", "67%", "90%") with zero citations, decorative stock Unsplash photography, and fabricated framework acronyms ("APEXA", "ARDDSF").
5. **No Sentence-Level Traceability or Human Verification:** Outputs were published directly to disk without human gating, atomic claim logging, or provenance verification.

v2 will solve these deficiencies without rebuilding working fetchers, CLI entry points, or the local UI.

---

## 2. Current Architecture & Entry Points

### 2.1 File & Directory Layout
```
research-agent-ml-enterprise/
├── ARCHITECTURE.md                  # V1 high-level design doc (partially stale)
├── README.md                        # V1 setup instructions (stale API list)
├── SETUP.md                         # Mac-specific setup notes
├── check_setup.sh                   # Environment validation script
├── config.yaml                      # Central runtime configuration
├── requirements.txt                 # Python dependencies
├── run.py                           # CLI shortcut wrapper calling src.app.main()
├── run.sh                           # Bash entry point (supports CLI and --ui)
├── web_app.py                       # Streamlit web dashboard
├── src/
│   ├── app.py                       # CLI driver & query orchestrator
│   ├── config.py                    # YAML loader & directory initialiser
│   ├── schemas.py                   # Pydantic models for PaperSummary & Synthesis
│   ├── analysis/
│   │   ├── business_context.py      # Focus-area regex matcher
│   │   ├── insight_builder.py       # Heuristic stats & finding summariser
│   │   ├── relevance.py             # Keyword token scoring & ranking
│   │   └── synthesizer.py           # Map-reduce LLM orchestration & citation validator
│   ├── fetchers/
│   │   ├── arxiv_client.py          # arXiv Atom API client
│   │   ├── crossref_client.py       # Crossref REST API client
│   │   ├── openalex_client.py       # OpenAlex REST API client
│   │   └── semantic_scholar_client.py # Semantic Scholar Graph API client
│   ├── llm/
│   │   ├── factory.py               # LLM provider builder (gemini vs ollama)
│   │   ├── gemini_client.py         # Google Gemini v1beta API client
│   │   └── ollama_client.py         # Local Ollama client (HTTP /api/generate)
│   ├── output/
│   │   ├── content_pack.py          # Legacy content pack generator
│   │   ├── html_storyline_builder.py# Dark-mode HTML report builder
│   │   ├── linkedin_pack_builder.py # Modular LinkedIn post pack builder
│   │   └── report_builder.py        # Markdown, HTML, JSON, and CSV file writer
│   ├── prompts/
│   │   └── research_prompts.py      # Map & reduce prompt templates (staged reduce)
│   └── publishing/                  # Personal-brand site builder & CLI
│       ├── __main__.py              # CLI for site (build, serve, publish)
│       ├── builder.py               # Jinja2 static site builder
│       └── publisher.py             # Transforms research_report.json to insight records
├── templates/                       # Legacy output format templates
├── tests/
│   └── test_pipeline.py             # 4 unit tests (dedupe, pipeline smoke, queries, OpenAlex)
├── outputs/                         # Default artifact landing directory
│   ├── csv/paper_index.csv          # 4-column literature index
│   ├── json/research_report.json    # Full synthesis data graph
│   └── reports/                     # Generated markdown and HTML briefs
└── website/                         # Static personal brand site templates & profile
```

### 2.2 Entry Points
1. **Main CLI Driver (`src/app.py` / `run.py`):**
   - Invocation: `python -m src.app [OPTIONS]` or `python run.py [OPTIONS]`
   - CLI Flags supported:
     - `--topic`: Research topic string (default: from `config.yaml` or env).
     - `--max-papers`: Integer cap on papers to synthesize (default: 12).
     - `--report-name`: Output markdown filename (default: `research_report.md`).
     - `--mode`: `quick` (2 search queries, 4 papers/query) or `deep` (4–5 queries, 6 papers/query).
     - `--tone`: `executive`, `engineering`, or `thought_leadership`.
     - `--length`: `concise` or `detailed`.
     - `--map-provider`: `ollama` or `gemini`.
     - `--reduce-provider`: `ollama` or `gemini`.
2. **Shell Script Runner (`./run.sh`):**
   - Automatically activates `.venv`.
   - Runs CLI by default; launches Streamlit frontend when passed `--ui` or `ui`.
3. **Personal Brand Publishing CLI (`python -m src.publishing`):**
   - Subcommands: `publish`, `build`, `serve`, `check`, `research`.
   - Builds static site from `outputs/json/research_report.json` into `website/dist/`.
4. **Local Web Dashboard (`web_app.py`):**
   - Launched via `streamlit run web_app.py --server.headless true`.

### 2.3 Runtime Configuration (`config.yaml`)
- `project`: `name`, `environment`
- `research`:
  - `default_topic`: "AI adoption in enterprise software delivery"
  - `max_papers`: 12
  - `min_relevance_score`: 0.5
  - `time_window`: "2019-2025"
  - `search_sources`: `[openalex, crossref, arxiv, semantic_scholar]`
- `llm`:
  - `map_provider`: Currently set to `gemini` (was `ollama`; changed when local Ollama was shut down).
  - `reduce_provider`: `gemini`
- `ollama`: `base_url` (http://localhost:11434), `model` (`qwen2.5:3b-instruct`), `num_ctx` (4096), `timeout_seconds` (180).
- `gemini`: `model` (`gemini-flash-latest`), reads `GEMINI_API_KEY` from `.env`.
- `output`: `reports_dir`, `json_dir`, `csv_dir`.

### 2.4 Dependencies (`requirements.txt`)
- `requests>=2.31.0` (HTTP API calls)
- `python-dotenv>=1.0.1` (Environment variable loading)
- `PyYAML>=6.0.1` (Configuration parsing)
- `pandas>=2.2.0` (DataFrame handling in Streamlit)
- `pydantic>=2.6.0` (Schema validation)
- `streamlit>=1.35.0` (Local web interface)
- *Implicit runtime dependencies:* `pytest` (used for test execution), `sqlite3` (built into Python standard library).

---

## 3. Literature Fetchers & API Audit

The `README.md` and `ARCHITECTURE.md` only document arXiv, Semantic Scholar, and Crossref. In recent updates, **OpenAlex** was added as a primary source due to its 250M+ open-access index and absence of rate-limiting blocks.

| Client File | Upstream API Endpoint | Query Strategy | Rate Limiting & Politeness | Data Returned | Status / Notes |
|---|---|---|---|---|---|
| `src/fetchers/openalex_client.py` | `https://api.openalex.org/works` | `search={clean_query}&per-page={max_results}` | Custom User-Agent header with mailto. High throughput, no API key needed. | Title, reconstructed abstract (from `abstract_inverted_index`), publication year, DOI/URL, authors, venue. | **Primary Workhorse.** Highly reliable; retrieved 7 of the 8 papers in the recent Kiro run. |
| `src/fetchers/crossref_client.py` | `https://api.crossref.org/works` | `query.bibliographic={clean_query}&rows={max_results}` | User-Agent with mailto (routes to Crossref Polite Pool). 3 retries on 429/503. | Title, abstract (often XML/HTML snippet or empty), year, authors, DOI, URL. | **Active.** Abstracts frequently missing or truncated; fallback abstract synthesized from title/venue. |
| `src/fetchers/arxiv_client.py` | `https://export.arxiv.org/api/query` | `search_query=all:{clean_query}&start=0&max_results={max_results}` | User-Agent with mailto. Retries with 3s backoff on 429. | Title, summary/abstract, published date, arXiv ID, URL. | **Active.** Subject to strict 3s per-request rate limit; returns preprints. |
| `src/fetchers/semantic_scholar_client.py` | `https://api.semanticscholar.org/graph/v1/paper/search` | `query={clean_query}&limit={limit}&fields=...` | User-Agent header. 3 retries with backoff on 429. | Title, abstract, year, authors, URL, venue. | **Unstable.** Heavily throttled without an API key (returns 429 frequently on residential/cloud IPs). |
| *SEC EDGAR* | `https://data.sec.gov/` | *Not yet implemented* | *None* | *None* | **Required in Phase 3** for enterprise 10-K/10-Q filing lane. |

---

## 4. Existing Local Frontend (`web_app.py`) Audit

### 4.1 Technology Stack & Launch Mechanism
- **Stack:** Streamlit (`v1.35.0+`), running as a local Python process.
- **Launch Command:** `.venv/bin/streamlit run web_app.py --server.headless true` (or `./run.sh --ui`).
- **Network Binding:** Listens on `http://localhost:8501`.

### 4.2 Engine Interaction & API Architecture
- **No HTTP API Exists:** The web app currently interacts with the research engine entirely **in-process** via direct Python module imports (`from src.app import build_topic_queries...`, `from src.analysis.synthesizer import SynthesisEngine...`).
- When the user clicks "Run Strategic Research", `web_app.py` executes the entire multi-step retrieval and synthesis pipeline synchronously inside the Streamlit script execution thread.

### 4.3 State Management
- **In-Memory:** Stores intermediate and final synthesis dictionaries in `st.session_state["synthesis"]`.
- **Disk Persistence:** Automatically caches and restores state from `outputs/json/research_report.json` upon startup.
- **Artifacts Generated:**
  - `outputs/reports/strategic_storyline.html` (interactive HTML report)
  - `outputs/reports/linkedin_professional_pack.md` (social/thought leadership copy)
  - `outputs/reports/{topic_slug}.md` (executive markdown brief)
  - `outputs/json/research_report.json` (monolithic data graph)
  - `outputs/csv/paper_index.csv` (source papers spreadsheet)

### 4.4 Human Capabilities & Workflow Gaps
| Feature / Action | Current State in Frontend | v2 Requirement |
|---|---|---|
| Topic Selection | Supported (dropdown + custom text box) | Supported via Question Register (Gate 1) |
| Depth & Provider Controls | Supported (quick/deep, max papers, ollama/gemini) | Supported; practitioner lane strictly local |
| Tone & Length Tuning | Supported (executive, engineering, thought leadership) | Supported; strength verbs governed by claims |
| Claim Review Queue | **Missing** | **Mandatory (Gate 3, View 1)** |
| Venue & Source Tiering | **Missing** | **Mandatory (Gate 2, View 2)** |
| Question Register Management | **Missing** | **Mandatory (Gate 1, View 3)** |
| Gap Matrix Sign-off | **Missing** | **Mandatory (Gate 4, View 4)** |
| Draft Review with Check Badges | **Missing** (view only) | **Mandatory (Gate 5, View 5)** |
| Publish Gate & Scorecard | **Missing** | **Mandatory (Gate 6, View 6)** |
| Practitioner Note Entry Form | **Missing** | **Mandatory (View 7, `practitioner.db`)** |
| Run History & Score Trends | Basic file viewer only | **Mandatory (View 8)** |
| Audit Trail Logging | **None** | **Mandatory append-only `reviews` table** |

---

## 5. Current Outputs vs v2 Target Deliverables

### 5.1 Current Outputs
1. **`outputs/reports/research_report.md` (and slugged markdown briefs):**
   - Monolithic narrative with 14 sections.
   - Mentions paper citations at section level (`[P1]`, `[P2]`), but claims are coarse, unvalidated, and grouped across heterogeneous venues.
2. **`outputs/reports/strategic_storyline.html`:**
   - Visual executive brief with dark-theme CSS, metric cards, and roadmap timelines.
   - Currently includes hardcoded or ungrounded statistics ("20x", "67%", "90%") and stock photography.
3. **`outputs/reports/linkedin_professional_pack.md`:**
   - 6 modular sharing angles (Executive, Engineering, Contrarian, Carousel, Talk, Memo).
   - Currently vulnerable to ungrounded claims and corrupted terms.
4. **`outputs/json/research_report.json`:**
   - JSON tree storing un-atomic paper summaries and synthesis fields.
5. **`outputs/csv/paper_index.csv`:**
   - 4 columns: `title,year,source,url`.

### 5.2 Pieces to be Superseded
- **Unchecked Assertions:** Any assertive sentence lacking a verified claim ID will be blocked by Gate 1 (Traceability).
- **Invented / Uncited Numerics:** The "20x", "67%", "90%" figures will be blocked by Gate 2 (Numeric Fidelity).
- **Misattributed Entity Claims:** Using general AI assistant papers to claim Kiro productivity gains will be blocked by Gate 3 (Entity Fidelity).
- **Uncapped Language:** Overstating evidence ("proves", "shows") when backed by weak preprints or vendor posts will be blocked by Gate 4 (Language Honesty).
- **Stock Images & Invented Acronyms:** Decorative Unsplash images and ungrounded acronyms ("APEXA", "ARDDSF") are banned under Constraint 7.
- **Legacy Files:** All existing outputs in `outputs/` will be flagged as `legacy-ungraded` and blocked from publication.

---

## 6. Test Coverage & Quality Gaps

### Current Test Suite (`tests/test_pipeline.py`)
- Run time: ~0.20s across 4 tests:
  - `test_dedupe`: Verifies DOI and title deduplication.
  - `test_pipeline`: Validates map-reduce flow with a `FakeLLM`.
  - `test_build_topic_queries`: Verifies query expansion and stopword cleaning.
  - `test_openalex_abstract_reconstruction`: Verifies abstract reconstruction from inverted index.

### Critical Testing Gaps for v2
1. **Zero Database Tests:** No SQLite schemas, WAL mode checks, or migration tests exist.
2. **Zero Claim Extraction Tests:** No tests verifying atomic extraction, confidence scoring, or term integrity.
3. **Zero Grading Rule Tests:** No tests validating deterministic grade assignment, venue tier lookups, or contradiction caps.
4. **Zero Regression Suites:** None of the 14 regression cases (R1–R14) defined in Section 11 exist.
5. **Zero Privacy/Denylist Tests:** No test verifying isolation of `practitioner.db` or scanning of `denylist.txt`.

---

## 7. Risks & Proposed Architectural Deviations

In accordance with Section 1 and Section 3 of the prompt, the repository's established conventions are followed. The following architectural decisions and deviations are logged for transparency:

### Deviation 1: Local Frontend API Architecture (Streamlit vs Standalone REST Server)
- **Prompt Assumption:** Suggests adding a minimal local-only API bound to `127.0.0.1` for the frontend.
- **Repo Convention:** The frontend is a native **Streamlit** application (`web_app.py`). Streamlit executes Python directly in-process and does not require an intermediate REST/HTTP API layer to interact with Python modules and SQLite databases.
- **Decision:** Rather than adding an unnecessary external web framework (like FastAPI or Flask) which would introduce network port conflicts and serialization overhead, we will create a dedicated local service layer (`src/ledger/service.py`) that binds directly to the SQLite databases on `127.0.0.1`. Streamlit will consume this service layer directly. Every user action will execute atomic SQLite transactions writing append-only rows to the `reviews` audit table. If external headless access is needed later, a minimal `127.0.0.1` HTTP endpoint can expose this service.
- **Log:** Recorded in `DECISIONS.md`.

### Deviation 2: Folder Layout Harmonisation
- **Prompt Target Layout:** Suggests top-level directories: `questions/`, `collectors/`, `extract/`, `ledger/`, `grade/`, `gaps/`, `synth/`, `score/`, `publish/`, `evals/`.
- **Repo Convention:** The existing repository groups operational code under `src/` (`src/analysis/`, `src/fetchers/`, `src/llm/`, `src/output/`, `src/prompts/`, `src/publishing/`).
- **Decision:** Follow the repo convention to avoid breaking existing import paths and CLI tools. Structure new modules cleanly under `src/`:
  - `src/ledger/` (data models, migrations, DB service)
  - `src/extract/` (atomic claim extraction)
  - `src/grade/` (rules, venue tiers, deterministic grading engine)
  - `src/gaps/` (gap matrix builder)
  - `src/synth/` (ledger-grounded synthesis, strength verb enforcer)
  - `src/score/` (gates, quality scorer)
  - `questions/` (register YAML)
  - `evals/` (regression suite R1–R14)
- **Log:** Recorded in `DECISIONS.md`.

### Deviation 3: LLM Default Configuration for Extraction vs Synthesis
- **Prompt Constraint 1:** Mandates local-first with Ollama for extraction and triage; remote model ONLY for public synthesis behind a config flag defaulting to OFF.
- **Repo State:** `config.yaml` had `map_provider: "gemini"` set in the previous session because Ollama was stopped.
- **Decision:** In v2, revert default configuration in `config.yaml` to `map_provider: "ollama"`, `allow_remote_synthesis: false`. Extraction will be strictly local. Remote Gemini synthesis will be permitted only when `allow_remote_synthesis: true` is explicitly configured, and strictly restricted to public claims (never practitioner claims).
- **Log:** Recorded in `DECISIONS.md`.

---

## 8. Audit Conclusion & Readiness

The audit is complete. No behaviour or production code has been altered during Phase 0. The repository is in a clean, tested state, ready for Phase 1 implementation (SQLite ledger with durability, claim extraction, sentence checker, and regression cases R1–R7, R10).
