# Architecture and Design

## System Layers

### 1. Input Layer (User)
- Topic selection
- Mode selection (quick vs deep)
- Report naming

### 2. Discovery Layer (Fetchers)
- ArxivClient: Searches arXiv via public API
- SemanticScholarClient: Queries Semantic Scholar
- CrossrefClient: Fetches from Crossref

These are modular and can be replaced or extended.

### 3. Processing Layer (Analysis)
- Deduplication: Remove duplicate papers
- Relevance Scoring: Score papers by business + engineering + topic fit
- Filtering: Keep papers above relevance threshold

### 4. Synthesis Layer (LLM)
- Uses local Ollama model
- Analyzes selected papers
- Extracts themes, trends, problems, gaps, recommendations
- Structures output as JSON

### 5. Output Layer (Report Builder)
- Generates markdown for humans
- Generates JSON for agents
- Generates CSV for spreadsheet review

## Data Flow

```
User Topic Input
        ↓
  Query Builder
        ↓
Multiple Paper Fetchers (parallel)
        ↓
    Merge & Dedupe
        ↓
  Relevance Scoring
        ↓
    Filter & Sort
        ↓
   Local LLM Analysis
        ↓
 Structured Synthesis
        ↓
  Report Generation
        ↓
 Markdown + JSON + CSV
```

## Design Decisions

### Why local Ollama?
- No cloud API costs
- Private data processing
- Full control over model selection
- Suitable for Mac environment

### Why multiple sources?
- Better coverage of research landscape
- Reduces bias from single source
- Captures different paper types (academic, preprints, applied)

### Why relevance scoring?
- Focuses synthesis on enterprise-relevant papers
- Reduces noise from academic publishing
- Balances topic, business, and engineering perspectives

### Why structured output?
- Markdown for human reading and sharing
- JSON for downstream agents and tools
- CSV for spreadsheet review and traceability

## Extensibility Points

1. **New Paper Sources**: Add new client in `src/fetchers/`
2. **New Analysis**: Add new scorers or extractors in `src/analysis/`
3. **New Models**: Use different Ollama model by changing config
4. **New Output Formats**: Add new writers in `src/output/`
5. **New Prompts**: Update templates in `src/prompts/`

## Performance Considerations

- Paper fetching is parallelizable (currently sequential)
- LLM calls are the bottleneck (typical: 30-60 seconds per synthesis)
- JSON parsing is resilient to malformed output
- Memory usage is low on Apple Silicon

## Future Improvements

1. Async fetching from multiple sources
2. Caching of papers and scores
3. Interactive web UI
4. Multi-turn agent loop for iterative refinement
5. Advanced clustering and theme extraction
6. Citation and reference extraction

