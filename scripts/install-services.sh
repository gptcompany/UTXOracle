#!/usr/bin/env bash
#
# Install UTXOracle systemd services
# Usage: sudo bash scripts/install-services.sh
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}==> Installing UTXOracle systemd services${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Check if service files exist
if [ ! -f "$PROJECT_ROOT/utxoracle-whale-detection.service" ]; then
    echo -e "${RED}ERROR: utxoracle-whale-detection.service not found${NC}"
    exit 1
fi

if [ ! -f "$PROJECT_ROOT/utxoracle-api.service" ]; then
    echo -e "${RED}ERROR: utxoracle-api.service not found${NC}"
    exit 1
fi

# Stop services if running
echo -e "${YELLOW}==> Stopping existing services (if any)...${NC}"
systemctl stop utxoracle-whale-detection.service 2>/dev/null || true
systemctl stop utxoracle-api.service 2>/dev/null || true

# Copy service files to systemd directory
echo -e "${YELLOW}==> Installing service files...${NC}"
cp "$PROJECT_ROOT/utxoracle-whale-detection.service" /etc/systemd/system/
cp "$PROJECT_ROOT/utxoracle-api.service" /etc/systemd/system/

# Set permissions
chmod 644 /etc/systemd/system/utxoracle-whale-detection.service
chmod 644 /etc/systemd/system/utxoracle-api.service

# Create required directories
echo -e "${YELLOW}==> Creating required directories...${NC}"
mkdir -p "$PROJECT_ROOT/data"
mkdir -p "$PROJECT_ROOT/logs"
chown -R sam:sam "$PROJECT_ROOT/data" "$PROJECT_ROOT/logs"

# Reload systemd
echo -e "${YELLOW}==> Reloading systemd daemon...${NC}"
systemctl daemon-reload

# Enable services
echo -e "${YELLOW}==> Enabling services...${NC}"
systemctl enable utxoracle-whale-detection.service
systemctl enable utxoracle-api.service

# Display status
echo ""
echo -e "${GREEN}==> Installation complete!${NC}"
echo ""
echo "Available commands:"
echo "  sudo systemctl start utxoracle-whale-detection"
echo "  sudo systemctl start utxoracle-api"
echo "  sudo systemctl status utxoracle-whale-detection"
echo "  sudo systemctl status utxoracle-api"
echo "  sudo journalctl -u utxoracle-whale-detection -f"
echo "  sudo journalctl -u utxoracle-api -f"
echo ""
echo -e "${YELLOW}NOTE: Services are enabled but not started. Start them manually when ready.${NC}"
