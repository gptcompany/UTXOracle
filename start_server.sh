#!/bin/bash
# UTXOracle Live Server Startup Script
# Prevents multiple instances

set -e

echo "🔍 Checking for existing UTXOracle server instances..."

# Kill any existing instances
EXISTING=$(ps aux | grep "[u]vicorn live.backend.api:app" | awk '{print $2}')
if [ -n "$EXISTING" ]; then
    echo "⚠️  Found existing instances, killing them..."
    echo "$EXISTING" | xargs kill -9
    sleep 2
    echo "✅ Cleaned up existing instances"
else
    echo "✅ No existing instances found"
fi

# Change to project directory
cd "$(dirname "$0")"

echo "🚀 Starting UTXOracle Live server..."
uv run uvicorn live.backend.api:app --host 0.0.0.0 --port 8000
