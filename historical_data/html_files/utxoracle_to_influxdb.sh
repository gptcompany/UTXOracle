#!/bin/bash
# UTXOracle to InfluxDB - Production Script (Parallel Safe)
# Usage: ./utxoracle_to_influxdb.sh YYYY-MM-DD [full|test]

set -e  # Exit on any error

# Parameters
DATE_INPUT="$1"
MODE="${2:-test}"  # full or test (default: test)

# Validation
if [ -z "$DATE_INPUT" ]; then
    echo "❌ Usage: $0 YYYY-MM-DD [full|test]"
    echo "   Examples:"
    echo "   $0 2023-12-15 test    # Import first 100 elements"
    echo "   $0 2023-12-15 full    # Import complete array (~56k elements)"
    exit 1
fi

# Convert date format for file matching
DATE_FILE=$(echo "$DATE_INPUT" | tr '-' '-')  # YYYY-MM-DD format
HTML_FILE="UTXOracle_${DATE_FILE}.html"

# Check if HTML file exists
if [ ! -f "$HTML_FILE" ]; then
    echo "❌ ERROR: HTML file not found: $HTML_FILE"
    exit 1
fi

# Unique temporary files using PID
PID=$$
TEMP_ARRAY="/tmp/utxoracle_array_${DATE_FILE}_${PID}.txt"
TEMP_PROTOCOL="/tmp/utxoracle_protocol_${DATE_FILE}_${PID}.line"

# Cleanup function
cleanup() {
    rm -f "$TEMP_ARRAY" "$TEMP_PROTOCOL"
}
trap cleanup EXIT

# InfluxDB configuration
TOKEN_FILE="/media/sam/2TB-NVMe/prod/services/influxdb/secrets/admin-token.txt"
if [ ! -f "$TOKEN_FILE" ]; then
    echo "❌ ERROR: Token file not found: $TOKEN_FILE"
    exit 1
fi
TOKEN=$(cat "$TOKEN_FILE")

# Calculate base timestamp (nanoseconds)
BASE_TIMESTAMP=$(date -d "$DATE_INPUT" +%s)000000000

echo "🎯 UTXOracle → InfluxDB (Parallel Safe)"
echo "Date: $DATE_INPUT"
echo "HTML: $HTML_FILE"
echo "Mode: $MODE"
echo "PID: $PID (unique temp files)"
echo

# Extract JavaScript array
echo "📊 Extracting JavaScript array..."
if ! grep -o "const prices = \\[[^]]*\\]" "$HTML_FILE" | sed "s/const prices = \\[\\([^]]*\\)\\]/\\1/" | tr "," "\\n" > "$TEMP_ARRAY"; then
    echo "❌ ERROR: Failed to extract prices array from $HTML_FILE"
    exit 1
fi

TOTAL_ELEMENTS=$(wc -l < "$TEMP_ARRAY")
echo "✅ Extracted: $TOTAL_ELEMENTS elements"

# Determine processing limit
if [ "$MODE" = "full" ]; then
    LIMIT_CMD="cat"
    echo "🚀 Processing FULL array ($TOTAL_ELEMENTS elements)"
else
    LIMIT_CMD="head -100"
    echo "🧪 Processing TEST mode (first 100 elements)"
fi

# Generate line protocol
echo "📝 Generating line protocol..."
eval "$LIMIT_CMD" "$TEMP_ARRAY" | nl -v0 | while read sequence price; do
    # Skip empty lines
    if [ -z "$price" ] || [ "$price" = " " ]; then
        continue
    fi
    
    # Timestamp = base + sequence (preserves ordering, avoids collision)
    timestamp=$((BASE_TIMESTAMP + sequence))
    
    # Create line protocol
    echo "bitcoin_intraday_analysis,analysis_date=$DATE_INPUT,source=utxoracle price=$price,sequence=$sequence $timestamp"
done > "$TEMP_PROTOCOL"

PROTOCOL_LINES=$(wc -l < "$TEMP_PROTOCOL")
echo "✅ Generated: $PROTOCOL_LINES line protocol records"

# Import to InfluxDB
echo "📤 Importing to InfluxDB bitcoin_historical bucket..."
HTTP_CODE=$(curl -w "%{http_code}" -s -o /dev/null \
    -X POST "http://localhost:8086/api/v2/write?org=production&bucket=bitcoin_historical" \
    -H "Authorization: Token $TOKEN" \
    -H "Content-Type: text/plain" \
    --data-binary @"$TEMP_PROTOCOL")

if [ "$HTTP_CODE" = "204" ]; then
    echo "✅ SUCCESS: $PROTOCOL_LINES records imported for date $DATE_INPUT"
    echo "📊 Grafana: Data ready for visualization"
else
    echo "❌ ERROR: HTTP $HTTP_CODE - Import failed"
    exit 1
fi

echo "🎯 UTXOracle import completed successfully!"
