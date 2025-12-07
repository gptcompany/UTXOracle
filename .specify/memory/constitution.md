<!--
Sync Impact Report - Constitution Update
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Version Change: 1.0.0 → 1.1.0
Bump Rationale: MINOR - Added Principle V (Data Privacy & Security) for real-time financial signals

Principles Modified:
  None

Principles Added:
  V. Data Privacy & Security (NEW)

Added Sections:
  - Principle V with privacy-first architecture requirements
  - Security standards for predictive financial data
  - Local-first processing mandate

Templates Status:
  ✅ .specify/templates/spec-template.md (no changes needed - principles compatible)
  ✅ .specify/templates/plan-template.md (Constitution Check will include new principle)
  ✅ .specify/templates/tasks-template.md (no changes needed - principles compatible)
  ✅ .specify/templates/checklist-template.md (no changes needed - principles compatible)

Runtime Guidance Updates:
  ✅ docs/ARCHITECTURE.md - Contains detailed spec documentation
  ✅ docs/DEVELOPMENT_WORKFLOW.md - Contains TDD and cleanup checklists
  ⚠️ .claude/prompts/utxoracle-system.md - Should reference new principle

Follow-up TODOs:
  - Review privacy implications of whale alert broadcasting
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-->

# UTXOracle Constitution

## Core Principles

### I. Code Quality & Simplicity

