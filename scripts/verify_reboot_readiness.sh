#!/bin/bash
# UTXOracle Reboot Readiness Verification Script
# Checks system configuration for persistence after reboot

set -e

echo "=== UTXOracle Reboot Readiness Check ==="
echo "Date: $(date)"
echo

# 1. Systemd persistence
echo "[1/4] Checking Systemd Persistence..."
SERVICES=("utxoracle-api" "utxoracle-live-compose" "utxoracle-whale-detection")
for svc in "${SERVICES[@]}"; do
    if systemctl is-enabled --quiet "$svc" 2>/dev/null; then
        echo "✅ $svc is enabled for auto-start"
    else
        echo "❌ $svc is NOT enabled"
    fi
    
    # Check Restart policy
    FRAG=$(systemctl show -p FragmentPath "$svc" | cut -d= -f2)
    if [ -n "$FRAG" ] && [ -f "$FRAG" ]; then
        POLICY=$(grep "Restart=" "$FRAG" | cut -d= -f2)
        echo "   Restart policy: $POLICY ($(basename "$FRAG"))"
        if [[ "$POLICY" =~ ^(always|on-failure)$ ]]; then
            echo "   ✅ Valid resilience policy"
        else
            echo "   ⚠️  Weak or missing resilience policy"
        fi
    else
        echo "   ❌ Service unit file not found or not installed in system"
    fi
done
echo

# 2. Docker persistence
echo "[2/4] Checking Docker Persistence..."
# Check for restart policies in compose file or live containers
if [ -f "docker-compose.live.yml" ]; then
    if grep -q "restart: always" docker-compose.live.yml || grep -q "restart: unless-stopped" docker-compose.live.yml; then
        echo "✅ docker-compose.live.yml contains restart policies"
    else
        echo "⚠️  docker-compose.live.yml might be missing restart policies"
    fi
else
    echo "❌ docker-compose.live.yml not found"
fi
echo

# 3. Cron Persistence
echo "[3/4] Checking Cron Persistence..."
if [ -f "/etc/cron.d/utxoracle-analysis" ]; then
    echo "✅ Cron file found at /etc/cron.d/utxoracle-analysis"
else
    echo "❌ Cron file NOT found in /etc/cron.d/"
fi
echo

# 4. Storage Persistence
echo "[4/4] Checking Storage Mounts..."
# Check if relevant paths are in fstab for NVMe persistence (optional, best-effort)
if grep -q "/media/sam/2TB-NVMe" /etc/fstab 2>/dev/null; then
    echo "✅ NVMe mount found in /etc/fstab"
else
    echo "⚠️  NVMe mount NOT found in /etc/fstab (reboot might lose it)"
fi

echo
echo "=== Reboot Readiness Check Complete ==="
