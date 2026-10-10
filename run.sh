#!/bin/bash
# Quick start script for the research agent

echo "Research Agent Quick Start"
echo "========================="
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing dependencies..."
pip install -q -r requirements.txt

if [ "$1" = "--ui" ] || [ "$1" = "ui" ]; then
    echo "Starting Web Frontend at http://localhost:8501 ..."
    streamlit run web_app.py
else
    echo "Running research agent CLI..."
    python -m src.app --topic "AI adoption in enterprise software delivery" --mode quick --max-papers 5 --map-provider gemini --reduce-provider gemini
    echo ""
    echo "Done! Check outputs/reports/ for your research brief."
    echo "Tip: Run './run.sh --ui' to launch the interactive web dashboard."
fi
