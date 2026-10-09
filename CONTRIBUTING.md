# Contribution Guidelines

This project is designed for personal research use and strategic synthesis on Mac.

## Suggested Improvements

1. **Prompts**: Refine the synthesis and analysis prompts in `src/analysis/synthesizer.py` and `src/prompts/research_prompts.py`
2. **Relevance Scoring**: Improve the scoring logic in `src/analysis/relevance.py`
3. **Output Templates**: Enhance markdown and JSON templates in `templates/`
4. **Sources**: Add more paper sources (PubMed, IEEE Xplore, Microsoft Academic)
5. **Features**: Add citation extraction, PDF summarization, or clustering

## Running with Claude Code or Google AI Studio

1. Open the project in Claude Code or Google AI Studio
2. Ask the AI to:
   - Refine prompts for your domain
   - Add new analysis layers
   - Improve report structure
   - Add new output formats

## Local Development

1. Create a branch for your changes
2. Test on a sample topic
3. Verify the outputs are useful
4. Document any significant changes

## Testing

Before committing:
```bash
source .venv/bin/activate
python -m src.app --topic "test topic" --mode quick
```

Check the outputs folder for generated reports.

## Code Style

- Python 3.9+
- Type hints preferred
- PEP 8 style guide
- Docstrings for classes and functions

