#!/bin/bash
# Batch import di tutte le 653 date UTXOracle → InfluxDB
# Usage: ./batch_all_dates.sh [workers] [mode]

WORKERS="${1:-8}"      # Numero worker paralleli (default: 8)
MODE="${2:-full}"      # full o test (default: full)

echo "🚀 BATCH IMPORT UTXOracle → InfluxDB"
echo "Workers: $WORKERS"
echo "Mode: $MODE"
echo "Target: All HTML files in current directory"
echo

# Verifica script principale esiste
if [ ! -f "./utxoracle_to_influxdb.sh" ]; then
    echo "❌ ERROR: utxoracle_to_influxdb.sh not found in current directory"
    exit 1
fi

# Lista tutti i file HTML UTXOracle
HTML_FILES=$(ls UTXOracle_*.html 2>/dev/null | wc -l)
if [ "$HTML_FILES" -eq 0 ]; then
    echo "❌ ERROR: No UTXOracle_*.html files found"
    exit 1
fi

echo "📁 Found: $HTML_FILES HTML files"

# Estrai date dai nomi file e processa in parallelo
ls UTXOracle_*.html | sed 's/UTXOracle_\(.*\)\.html/\1/' | xargs -I {} -P "$WORKERS" bash -c '
    DATE="$1"
    MODE="$2"
    echo "🔄 Processing: $DATE (Worker $$)"
    if ./utxoracle_to_influxdb.sh "$DATE" "$MODE"; then
        echo "✅ Completed: $DATE"
    else
        echo "❌ Failed: $DATE" >&2
    fi
' _ {} "$MODE"

echo "🎯 Batch processing completed!"
echo "📊 All data ready for visualization"
