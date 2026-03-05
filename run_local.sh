#!/bin/bash
# run_local.sh — Run Enrichr locally for development
set -e

echo "🔧 Starting Enrichr locally..."

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "⚠️  ANTHROPIC_API_KEY not set."
  echo "   Export it: export ANTHROPIC_API_KEY=sk-ant-..."
  exit 1
fi

# Install dependencies if needed
if ! python -c "import flask" 2>/dev/null; then
  echo "📦 Installing dependencies..."
  pip install -r requirements.txt
fi

# Create temp dirs
mkdir -p /tmp/uploads /tmp/outputs

echo "🌐 Starting Flask dev server on http://localhost:8080"
python app.py
