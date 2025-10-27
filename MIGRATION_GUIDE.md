# Migration Guide: Spec-002 → Spec-003

**From**: Custom Infrastructure (spec-002)  
**To**: mempool.space Hybrid Architecture (spec-003)  
**Date**: 2025-10-27  
**Status**: Migration Complete

---

## Overview

Spec-003 represents a **fundamental architectural shift** from custom Bitcoin infrastructure to a hybrid approach leveraging the battle-tested mempool.space stack.

### What Changed

| Component | Spec-002 | Spec-003 | Status |
|-----------|----------|----------|--------|
| **ZMQ Listener** | Custom (229 lines) | mempool.space Docker stack | ✅ Replaced |
| **Transaction Parser** | Custom (369 lines) | mempool.space electrs | ✅ Replaced |
| **Block Parser** | Custom (144 lines) | mempool.space backend | ✅ Replaced |
| **Orchestrator** | Custom (271 lines) | \`daily_analysis.py\` (608 lines) | ✅ Replaced |
| **Bitcoin RPC** | Custom (109 lines) | mempool.space + cookie auth | ✅ Replaced |
| **Baseline Calculator** | Duplicated algorithm (581 lines) | \`UTXOracle_library.py\` (536 lines) | ✅ Refactored |
| **Frontend** | Custom Canvas (500+ lines) | Plotly.js (380 lines) | ✅ Simplified |

**Total Code Reduction**: 3,102 → 1,598 lines (**48.5% reduction**)

---

## Key Benefits

- ✅ **48.5% less code** to maintain
- ✅ **Battle-tested infrastructure** (mempool.space)
- ✅ **No binary parsing** (delegated to electrs)
- ✅ **Clean library API** (Rust migration ready)
- ✅ **Zero algorithm duplication**

---

## Migration Steps

See full details in \`specs/003-mempool-integration-refactor/IMPLEMENTATION_STATUS.md\`

### Quick Start (Post Bitcoin Core Sync)

1. Deploy mempool-stack:
   \`\`\`bash
   bash scripts/setup_full_mempool_stack.sh
   cd /media/sam/2TB-NVMe/prod/apps/mempool-stack
   docker-compose up -d
   \`\`\`

2. Update .env:
   \`\`\`bash
   MEMPOOL_API_URL=http://localhost:8999
   \`\`\`

3. Start API server:
   \`\`\`bash
   sudo systemctl enable --now utxoracle-api
   \`\`\`

---

**Full Documentation**: See \`specs/003-mempool-integration-refactor/\` for complete guides
