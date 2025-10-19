# Hook-Based Learning & Statistics Collection Systems
## Research Report: AI Agent Frameworks on GitHub

**Research Date**: 2025-10-19
**Focus**: Hook systems, telemetry, pattern detection, and auto-checkpoint mechanisms
**Time Invested**: 45 minutes

---

## Executive Summary

Five key findings from researching hook-based systems across major AI agent frameworks:

1. **Callback/Event Pattern Dominates**: LangChain (callbacks), CrewAI (telemetry), and pytest (hookimpl) all use similar observer patterns with lifecycle hooks
2. **Mixin Architecture Wins**: LangChain's `BaseCallbackHandler` uses multiple mixins (LLMManagerMixin, ToolManagerMixin, etc.) for separation of concerns
3. **Anonymous Telemetry is Standard**: CrewAI and AutoGPT collect anonymous usage stats by default, with opt-out via environment variables
4. **OpenTelemetry Integration is Emerging**: All modern frameworks (2025) moving toward OpenTelemetry for standardized observability
5. **No Built-in Pattern Detection**: Frameworks collect raw data but delegate pattern analysis to external platforms (LangSmith, AgentOps, SigNoz)

---

## Part 1: Implementation Patterns (Code Examples)

### 1.1 LangChain: Mixin-Based Callback System

**Architecture**: Multiple mixins compose a `BaseCallbackHandler` with ~30 lifecycle events

```python
# From langchain_core/callbacks/base.py
class BaseCallbackHandler(
    LLMManagerMixin,
    ChainManagerMixin,
    ToolManagerMixin,
    RetrieverManagerMixin,
    CallbackManagerMixin,
    RunManagerMixin,
):
    """Base callback handler for LangChain."""

    raise_error: bool = False
    run_inline: bool = False

    @property
    def ignore_llm(self) -> bool:
        return False

    @property
    def ignore_tool(self) -> bool:
        return False
```

**Key Lifecycle Events**:
```python
# Tool hooks
def on_tool_start(
    self,
    serialized: dict[str, Any],
    input_str: str,
    *,
    run_id: UUID,
    parent_run_id: UUID | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Run when the tool starts running."""

def on_tool_end(
    self,
    output: Any,
    *,
    run_id: UUID,
    parent_run_id: UUID | None = None,
    **kwargs: Any,
) -> Any:
    """Run when the tool ends running."""

def on_tool_error(
    self,
    error: BaseException,
    *,
    run_id: UUID,
    parent_run_id: UUID | None = None,
    **kwargs: Any,
) -> Any:
    """Run when tool errors."""

# LLM hooks
def on_llm_start(...) -> Any: ...
def on_llm_end(...) -> Any: ...
def on_llm_error(...) -> Any: ...
def on_llm_new_token(...) -> Any:  # Streaming support

# Chain hooks
def on_chain_start(...) -> Any: ...
def on_chain_end(...) -> Any: ...
def on_chain_error(...) -> Any: ...

# Agent hooks
def on_agent_action(...) -> Any: ...
def on_agent_finish(...) -> Any: ...

# Custom events (NEW in 0.2.15)
def on_custom_event(
    self,
    name: str,
    data: Any,
    *,
    run_id: UUID,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Override to define a handler for a custom event."""
```

**Usage Pattern**:
```python
from langchain_core.callbacks import BaseCallbackHandler

class StatisticsCollector(BaseCallbackHandler):
    def __init__(self):
        self.tool_usage = {}
        self.errors = []

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        tool_name = serialized.get("name", "unknown")
        self.tool_usage[tool_name] = self.tool_usage.get(tool_name, 0) + 1

    def on_tool_error(self, error, *, run_id, **kwargs):
        self.errors.append({
            "run_id": str(run_id),
            "error": str(error),
            "timestamp": datetime.now().isoformat()
        })

# Usage
callback = StatisticsCollector()
result = llm.invoke("Hello", config={"callbacks": [callback]})
print(callback.tool_usage)  # {'tool_name': 5, ...}
```

