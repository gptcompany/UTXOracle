# Resume Point for Next Session

**Date**: 2025-10-19
**Command to resume**: `/speckit.implement`
**Feature**: specs/002-mempool-live-oracle

## Current Status

### ✅ Completed (T001-T032)
- Phase 1: Setup complete (UV workspace, directories, dependencies)
- Phase 2: Foundational complete (data models, test fixtures, shared infrastructure)
- Module 1: Bitcoin Interface COMPLETE (ZMQ listener, auto-reconnect, tests passing)

### ⚠️ In Progress (T033-T038) - Module 2: Transaction Processor
**Current state**: PARTIALLY implemented (incremental TDD in progress)

**File**: `live/backend/tx_processor.py`
- ✅ Dataclasses defined (TransactionInput, TransactionOutput, ParsedTransaction)
- ✅ Method `parse_transaction()` exists
- ✅ Parses `version` field only (4 bytes)
- ❌ NOT yet parsing: inputs, outputs, locktime, SegWit

**Next test to fix**:
```bash
uv run pytest tests/test_tx_processor.py::test_parse_binary_transaction -v
```

**Expected error**: Test will fail because `inputs=[]` but test expects `len(inputs)==1`

**Next step**: Implement input parsing incrementally following TDD workflow

### 📝 Pending (T039-T104)
- Module 3: Mempool Analyzer (histogram, stencil, convergence)
- Module 4: Data Streamer (FastAPI WebSocket)
- Module 5: Visualization Renderer (Canvas 2D)
- Integration & Polish

## Important Changes Made This Session

### 🎯 Agent Descriptions Updated
**All 5 implementation agents now have "⚡ Incremental Implementation Workflow" section**:
- `.claude/agents/transaction-processor.md` ✅
- `.claude/agents/bitcoin-onchain-expert.md` ✅
- `.claude/agents/mempool-analyzer.md` ✅
- `.claude/agents/data-streamer.md` ✅
- `.claude/agents/visualization-renderer.md` ✅

**This section explains**:
- Context: Tests pre-written in batch by tdd-guard (tasks T020-T027)
- Workflow: Run test → Capture error → Minimal fix → Repeat
- Why: TDD hook rejects batch implementation as "over-implementation"

### 🛡️ TDD Hook Behavior Understood
**Hook location**: `/home/sam/.npm-global/bin/tdd-guard` (Node.js package)
**Hook config**: `.claude/settings.local.json` line 104-111 (PreToolUse matcher)

**How it works**:
1. Every Write/Edit calls tdd-guard hook
2. Hook validates implementation is MINIMAL for ONE specific error
3. Hook rejects "batch" implementation (all features at once)
4. Hook accepts "incremental" implementation (one error → one fix)

**Required workflow**:
1. Run test first → Get specific error (e.g., `AttributeError`)
2. Show error output in implementation message
3. Implement ONLY the minimal fix for THAT error
4. Re-run test → Get NEXT error
5. Repeat until GREEN

## How to Resume

### Option A: Continue with /speckit.implement (Recommended)
```bash
/speckit.implement
```

The workflow will:
1. Parse tasks.md and detect T033-T038 are pending
2. Launch `transaction-processor` agent (as per tasks.md agent assignment)
3. Agent will follow incremental TDD workflow (new section added)
4. Complete Module 2 incrementally (T033-T038)
5. Mark tasks [X] as completed in tasks.md

### Option B: Manual agent delegation
```
Launch transaction-processor agent with context:
- Implement Module 2 tasks T033-T038
- Tests exist: tests/test_tx_processor.py (10 tests, all FAILING)
- Current state: tx_processor.py partially implemented (version field only)
- Follow incremental TDD workflow (section in agent description)
```

## Key Files to Check Next Session

### Implementation files
- `live/backend/tx_processor.py` - Partially complete (version parsing only)
- `live/backend/bitcoin_parser.py` - NOT created yet (T033 creates this)

### Test files (all exist, all FAILING for Module 2)
- `tests/test_tx_processor.py` - 10 tests for Module 2

### Task tracking
- `specs/002-mempool-live-oracle/tasks.md` - Mark [X] as you complete

### Agent descriptions (updated with TDD workflow)
- `.claude/agents/transaction-processor.md` - Read "⚡ Incremental Implementation Workflow"

## Expected Next Steps

When you run `/speckit.implement` next session:

1. **Checkpoint validation**: Verify Phase 1-2 complete, Module 1 complete
2. **Task parsing**: Identify T033-T038 as next tasks (Module 2)
3. **Agent launch**: Launch `transaction-processor` subagent
4. **Incremental TDD**: Agent will:
   - Run test → Error: `inputs=[]` but expected `len==1`
   - Implement input parsing (varint + loop)
   - Run test → Error: next field missing
   - Continue until test PASSES
5. **Mark tasks [X]**: Update tasks.md after each completed task
6. **Proceed to Module 3**: Once T033-T038 complete

## Notes for Future You

- ✅ TDD hook is WORKING AS DESIGNED - forces incremental development
- ✅ Agent descriptions NOW include incremental workflow instructions
- ✅ No need to disable hook - agents know how to work with it
- ✅ Each agent call will be slower (many test/fix cycles) but safer
- ✅ Coverage will be high because every line has a test that required it

**Estimated time for Module 2**: 20-30 incremental cycles (~10 minutes with agent automation)

---

*Created*: 2025-10-19
*Session Context*: 129k tokens used, agents updated, ready to resume
