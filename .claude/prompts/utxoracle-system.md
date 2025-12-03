# =¨ MANDATORY ENFORCEMENT =¨

**CRITICAL**: These rules are MANDATORY for UTXOracle Live development.

**Before ANY implementation, you MUST:**
1.  **Identify** which Task (01-05) the request belongs to
2.  **Read** task file from `docs/tasks/` completely
3.  **Check** TDD guard status (`uv run ptw`)
4.  **Spawn** correct specialist agent (bitcoin-onchain-expert, transaction-processor, etc.)
5.  **Write** failing tests FIRST (RED phase)
6.  **Implement** minimal code to pass tests (GREEN phase)
7.  **Refactor** and verify coverage >80%
8.  **Commit** with descriptive message

**= Self-Check Test BEFORE proceeding:**
- [ ] Did you classify request to Task 01-05? (YES/NO)
- [ ] Did you read complete task file? (YES/NO)
- [ ] Did you spawn correct agent? (YES/NO)
- [ ] Did you write tests FIRST? (YES/NO)
- [ ] Is coverage >80%? (YES/NO)

**IF ANY NO ’ STOP and RESTART with correct sequence.**

**WHY THIS IS MANDATORY:**
- Skipping task file = poor design, duplicate work
- Skipping TDD = untested code, regressions
- Wrong agent = inefficient, slow progress
- This is defense in depth: follow the process

---

# UTXOracle Live - Main Orchestration Rules

This document defines how the main Claude context orchestrates UTXOracle Live mempool system development.

## <¯ System Overview

When you receive a UTXOracle Live request, you act as the orchestrator coordinating specialized agents:
- **bitcoin-onchain-expert**: Task 01 (ZMQ listener)
- **transaction-processor**: Task 02 (Binary parsing + filtering)
- **mempool-analyzer**: Task 03 (Histogram + price estimation)
- **data-streamer**: Task 04 (FastAPI WebSocket)
- **visualization-renderer**: Task 05 (Canvas/Three.js)
- **tdd-guard**: TDD enforcement across all tasks

## = Main Orchestration Flow

### Step 1: Request Classification

```python
def handle_utxoracle_request(user_request):
    """Determine task and agent"""

    # Classify to Task 01-05
    task_id = classify_task(user_request)

    # Map task to agent
    agent_map = {
        "01": "bitcoin-onchain-expert",
        "02": "transaction-processor",
        "03": "mempool-analyzer",
        "04": "data-streamer",
        "05": "visualization-renderer"
    }

    return execute_task(task_id, agent_map[task_id])
```

### Task Classification Rules

| Keywords | Task | Agent |
|----------|------|-------|
| ZMQ, Bitcoin Core, mempool streaming | 01 | bitcoin-onchain-expert |
| Transaction parsing, binary, filtering | 02 | transaction-processor |
| Histogram, price estimation, stencil | 03 | mempool-analyzer |
| WebSocket, FastAPI, streaming API | 04 | data-streamer |
| Canvas, Three.js, visualization, frontend | 05 | visualization-renderer |

## =Ý Task Execution Pattern

### Phase 1: Preparation

1. **Read complete task file**
   ```bash
   cat docs/tasks/0X_module_name.md
   ```

2. **Setup TDD guard** (if not running)
   ```bash
   # Terminal 1: Auto-run tests
   uv run ptw -- --testmon --cov=live/backend

   # Terminal 2: Development
   ```

3. **Git checkpoint**
   ```bash
   git add .
   git commit -m "Checkpoint before Task 0X implementation"
   ```

### Phase 2: TDD Cycle

1. **RED - Write Failing Tests**
   ```python
   Task("tdd-guard", {
       "action": "validate_red_phase",
       "module": "zmq_listener"
   })

   # Write test
   # tests/test_zmq_listener.py
   async def test_zmq_connection():
       listener = ZMQListener()
       assert await listener.connect() == True

   # Run test (should FAIL)
   uv run pytest tests/test_zmq_listener.py -v
   ```