**MUST adhere to KISS (Keep It Simple) and YAGNI (You Ain't Gonna Need It) principles:**
- Choose boring, proven technology over novelty (Python before Rust, vanilla JS before frameworks)
- Avoid premature optimization: make it work, then make it fast
- Each module MUST serve a single, well-defined purpose
- Minimize dependencies: every external dependency is technical debt
- Prioritize readability: code that a junior developer can understand beats "clever" code
- Delete dead code immediately: if unused for 2 weeks, remove it
- No generic solutions until you have 3+ real use cases requiring abstraction

**Rationale:** UTXOracle's reference implementation (`UTXOracle.py`) demonstrates that transparency
and simplicity create more value than premature optimization. The 12-step sequential algorithm is
deliberately verbose and linear for educational clarity. New modules must maintain this philosophy
while enabling modularity for production use.

### II. Test-First Discipline (NON-NEGOTIABLE)

**TDD cycle MUST be strictly enforced:**
1. **RED**: Write failing tests first, get user approval on test design
2. **GREEN**: Implement minimal code to pass tests
3. **REFACTOR**: Improve code while maintaining test coverage

**Coverage requirements:**
- Minimum 80% coverage for all production code
- Integration tests required for: module contracts, contract changes, inter-service communication, shared data models
- Tests written BEFORE implementation, no exceptions
- `tdd-guard` agent validates compliance before merge

**Test organization:**
- Unit tests: `tests/test_{module}/`
- Integration tests: `tests/integration/`
- Fixtures: `tests/fixtures/`
- Use `pytest-test-generator` skill for test boilerplate generation

**Rationale:** UTXOracle's price calculations are mission-critical financial data. TDD ensures
correctness, reproducibility, and prevents regressions. The reference implementation's transparency
makes it testable; new modules must maintain this testability.

### III. User Experience Consistency

**All user-facing interfaces MUST maintain consistency:**

**CLI Standards:**
- Text in/out protocol: stdin/arguments → stdout, errors → stderr
- Support both JSON and human-readable formats
- Follow UTXOracle.py argument patterns (e.g., `-d YYYY/MM/DD`, `-rb` for recent blocks, `-p` for paths)
- Provide `--help` with clear examples
- Exit codes: 0 (success), 1 (user error), 2 (system error)

**Visualization Standards:**
- Interactive HTML output with Canvas 2D (MVP) or WebGL (production >5k points)
- Auto-open browser unless `--no-browser` flag provided
- Include: date, price, confidence score, transaction histogram, intraday evolution, blockchain metadata
- Follow existing `UTXOracle_YYYY-MM-DD.html` naming convention

**API Standards (WebSocket):**
- Real-time streaming for mempool analysis
- JSON message format with schema validation (Pydantic models)
- Client connection management with graceful disconnection
- Error handling with descriptive messages

**Rationale:** UTXOracle has 672 days of historical data (Dec 2023 → Oct 2025) with consistent
output format. Users rely on reproducibility and consistent interfaces. Breaking this consistency
creates confusion and technical debt.

### IV. Performance Standards

**MUST meet these performance requirements:**

**Batch Processing:**
- Process historical dates at ~2.25 seconds/date with parallel workers (12 workers baseline)
- Support date ranges via `utxoracle_batch.py` script
- 99.85% success rate minimum (current baseline from 672-day dataset)

**Real-time Mempool:**
- ZMQ transaction streaming latency <100ms
- Price estimation updates ≤5 seconds for new histogram data
- WebSocket broadcast latency <50ms
- Frontend rendering: 60 FPS for Canvas 2D, 30 FPS minimum for WebGL

**Resource Limits:**
- Bitcoin Core RPC: connection pooling, max 10 concurrent requests
- Memory: histogram data structures optimized for <500MB RAM
- Disk: HTML outputs compressed if >1MB

**Logging & Observability:**
- Structured logging (JSON) for production, human-readable for development
- Log levels: ERROR (always), WARN (important), INFO (default), DEBUG (verbose)
- Performance metrics: execution time, RPC call count, memory usage

**Rationale:** UTXOracle processes blockchain data efficiently despite Python's performance
limitations. The reference implementation proves the algorithm works; production modules must
maintain this efficiency while adding real-time capabilities.

### V. Data Privacy & Security

**MUST prioritize user privacy and data security:**

**Privacy-First Architecture:**
- Process all blockchain data locally: no external API dependencies for price calculation
- Self-host all infrastructure (mempool.space, electrs, Bitcoin Core)
- Never transmit user queries or analysis results to third parties
- Cookie authentication preferred over password-based RPC
- Optional features (webhooks, public APIs) MUST be opt-in with explicit consent

**Predictive Data Protection:**
- Whale detection signals are sensitive financial intelligence
- WebSocket connections MUST use authentication tokens in production
- Historical predictions stored locally with configurable retention (90-day default)
- Alert broadcasting limited to authenticated clients only
- Redis pub/sub channels MUST use namespace isolation

**Security Standards:**
- Input validation on all external data (transaction IDs, addresses, amounts)
- Rate limiting on API endpoints to prevent abuse
- Sanitize all user inputs before database queries (SQL injection prevention)
- Use Pydantic models for automatic validation and type safety
- Regular security audits of WebSocket message handling

**Rationale:** UTXOracle's evolution into real-time predictive analysis (mempool whale detection)
creates valuable financial signals that could be exploited if not properly secured. The principle
of local-first processing that made UTXOracle trustworthy for historical analysis must extend
to real-time systems. Users trust us because we don't leak their data.

## Development Workflow

**Black Box Architecture (Vibe Coding Principles):**
- Each module is independently replaceable without breaking others
- Modules communicate only through well-defined interfaces
- One module, one developer ownership pattern
- If you don't understand a module, rewrite it cleanly rather than patching it

**Agent & Skill System:**
- **6 Subagents** for complex reasoning: `bitcoin-onchain-expert`, `transaction-processor`,
  `mempool-analyzer`, `data-streamer`, `visualization-renderer`, `tdd-guard`
- **4 Skills** for template-driven automation: `pytest-test-generator`, `github-workflow`,
  `pydantic-model-generator`, `bitcoin-rpc-connector`
- Token savings: ~87,600 tokens/task (20.4k from Skills + 67.2k from MCP optimization)

**Task Classification:**
- **Task 01**: Bitcoin ZMQ interface (`bitcoin-onchain-expert`)
- **Task 02**: Binary transaction parsing (`transaction-processor`)
- **Task 03**: Mempool price estimation (`mempool-analyzer`)
- **Task 04**: WebSocket API (`data-streamer`)
- **Task 05**: Canvas/WebGL visualization (`visualization-renderer`)

**Pre-Commit Cleanup (NON-NEGOTIABLE):**
- Remove temporary files (`.tmp`, `.bak`, `~`, `.swp`)
- Clean Python cache (`__pycache__`, `.pyc`, `.pytest_cache`)
- Delete debug code (`print()`, `console.log`, `debugger`)
- Remove unused imports (`ruff check --select F401`)
- Run linter/formatter if available (`ruff check .`, `ruff format .`)
- Update `docs/ARCHITECTURE.md` if architecture/specs changed (NOT CLAUDE.md)
- Review `.gitignore` for new patterns

## Governance

**Constitution Authority:**
- This constitution supersedes all other development practices
- All PRs and code reviews MUST verify constitutional compliance
- Complexity requires explicit justification against KISS/YAGNI principles
- Use `.claude/prompts/utxoracle-system.md` for runtime development guidance

**Amendment Process:**
1. Propose change with rationale in GitHub issue
2. Document impact on existing modules and templates
3. Require approval from project maintainer
4. Update version following semantic versioning:
   - **MAJOR**: Backward-incompatible governance/principle changes
   - **MINOR**: New principles or materially expanded guidance
   - **PATCH**: Clarifications, wording fixes, non-semantic refinements
5. Propagate changes to dependent templates (`.specify/templates/*.md`)

**Compliance Review:**
- Every PR checked against principles I-V
- `tdd-guard` agent validates TDD compliance (Principle II)
- Performance benchmarks validated against Principle IV baselines
- UX consistency verified against historical outputs (Principle III)
- Security review for any code handling predictive signals (Principle V)

**Version**: 1.1.0 | **Ratified**: 2025-10-19 | **Last Amended**: 2025-11-07
