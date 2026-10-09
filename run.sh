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

echo ""
echo "Running research agent..."
echo ""

python -m src.app --topic "AI adoption in enterprise software delivery" --mode deep

echo ""
echo "Done! Check outputs/reports/ for your research brief."