**Token Tracking Example**:
```python
from langchain_core.callbacks import UsageMetadataCallbackHandler

callback = UsageMetadataCallbackHandler()

llm_1.invoke("Hello", config={"callbacks": [callback]})
llm_2.invoke("World", config={"callbacks": [callback]})

# Aggregate usage across multiple calls
print(callback.usage_metadata)  # {input_tokens: 10, output_tokens: 15, ...}
```

---

### 1.2 CrewAI: Anonymous Telemetry with OpenTelemetry

**Architecture**: Environment-variable controlled telemetry with opt-in detailed sharing

```python
# Enable/Disable Telemetry
import os

# Disable CrewAI telemetry
os.environ['CREWAI_DISABLE_TELEMETRY'] = 'true'

# Disable all OpenTelemetry
os.environ['OTEL_SDK_DISABLED'] = 'true'
```

**Data Collection (Default - Anonymous)**:
- CrewAI version, Python version
- Crew metadata: random key, process type, task/agent counts
- Agent data: role, settings, tools (NO prompts/backstories)
- Task metadata (NO descriptions/context)
- Tool usage statistics
- Execution data (NO outputs)

**Advanced Telemetry (Opt-in)**:
```python
from crewai import Crew

crew = Crew(
    agents=[agent1, agent2],
    tasks=[task1, task2],
    share_crew=True  # ⚠️ Enables detailed data collection (includes prompts/outputs)
)
```

**What `share_crew=True` Adds**:
- Agent goals, backstories
- Task contexts, descriptions
- Execution outputs
- Personal information (if included in prompts)

**Integration Pattern**:
```python
# CrewAI integrates with external platforms
from crewai import Crew
import openlit  # OpenTelemetry integration

# Initialize OpenLIT for tracing
openlit.init()

crew = Crew(agents=[...], tasks=[...])
result = crew.kickoff()

# Traces automatically sent to observability platform
```

---

### 1.3 Pytest: Plugin Hook System

**Architecture**: Decorator-based hookspec with dynamic argument pruning

```python
# From pytest hookspec.py
import pytest

@pytest.hookspec(
    firstresult=True,  # Stop after first non-None result
    historic=True,     # Call for late-registered plugins
    warn_on_impl_args={"fspath": ...}  # Warn about deprecated args
)
def pytest_collection_modifyitems(
    session: Session,
    config: Config,
    items: list[Item]
) -> None:
    """Called after collection to filter/reorder test items."""
```

**Hook Implementation Example**:
```python
# conftest.py
import pytest

@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(session, config, items):
    """Collect test statistics during collection phase."""
    stats = {
        "total_tests": len(items),
        "by_marker": {},
        "by_file": {}
    }

    for item in items:
        # Collect by marker
        for marker in item.iter_markers():
            stats["by_marker"][marker.name] = \
                stats["by_marker"].get(marker.name, 0) + 1

        # Collect by file
        file_path = str(item.fspath)
        stats["by_file"][file_path] = \
            stats["by_file"].get(file_path, 0) + 1

    # Store in session for later access
    session.stats = stats

@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """Wrap test execution to collect timing data."""
    outcome = yield
    report = outcome.get_result()

    # Collect execution statistics
    if report.when == "call":
        stats = {
            "duration": report.duration,
            "outcome": report.outcome,  # "passed", "failed", "skipped"
            "nodeid": report.nodeid
        }

        # Store in item for fixture access
        item.test_stats = stats

    return report

@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Generate custom statistics report at end of session."""
    stats = terminalreporter.stats

    print("\n=== Custom Test Statistics ===")
    print(f"Total tests: {stats.get('passed', 0) + stats.get('failed', 0)}")
    print(f"Passed: {len(stats.get('passed', []))}")
    print(f"Failed: {len(stats.get('failed', []))}")
```

