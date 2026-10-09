#!/bin/bash
# Check dependencies and verify setup

echo "Research Agent Setup Checker"
echo "============================="
echo ""

# Check Python
echo "[1/4] Checking Python..."
if command -v python3 &> /dev/null; then
    python_version=$(python3 --version)
    echo "✓ $python_version found"
else
    echo "✗ Python3 not found. Please install Python 3.9+"
    exit 1
fi

# Check Ollama
echo ""
echo "[2/4] Checking Ollama..."
if command -v ollama &> /dev/null; then
    echo "✓ Ollama found"
else
    echo "✗ Ollama not found. Please install from https://ollama.ai"
    exit 1
fi

# Check Ollama server
echo ""
echo "[3/4] Checking Ollama server..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✓ Ollama server is running"
else
    echo "⚠ Ollama server not running. Start it with: ollama serve"
fi

# Check dependencies
echo ""
echo "[4/4] Checking Python dependencies..."
if [ -f "requirements.txt" ]; then
    python3 -c "import requests; import yaml; import pandas" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✓ All dependencies installed"
    else
        echo "⚠ Some dependencies missing. Run: pip install -r requirements.txt"
    fi
else
    echo "✗ requirements.txt not found"
    exit 1
fi

echo ""
echo "Setup check complete!"
echo "Ready to run: python -m src.app --topic \"Your topic here\""
