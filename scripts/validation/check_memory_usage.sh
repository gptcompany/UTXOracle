#!/bin/bash
# UTXOracle Memory Usage Check (T104)
# Monitor memory usage of API processes

echo "=== UTXOracle Memory Usage Check ==="
echo "Date: $(date)"
echo

# Find API processes (Legacy and Live)
# Legacy uses uvicorn directly or uv run uvicorn
# Live uses uvicorn or python -m api.apps.live

echo "Process RSS (Memory):"
ps -eo pid,rss,command | grep -E "uvicorn|api\.apps\.live|api\.main" | grep -v grep | awk '{printf "PID %s: %.2f MB (%s)\n", $1, $2/1024, $3}'

echo
echo "System Summary:"
free -h | head -2

echo
echo "To monitor for 24h (T104), run:"
echo "while true; do ps -C uvicorn -o rss= >> /tmp/api_memory.log; sleep 3600; done"