**Execution Order Control**:
```python
@pytest.hookimpl(tryfirst=True)   # Execute early
def hook_early(): ...

@pytest.hookimpl(trylast=True)    # Execute late
def hook_late(): ...

@pytest.hookimpl(wrapper=True)    # Wrap all others
def hook_wrapper():
    # Before all hooks
    yield
    # After all hooks
```

**Fixture Integration**:
```python
@pytest.hookimpl
def pytest_runtest_makereport(item, call):
    """Access fixture data from hooks."""
    # Get fixture values
    if "tmp_path" in item.fixturenames:
        tmp_path = item.funcargs["tmp_path"]
        print(f"Test used tmp_path: {tmp_path}")
```

---

### 1.4 Pre-commit Hooks: Git-Based Automation

**Pattern**: Python entry points triggered by git events

**.pre-commit-config.yaml**:
```yaml
repos:
  - repo: local
    hooks:
      - id: generate-docs
        name: Auto-generate documentation
        entry: python scripts/generate_docs.py
        language: system
        pass_filenames: false
        always_run: true

      - id: track-usage
        name: Track tool usage statistics
        entry: python scripts/track_usage.py
        language: system
        types: [python]
```

**Custom Hook Implementation**:
```python
# scripts/track_usage.py
import sys
import json
from pathlib import Path
from datetime import datetime

def track_commit_stats():
    """Track statistics about commits."""
    stats_file = Path(".git/hooks/stats.jsonl")

    stats = {
        "timestamp": datetime.now().isoformat(),
        "files_changed": len(sys.argv) - 1,
        "file_types": {}
    }

    # Analyze changed files
    for filepath in sys.argv[1:]:
        ext = Path(filepath).suffix
        stats["file_types"][ext] = stats["file_types"].get(ext, 0) + 1

    # Append to JSONL log
    with stats_file.open("a") as f:
        f.write(json.dumps(stats) + "\n")

    return 0  # Success

if __name__ == "__main__":
    sys.exit(track_commit_stats())
```

**Auto-Documentation Hook**:
```python
# scripts/generate_docs.py
import subprocess
from pathlib import Path

def generate_docs():
    """Auto-generate docs from docstrings."""
    # Run pdoc3 on changed Python files
    subprocess.run([
        "pdoc3",
        "--html",
        "--output-dir", "docs/api",
        "src/"
    ])

    # Stage generated docs
    subprocess.run(["git", "add", "docs/api/"])

    return 0

if __name__ == "__main__":
    sys.exit(generate_docs())
```

---

### 1.5 AutoGPT: Observability Integration

**Pattern**: Third-party telemetry via instrumentation libraries

```python
# Integration with Graphsignal
import graphsignal

# Initialize tracing
graphsignal.configure(
    api_key=os.environ['GRAPHSIGNAL_API_KEY'],
    deployment='autogpt-production'
)

# AutoGPT automatically traced
python -m autogpt  # All operations traced to Graphsignal
```

**Captured Data**:
- LLM prompts and completions
- Memory operations (retrieve/add)
- Command executions
- Costs and latency
- Token usage

**Session Management**:
- Short-term memory: Buffer for recent context within session
- Long-term memory: Persisted externally (vector DB, local files)
- Memory continuity: Retained across sessions via mounted volumes

---

## Part 2: Comparison Matrix