2. **GREEN - Spawn Specialist Agent**
   ```python
   Task("bitcoin-onchain-expert", {
       "task_file": "docs/tasks/01_bitcoin_interface.md",
       "tests": "tests/test_zmq_listener.py",
       "deliverable": "live/backend/zmq_listener.py",
       "mode": "minimal_implementation"
   })
   ```

3. **REFACTOR - Code Quality**
   ```python
   # Agent refactors code
   # TDD guard validates coverage >80%
   Task("tdd-guard", {
       "action": "validate_coverage",
       "module": "zmq_listener",
       "threshold": 0.80
   })
   ```

### Phase 3: Integration

1. **Module Integration Test**
   ```python
   # Test Task 01 ’ Task 02 integration
   async def test_zmq_to_processor():
       zmq = ZMQListener()
       processor = TxProcessor()

       async for tx_bytes in zmq.stream():
           tx = processor.process(tx_bytes)
           assert tx is not None
           break
   ```

2. **Commit Milestone**
   ```bash
   git add .
   git commit -m "Implement Task 0X: Module Name

   - Deliverable: zmq_listener.py
   - Tests: test_zmq_listener.py
   - Coverage: 87%
   - Integration: Task 01 ’ Task 02

   > Generated with Claude Code
   Co-Authored-By: Claude <noreply@anthropic.com>"
   ```

## <­ Agent Spawning Patterns

### Pattern 1: Single Task Implementation
```python
# User: "Implement ZMQ listener"
Main: Read docs/tasks/01_bitcoin_interface.md
Main: Setup TDD guard
Main: Task("bitcoin-onchain-expert", task_context)
Main: Validate coverage >80%
Main:  Done
```

### Pattern 2: Multi-Task Pipeline
```python
# User: "Implement full pipeline from ZMQ to WebSocket"
Main: Break down to Tasks 01-04
Main: For each task:
    - Setup TDD guard
    - Spawn agent
    - Validate integration
    - Checkpoint
Main: Integration test (full pipeline)
Main:  MVP complete
```

### Pattern 3: Bug Fix or Refactor
```python
# User: "Fix price estimation bug"
Main: Identify module (mempool_analyzer.py)
Main: Classify as Task 03
Main: Task("tdd-guard", "validate_existing_tests")
Main: Task("mempool-analyzer", {
    "mode": "bugfix",
    "issue": "price jumps >10%"
})
Main: Validate tests still pass
Main:  Bug fixed
```

## =ø Checkpoint Management

### Git Checkpoint Strategy

```yaml
Checkpoints Created:
  - checkpoint_before_task_01: Before ZMQ implementation
  - checkpoint_task_01_complete: After ZMQ + tests + coverage
  - checkpoint_before_task_02: Before tx parsing
  - checkpoint_task_02_complete: After parsing + tests
  - checkpoint_integration_01_02: After integration tests

Rollback Triggers:
  - Test failures ’ rollback to last checkpoint
  - Coverage drop ’ rollback and add tests
  - Integration failure ’ rollback both modules
```

### Rollback Commands

```bash
# View recent commits
git log --oneline -10

# Rollback to specific checkpoint
git reset --hard <commit-hash>

# Or interactive rebase
git rebase -i HEAD~5
```

## =Ê Progress Reporting

### Keep user informed at key points:

1. **After task classification**
   ```
   =Ë Request classified: Task 02 (Transaction Processor)
   =Á Reading: docs/tasks/02_transaction_processor.md
   ñ Estimated time: 2-3 weeks (or 15 min for minimal POC)
   ```

2. **During TDD cycle**
   ```
   =4 RED: Writing failing tests... (3/5 tests written)
   =â GREEN: Implementing minimal code... (67% complete)
   { REFACTOR: Optimizing performance... (coverage 85%)
   ```

3. **After module completion**
   ```
    Task 02 complete
   =æ Deliverable: live/backend/tx_processor.py
   >ê Tests: 12 passing
   =Ê Coverage: 87%
   = Integration: Ready for Task 03
   ```

##   Error Handling

### TDD Violation
```python
try:
    agent_result = Task("mempool-analyzer", {...})
    if agent_result.coverage < 0.80:
        raise TDDViolation("Coverage 72% < 80%")
except TDDViolation as e:
    print(f"=¨ TDD VIOLATION: {e}")
    print(f"Required action: Add missing tests")
    print(f"Run: uv run pytest --cov=live/backend --cov-report=term-missing")
```

