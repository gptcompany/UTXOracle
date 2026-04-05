#!/bin/bash
# UTXOracle Network Bandwidth Check (T106)
# Checks if mempool-stack usage is mostly localhost

echo "=== UTXOracle Network Bandwidth Check ==="
echo "Date: $(date)"
echo

echo "Local active connections to infrastructure ports:"
echo "Mempool API (8999): $(ss -ant | grep :8999 | grep ESTAB | wc -l) connections"
echo "Electrs (3001):    $(ss -ant | grep :3001 | grep ESTAB | wc -l) connections"
echo "QuestDB (8812):   $(ss -ant | grep :8812 | grep ESTAB | wc -l) connections"

echo
echo "Docker internal network traffic (best-effort):"
if command -v docker > /dev/null; then
    docker stats --no-stream --format "table {{.Name}}\t{{.NetIO}}"
fi

echo
echo "To measure real-time bandwidth (T106), use:"
echo "sudo nethogs -v 3"
echo "or"
echo "sudo iftop -i lo"