| Feature | LangChain | AutoGPT | CrewAI | Pre-commit | Pytest |
|---------|-----------|---------|--------|------------|--------|
| **Hook System** | Mixin callbacks | Event bus | Telemetry decorators | Git hooks (bash/python) | Plugin decorators |
| **Lifecycle Events** | 30+ events (start/end/error for LLM/tool/chain/agent) | Session lifecycle | Crew/task/agent lifecycle | Git events (pre-commit, post-checkout) | Test collection/execution/reporting |
| **Data Format** | Dict (in-memory) | JSONL (Graphsignal) | OpenTelemetry | JSONL/JSON | Dict/XML |
| **Storage** | Callback manager | External platform | OpenTelemetry backend | File (.git/hooks/) | terminalreporter.stats |
| **Real-time** | Yes (streaming) | Yes (via platform) | Yes (via OTEL) | No (batch per commit) | No (batch per session) |
| **Pattern Detection** | No (manual in callback) | Yes (Graphsignal) | Yes (AgentOps, OpenLIT) | No | No |
| **Auto-Actions** | No | Partial (retry/memory) | Yes (agent adaptation) | Yes (pre-commit reject) | Partial (xfail/skip) |
| **Async Support** | Yes (`AsyncCallbackHandler`) | Yes | Yes | No | Limited |
| **Extensibility** | High (subclass handler) | Medium (platform-dependent) | High (custom OTEL) | High (custom scripts) | High (plugin system) |
| **Privacy** | Full control | Opt-in sharing | Anonymous by default | Local only | Local only |
| **Opt-out** | Don't pass callback | Platform config | `CREWAI_DISABLE_TELEMETRY=true` | Remove hook | N/A |

---

## Part 3: Best Practices

### 3.1 Common Patterns Across Projects

**1. Lifecycle Hook Triad: `start` / `end` / `error`**
- All frameworks use this pattern for trackable events
- Enables complete visibility into execution flow
- Supports error handling and recovery

**2. UUID-Based Run Tracking**
- LangChain: `run_id` + `parent_run_id` for nested calls
- CrewAI: Random crew keys for anonymization
- Pytest: `nodeid` for test identification

**3. Metadata/Tags for Context**
- LangChain: `tags`, `metadata` parameters
- Pytest: Markers (`@pytest.mark.slow`)
- Pre-commit: File type filtering

**4. Mixin Composition Over Inheritance**
- LangChain's 6 mixins allow selective override
- Better than monolithic base class
- Supports `ignore_llm`, `ignore_tool` flags for filtering

**5. Environment Variable Configuration**
- `CREWAI_DISABLE_TELEMETRY`
- `OTEL_SDK_DISABLED`
- `GRAPHSIGNAL_API_KEY`
- Enables runtime control without code changes

**6. JSONL for Append-Only Logs**
- Pre-commit, AutoGPT use JSONL for statistics
- Supports streaming analysis
- Easy to parse incrementally

---

### 3.2 Anti-Patterns to Avoid

**1. Blocking I/O in Hooks**
- LangChain: Use `AsyncCallbackHandler` for async operations
- Pytest: Hooks block test execution
- Solution: Write to queue, process async

**2. Storing Sensitive Data**
- CrewAI warning: Don't include PII in agent roles/tool names
- LangChain: Filter prompts/outputs before logging
- Solution: Redact or hash sensitive fields

**3. Tight Coupling to External Services**
- AutoGPT depends on Graphsignal for telemetry
- Solution: Abstract telemetry behind interface

**4. Over-Collection**
- Collecting unused data wastes storage/bandwidth
- Solution: Collect only actionable metrics

**5. No Versioning for Telemetry Schema**
- Breaking changes in telemetry format break analysis
- Solution: Include schema version in each event

**6. Ignoring Hook Execution Order**
- Pytest: `tryfirst` vs `trylast` matters for state
- Solution: Explicitly declare ordering requirements

---

### 3.3 Performance Considerations

**1. Minimal Overhead**
- LangChain callbacks: ~1-5ms per event
- Pytest hooks: Negligible for collection, measurable for reporting
- Pre-commit: Runs once per commit (acceptable latency)

**2. Batch vs Real-time**
- Real-time: LangChain streaming, OTEL exporters
- Batch: Pre-commit (per commit), pytest (per session)
- Hybrid: Buffer events, flush periodically

