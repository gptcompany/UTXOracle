#!/bin/bash
# DuckDB Daily Backup Script (T095)

DUCKDB_PATH="/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
BACKUP_DIR="/media/sam/2TB-NVMe/prod/apps/utxoracle/backups"
DATE=$(date +%Y-%m-%d)
BACKUP_FILE="$BACKUP_DIR/utxoracle_cache_$DATE.db"

# Create backup directory if not exists
mkdir -p "$BACKUP_DIR"

# Backup database
if [ -f "$DUCKDB_PATH" ]; then
    cp "$DUCKDB_PATH" "$BACKUP_FILE"
    echo "✅ Backup created: $BACKUP_FILE"
    
    # Delete backups older than 30 days
    find "$BACKUP_DIR" -name "utxoracle_cache_*.db" -mtime +30 -delete
    echo "✅ Old backups cleaned (>30 days)"
else
    echo "❌ Database not found: $DUCKDB_PATH"
    exit 1
fi
