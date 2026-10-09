#!/usr/bin/env python3
"""Installation and setup guide for the Research Agent."""

print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                   Research Agent Setup Guide for Mac                        ║
╚════════════════════════════════════════════════════════════════════════════╝

This guide will help you set up the research agent on your Mac.

## Step 1: Install Ollama

1. Go to https://ollama.ai or run:
   brew install ollama

2. Start the Ollama server:
   ollama serve

3. In a new terminal, download the recommended model:
   ollama pull qwen2.5:7b-instruct

   (Or use:
   ollama pull llama3.1:8b-instruct)

## Step 2: Set Up Python Environment

1. Clone or navigate to the research-agent-ml-enterprise directory

2. Create a virtual environment:
   python3 -m venv .venv

3. Activate it:
   source .venv/bin/activate

4. Install dependencies:
   pip install -r requirements.txt

## Step 3: Configure Environment

1. Copy the environment template:
   cp .env.example .env

2. Update .env with your values (usually defaults are fine):
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen2.5:7b-instruct
   DEFAULT_TOPIC=AI adoption in enterprise software delivery
   MAX_PAPERS=12

## Step 4: Run Your First Research

1. Make sure Ollama server is running (step 1.2)

2. Run the research agent:
   python -m src.app --topic "AI adoption in enterprise software delivery" --mode deep

3. Or for a quick scan:
   python -m src.app --topic "AI adoption in enterprise software delivery" --mode quick

4. Output will be saved to:
   outputs/reports/research_report.md
   outputs/json/research_report.json
   outputs/csv/paper_index.csv

## Step 5: Use with Claude Code or Google AI Studio

1. Open the project in Claude Code or Google AI Studio

2. Ask it to:
   - Refine the prompts in src/analysis/synthesizer.py
   - Improve the relevance scoring in src/analysis/relevance.py
   - Enhance the report templates in templates/
   - Add new output formats

## Troubleshooting

### Ollama not connecting
- Ensure Ollama server is running: ollama serve
- Check that http://localhost:11434 is accessible
- Try: curl http://localhost:11434/api/tags

### No papers found
- Try a different topic
- Check internet connectivity
- Verify free APIs are working (arXiv, Semantic Scholar, Crossref)

### Model memory issues
- Use a smaller model: ollama pull mistral:7b-instruct
- Reduce max_papers in config.yaml
- Close other applications

### JSON parsing errors
- These are usually handled, but check the model output
- Try a simpler topic
- Increase temperature in src/llm/ollama_client.py to 0.4-0.5

## Next Steps

1. Run the agent on a topic you care about
2. Review the output and adjust prompts
3. Add domain-specific refinements
4. Use the JSON output for downstream agents or tools

For more info, see README.md
""")