**3. Selective Activation**
- LangChain: `ignore_llm=True` to skip LLM callbacks
- CrewAI: Disable telemetry entirely
- Pytest: Custom markers to skip expensive hooks

**4. Memory Management**
- Callback handlers persist for session lifetime
- Solution: Periodically flush buffers to disk

**5. Network I/O**
- OpenTelemetry: Async exporters with retry
- Solution: Local buffer + background thread

---

## Part 4: Applicability to Claude Code

### 4.1 Patterns to Adopt

**1. Mixin-Based Hook Architecture (LangChain)**
```python
# .claude/hooks/base.py
class ToolManagerMixin:
    def on_tool_start(self, tool_name: str, run_id: str) -> None:
        pass

    def on_tool_end(self, tool_name: str, run_id: str, duration: float) -> None:
        pass

    def on_tool_error(self, tool_name: str, run_id: str, error: Exception) -> None:
        pass

class AgentManagerMixin:
    def on_agent_spawn(self, agent_name: str, task_id: str) -> None:
        pass

    def on_agent_checkpoint(self, agent_name: str, state: dict) -> None:
        pass

class BaseHookHandler(ToolManagerMixin, AgentManagerMixin):
    ignore_tools: bool = False
    ignore_agents: bool = False
```

**Adaptation**:
- Create mixins for: Tools, Agents, Files, Git, Tests
- Allow selective hooking via `ignore_*` flags
- Store run IDs in `.claude/logs/`

**Implementation Effort**: 2-3 days
- Day 1: Define base classes and mixins
- Day 2: Implement handlers for tool/agent events
- Day 3: Integrate with existing Claude Code workflow

---

**2. JSONL Event Log (Pre-commit, AutoGPT)**
```python
# .claude/hooks/logger.py
import json
from pathlib import Path
from datetime import datetime

class EventLogger:
    def __init__(self, log_path: Path = Path(".claude/logs/events.jsonl")):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event_type: str, data: dict):
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            **data
        }
        with self.log_path.open("a") as f:
            f.write(json.dumps(event) + "\n")
```

**Adaptation**:
- Log tool calls: `{"type": "tool_start", "tool": "Read", "file": "main.py"}`
- Log agent switches: `{"type": "agent_spawn", "agent": "tdd-guard"}`
- Log checkpoints: `{"type": "checkpoint", "state": {...}}`

**Implementation Effort**: 1 day
- Simple append-only logging
- Integrate with existing tool wrapper

---

**3. Statistics Aggregator (Pytest)**
```python
# .claude/hooks/stats.py
from collections import defaultdict

class StatisticsCollector(BaseHookHandler):
    def __init__(self):
        self.tool_usage = defaultdict(int)
        self.errors_by_tool = defaultdict(list)
        self.agent_spawn_counts = defaultdict(int)

    def on_tool_start(self, tool_name: str, run_id: str):
        self.tool_usage[tool_name] += 1

    def on_tool_error(self, tool_name: str, run_id: str, error: Exception):
        self.errors_by_tool[tool_name].append({
            "run_id": run_id,
            "error": str(error),
            "timestamp": datetime.now().isoformat()
        })

    def on_agent_spawn(self, agent_name: str, task_id: str):
        self.agent_spawn_counts[agent_name] += 1

    def generate_report(self) -> dict:
        return {
            "total_tool_calls": sum(self.tool_usage.values()),
            "most_used_tools": sorted(
                self.tool_usage.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
            "error_rate_by_tool": {
                tool: len(errors) / self.tool_usage[tool]
                for tool, errors in self.errors_by_tool.items()
            },
            "agent_usage": dict(self.agent_spawn_counts)
        }
```

**Adaptation**:
- Track which tools are used most frequently
- Identify error-prone operations
- Detect agent thrashing (too many spawns)

**Implementation Effort**: 2 days
- Day 1: Implement collector
- Day 2: Integrate with JSONL logger for persistence

