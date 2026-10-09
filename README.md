# Research Agent for AI/ML Enterprise Adoption

A lightweight, cost-effective research synthesis agent for Mac users. It helps you:
- take a topic as input
- find research papers
- identify trends, business problems, and gaps
- produce strategic recommendations and roadmaps
- generate human-readable reports and agent-friendly JSON

This project is designed for deep-dive research in AI/ML, enterprise adoption, agile, SDLC, and related engineering/business topics.

Why this stack:
- Local-first: runs on your Mac without expensive cloud API usage
- Low cost: uses free academic APIs and local Ollama models
- Practical: suitable for both professional research and content generation
- Flexible: outputs Markdown and JSON for human and agent consumption

Topography used

This project follows a layered topology that separates discovery, extraction, synthesis, and reporting.

User input
  ↓
Topic + filters
  ↓
Research fetcher
  ├─ arXiv API
  ├─ Semantic Scholar API
  ├─ Crossref API
  ↓
Paper metadata + abstracts
  ↓
Relevance ranking + dedupe
  ↓
Local LLM analysis (Ollama)
  ├─ paper summary
  ├─ business readout
  ├─ gap detection
  ├─ trend extraction
  ↓
Cross-paper synthesis engine
  ├─ themes
  ├─ market signals
  ├─ business problems
  ├─ recommendations
  ├─ roadmap
  ↓
Report generator
  ├─ research_report.md
  ├─ research_report.json
  ├─ paper_index.csv
  └─ content_pack.md

Project goals
- Explore research topics with strong enterprise and engineering relevance
- Convert research into business language
- Highlight strategic gaps and market opportunities
- Produce shareable content for professional communities
- Generate a structured brief that is usable by humans or future agents

Recommended local model
- Ollama model: qwen2.5:7b-instruct or llama3.1:8b-instruct
- Reason: strong quality-speed tradeoff on Apple Silicon Macs

Architecture overview
- `src/fetchers/` = source APIs (arXiv, Semantic Scholar, Crossref)
- `src/llm/` = local Ollama integration
- `src/analysis/` = relevance scoring, business context, synthesis
- `src/output/` = markdown, JSON, and content-pack generation
- `templates/` = reusable output formats

Quick start

1. Install Ollama on your Mac
   - brew install ollama
   - ollama serve
   - ollama pull qwen2.5:7b-instruct

2. Create a Python virtual environment
   - python3 -m venv .venv
   - source .venv/bin/activate

3. Install dependencies
   - pip install -r requirements.txt

4. Configure environment
   - cp .env.example .env
   - update values as needed

5. Run the app
   - python -m src.app --topic "AI adoption in enterprise software delivery" --mode deep

6. For a quick overview
   - python -m src.app --topic "AI adoption in enterprise software delivery" --mode quick

What the app does

1. Builds search queries from the topic
2. Fetches papers from several free public APIs
3. Deduplicates and ranks the results by topic + business + engineering relevance
4. Sends the selected set to a local LLM for synthesis
5. Adds business context and signalling for enterprise decision-makers
6. Produces a strategic brief in markdown and JSON
7. Creates a paper index and structured content pack

Report sections

The generated report includes:
- Executive Summary
- Research Scope and Questions
- Search Strategy and Sources
- Business Context
- Papers Reviewed
- Summary of Key Findings
- Research Themes
- Market Trends
- Business Problems
- Research Gaps
- Recommendations
- Strategic Roadmap
- Professional Content Ideas
- References
- Appendix

JSON schema

The project outputs a JSON object shaped like this:

{
  "topic": "AI adoption in enterprise software delivery",
  "executive_summary": "...",
  "objective": "...",
  "research_questions": ["..."],
  "sources": ["arXiv", "Semantic Scholar", "Crossref"],
  "time_window": "2019-2025",
  "business_context": {
    "focus_areas": {"ai": ["ai", "model"], "enterprise": ["enterprise"]},
    "business_signal": "...",
    "finding_summary": ["..."]
  },
  "papers": [],
  "key_findings": ["..."],
  "themes": [],
  "market_trends": [],
  "business_problems": [],
  "research_gaps": [],
  "recommendations": [],
  "strategic_roadmap": [],
  "content_pack": {
    "linkedin_post_ideas": [],
    "article_topics": [],
    "talk_outline": []
  },
  "references": []
}

This is optimized for downstream processing by humans and future agents.

Suggested usage patterns

Deep dive mode
- Use a narrow topic
- Fetch 20-30 papers
- Keep top 8-15 for synthesis
- Produce a detailed report with roadmap and content pack

Quick scan mode
- Use 5-10 papers
- Emphasize trends and opportunities
- Generate a concise briefing

Content mode
- Create a professional brief with LinkedIn post ideas, article topics, and talk outlines

Next refinement opportunities
- Add PubMed, IEEE Xplore, or Microsoft Academic support
- Add PDF or full-text summarization
- Add clustering for theme extraction
- Add a web UI for topic submission
- Add structured comparisons across enterprise domains

License

This project is intended for personal research use and strategic synthesis.
