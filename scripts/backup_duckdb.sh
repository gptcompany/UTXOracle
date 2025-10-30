#!/bin/bash
# DuckDB Backup Script
# Creates daily backups with 30-day retention

set -e

DB_PATH="/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
BACKUP_DIR="/media/sam/2TB-NVMe/prod/apps/utxoracle/data/backups"
RETENTION_DAYS=30

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup filename with date
BACKUP_FILE="$BACKUP_DIR/utxoracle_cache_$(date +%Y-%m-%d).db"

# Create backup (copy)
if [ -f "$DB_PATH" ]; then
    cp "$DB_PATH" "$BACKUP_FILE"
    echo "✅ Backup created: $BACKUP_FILE"
    echo "   Size: $(du -h $BACKUP_FILE | cut -f1)"
else
    echo "❌ Source database not found: $DB_PATH"
    exit 1
fi

# Remove old backups (keep last 30 days)
find "$BACKUP_DIR" -name "utxoracle_cache_*.db" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
echo "✅ Removed backups older than $RETENTION_DAYS days"

# List recent backups
echo
echo "Recent backups:"
ls -lh "$BACKUP_DIR" | tail -5