---

**4. Auto-Checkpoint on Pattern Detection**
```python
# .claude/hooks/checkpointer.py
class AutoCheckpointer(BaseHookHandler):
    def __init__(self, threshold: int = 10):
        self.tool_calls_since_checkpoint = 0
        self.threshold = threshold

    def on_tool_end(self, tool_name: str, run_id: str, duration: float):
        self.tool_calls_since_checkpoint += 1

        # Auto-checkpoint every N tool calls
        if self.tool_calls_since_checkpoint >= self.threshold:
            self.create_checkpoint()
            self.tool_calls_since_checkpoint = 0

    def on_tool_error(self, tool_name: str, run_id: str, error: Exception):
        # Immediate checkpoint on error
        self.create_checkpoint()

    def create_checkpoint(self):
        # Save current state to .claude/checkpoints/
        checkpoint = {
            "timestamp": datetime.now().isoformat(),
            "tool_usage": dict(self.tool_usage),
            "errors": dict(self.errors_by_tool)
        }
        Path(f".claude/checkpoints/{datetime.now().timestamp()}.json").write_text(
            json.dumps(checkpoint, indent=2)
        )
```

**Adaptation**:
- Trigger checkpoint after N tool calls
- Trigger on first error in a sequence
- Store in `.claude/checkpoints/`

**Implementation Effort**: 1-2 days

---

### 4.2 What Would Need Adaptation

**1. OpenTelemetry Integration**
- CrewAI/LangChain use OTEL for standardized tracing
- Adaptation: Too heavyweight for Claude Code
- Alternative: Stick with JSONL logs, use sqlite for queries

**2. Async Callback Handlers**
- LangChain has `AsyncCallbackHandler` for non-blocking I/O
- Adaptation: Claude Code is synchronous, not needed yet
- Future: If we add background tasks, adopt async pattern

**3. External Platform Integration**
- AutoGPT/CrewAI rely on AgentOps, LangSmith, Graphsignal
- Adaptation: Not applicable, we want local-only analytics
- Alternative: Build simple dashboard reading JSONL logs

**4. Run ID Hierarchy**
- LangChain tracks `run_id` + `parent_run_id` for nested calls
- Adaptation: Claude Code has flat tool calls, simpler tracking
- Alternative: Use session ID + sequential counter

---

### 4.3 Implementation Effort Estimates

| Pattern | Complexity | Effort | Priority | ROI |
|---------|-----------|---------|----------|-----|
| Mixin-based hooks | Medium | 2-3 days | High | High (enables all features) |
| JSONL event logging | Low | 1 day | High | High (simple, actionable) |
| Statistics collector | Low | 2 days | High | High (surface insights) |
| Auto-checkpoint | Medium | 1-2 days | Medium | Medium (convenience) |
| Pattern detection (clustering) | High | 5-7 days | Low | Medium (nice-to-have) |
| Dashboard for logs | Medium | 3-4 days | Low | Low (JSONL grep works) |

**Total Effort for MVP**: ~6-8 days
- Day 1-3: Mixin hooks + JSONL logging
- Day 4-5: Statistics collector
- Day 6-8: Auto-checkpoint + integration testing

---

## Part 5: Recommendations for UTXOracle

### 5.1 Immediate Actions (Week 1)

**1. Create Hook Framework**
```bash
# File structure
.claude/hooks/
├── __init__.py
├── base.py          # BaseHookHandler, mixins
├── logger.py        # EventLogger (JSONL)
├── stats.py         # StatisticsCollector
└── checkpointer.py  # AutoCheckpointer
```