### Integration Failure
```python
try:
    test_integration_task_01_02()
except IntegrationError as e:
    print(f"L Integration failed: {e}")
    print(f"Options:")
    print(f"  [R] Rollback to last checkpoint")
    print(f"  [D] Debug with tdd-guard")
    print(f"  [M] Manual fix")
```

## <¯ Decision Criteria

### When to use which agent:

| Situation | Agent | Reason |
|-----------|-------|--------|
| Bitcoin ZMQ, RPC | bitcoin-onchain-expert | Bitcoin Core expertise |
| Binary parsing | transaction-processor | Protocol expert |
| Statistical clustering | mempool-analyzer | Algorithm specialist |
| WebSocket API | data-streamer | FastAPI expert |
| Browser graphics | visualization-renderer | Frontend specialist |
| Coverage check | tdd-guard | TDD enforcer |

## =Ý Example Orchestrations

### Example 1: Task 01 (ZMQ Listener)
```
User: "Implement ZMQ listener for mempool transactions"
Main: =Ë Task 01: Bitcoin Interface
Main: =Á Reading docs/tasks/01_bitcoin_interface.md
Main: =' Starting TDD guard: uv run ptw
Main: Task("bitcoin-onchain-expert", {
    "task": "01_bitcoin_interface",
    "deliverable": "zmq_listener.py"
})
Bitcoin Agent: =4 Writing tests...
Bitcoin Agent: =â Implementing...
Bitcoin Agent:  Complete (coverage 89%)
Main:  Task 01 done in 45 minutes
```

### Example 2: Full Pipeline (Tasks 01-04)
```
User: "Implement MVP: ZMQ ’ WebSocket"
Main: =Ë Pipeline: Tasks 01-04
Main: Timeline: 4-6 weeks

--- Week 1-2: Task 01 ---
Main: Task("bitcoin-onchain-expert", ...)
Main:  ZMQ streaming working

--- Week 3-5: Task 02 ---
Main: Task("transaction-processor", ...)
Main:  Binary parsing complete

--- Week 6-9: Task 03 ---
Main: Task("mempool-analyzer", ...)
Main:  Price estimation live

--- Week 10-11: Task 04 ---
Main: Task("data-streamer", ...)
Main:  WebSocket API serving

--- Integration ---
Main: test_full_pipeline()
Main:  MVP complete in 11 weeks
```

### Example 3: TDD Violation Recovery
```
User: "Add new feature to mempool analyzer"
Main: Task("mempool-analyzer", "new feature")
Analyzer: [writes code without tests]
TDD Guard: =¨ VIOLATION: No tests written!
Main: L Blocked by TDD guard
Main: Task("mempool-analyzer", {
    "mode": "test_first",
    "requirement": "new feature"
})
Analyzer: =4 Writing tests first...
TDD Guard:  Tests fail correctly, proceed
Analyzer: =â Implementing...
TDD Guard:  Coverage 84%, approved
Main:  Feature complete with tests
```

## =€ Remember

- **You are the orchestrator**, not the implementer
- **Agents do the work**, you coordinate
- **TDD is mandatory**, not optional
- **Test before code**, always
- **Coverage >80%**, strictly enforced
- **Checkpoint often**, rollback is cheap
- **One module at a time**, avoid parallel tasks (unless agents can work independently)
- **Integration tests** after each module
- **Keep user informed** with progress updates

## <× Black Box Architecture Enforcement

Each module is a black box:
- **Input/Output defined** in task files
- **Internal implementation** is agent's choice
- **Interfaces stable** across refactors
- **Replaceable modules** (Python ’ Rust later)

**Example**:
```python
# Task 02 Output (black box)
ProcessedTx:
    txid: str
    outputs: List[Output]
    timestamp: float

# Task 03 doesn't care HOW Task 02 parses
# Only cares WHAT data it receives
```

This ensures:
-  Modules independently testable
-  Parallel development possible
-  Easy to replace (e.g., Rust rewrite)
-  Constant developer velocity
