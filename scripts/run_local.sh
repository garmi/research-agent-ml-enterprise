#!/usr/bin/env bash
# S29d: run AI Guruji on this Mac with Ollama beside it, for when Gemini's limit is reached.
# Nothing is exposed to the internet. Your Gemini key, if you use one, is read from your own environment
# (or .env); this script never stores or prints it.
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${OLLAMA_MODEL:-qwen2.5:3b-instruct}"
export OLLAMA_MODEL="$MODEL"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export RESEARCH_RUNS_DIR="${RESEARCH_RUNS_DIR:-$HOME/.ai-guruji/runs}"   # runs survive a restart
mkdir -p "$RESEARCH_RUNS_DIR"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed. Install it from https://ollama.com/download, then run this again." >&2
  exit 1
fi
if ! curl -fsS "$OLLAMA_BASE_URL/api/tags" >/dev/null 2>&1; then
  echo "Starting Ollama..."
  (ollama serve >/dev/null 2>&1 &)
  for _ in $(seq 1 20); do curl -fsS "$OLLAMA_BASE_URL/api/tags" >/dev/null 2>&1 && break; sleep 1; done
fi
if ! ollama list | awk '{print $1}' | grep -qx "$MODEL"; then
  echo "Downloading $MODEL (about 2 GB, once)..."
  ollama pull "$MODEL"
fi

PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
echo "Opening AI Guruji at http://localhost:8501 (engine: Ollama $MODEL)"
exec "$PY" -m streamlit run web_app.py --server.port 8501