**2. Wrap Existing Tool Calls**
```python
# Pseudo-code integration
from .claude.hooks import EventLogger, StatisticsCollector

logger = EventLogger()
stats = StatisticsCollector()

def tool_wrapper(func):
    def wrapper(*args, **kwargs):
        run_id = str(uuid.uuid4())
        tool_name = func.__name__

        # Log start
        logger.log("tool_start", {
            "tool": tool_name,
            "run_id": run_id,
            "args": args
        })
        stats.on_tool_start(tool_name, run_id)

        try:
            result = func(*args, **kwargs)
            logger.log("tool_end", {
                "tool": tool_name,
                "run_id": run_id,
                "success": True
            })
            stats.on_tool_end(tool_name, run_id, duration=...)
            return result
        except Exception as e:
            logger.log("tool_error", {
                "tool": tool_name,
                "run_id": run_id,
                "error": str(e)
            })
            stats.on_tool_error(tool_name, run_id, e)
            raise
    return wrapper
```

**3. Enable Opt-out**
```bash
# .claude/.env
CLAUDE_CODE_TELEMETRY=false
```

---

### 5.2 Medium-term Enhancements (Month 1)

**1. Pattern Detection**
- Analyze JSONL logs for common sequences
- Detect tool call loops (same tool called 5+ times consecutively)
- Flag error clusters (same error in <5 min window)

**2. Smart Checkpointing**
- Checkpoint before risky operations (git commit, file delete)
- Checkpoint after successful task completion
- Auto-recovery: Load last checkpoint on error

**3. Agent Learning**
- Track which agents succeed/fail at which tasks
- Recommend agent for new tasks based on history
- Auto-tune agent selection thresholds

---

### 5.3 Long-term Vision (Month 3+)

**1. Self-Optimizing Skills**
- Skills report their own usage statistics
- Claude Code learns which Skills save most tokens
- Auto-suggest Skill creation for repetitive patterns

**2. Anomaly Detection**
- ML model trained on normal execution patterns
- Flag unusual sequences (potential bugs/inefficiencies)
- Alert on performance degradation

**3. Explainable AI**
- Visualize decision trees for agent selection
- Show why a particular tool was chosen
- Trace token usage back to source patterns

---

## Appendix A: Key References

### Documentation
- [LangChain Callbacks](https://python.langchain.com/docs/concepts/callbacks/)
- [CrewAI Telemetry](https://docs.crewai.com/en/telemetry)
- [Pytest Hooks](https://docs.pytest.org/en/stable/how-to/writing_hook_functions.html)
- [Pre-commit Framework](https://pre-commit.com/)

### Code Repositories
- [langchain-ai/langchain](https://github.com/langchain-ai/langchain) - `libs/core/langchain_core/callbacks/base.py`
- [joaomdmoura/crewAI](https://github.com/joaomdmoura/crewAI) - Telemetry implementation
- [pytest-dev/pytest](https://github.com/pytest-dev/pytest) - `src/_pytest/hookspec.py`
- [pre-commit/pre-commit-hooks](https://github.com/pre-commit/pre-commit-hooks)

### Articles
- [Automate Python Documentation with Pre-commit Hooks](https://towardsdatascience.com/automate-your-python-code-documentation-with-pre-commit-hooks-35c7191949a4/)
- [LangChain Observability Guide](https://last9.io/blog/langchain-observability/)
- [Understanding Pytest Hooks](https://pytest-with-eric.com/hooks/pytest-hooks/)

---

## Appendix B: Implementation Checklist

- [ ] Create `.claude/hooks/` directory structure
- [ ] Implement `BaseHookHandler` with mixins
- [ ] Implement `EventLogger` (JSONL)
- [ ] Implement `StatisticsCollector`
- [ ] Wrap existing tool calls with hooks
- [ ] Add environment variable opt-out
- [ ] Test with sample workflow
- [ ] Implement `AutoCheckpointer`
- [ ] Add pattern detection (clustering)
- [ ] Create simple CLI for log analysis
- [ ] Document usage in CLAUDE.md
- [ ] Add to Skills framework

---

**Research completed**: 2025-10-19
**Next steps**: Present to user, get feedback, prioritize implementation
