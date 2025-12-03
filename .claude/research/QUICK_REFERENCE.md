# Quick Reference: Best Practices Implementation

**Last Updated**: 2025-10-19
**Full Report**: See `web_best_practices.md`

---

## Quick Wins (Implement First)

### 1. Pre-commit Framework (2 hours)

```bash
# Install
uv pip install pre-commit

# Create .pre-commit-config.yaml
cat > .pre-commit-config.yaml <<'EOF'
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: ['--maxkb=1000']
EOF

# Install and test
pre-commit install
pre-commit run --all-files
```

### 2. Post-commit Statistics (1 hour)

```bash
# Create stats collector
mkdir -p .claude/hooks
cat > .claude/hooks/collect_stats.py <<'EOF'
#!/usr/bin/env python3
import json, subprocess
from datetime import datetime
from pathlib import Path

stats_file = Path(".claude/logs/tool_usage.jsonl")
stats_file.parent.mkdir(parents=True, exist_ok=True)

sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
files = subprocess.check_output(
    ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"]
).decode().strip().split("\n")

stats = {
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "sha": sha[:8],
    "files_changed": len(files),
}

with stats_file.open("a") as f:
    f.write(json.dumps(stats) + "\n")
EOF

chmod +x .claude/hooks/collect_stats.py

# Add to .pre-commit-config.yaml
cat >> .pre-commit-config.yaml <<'EOF'
  - repo: local
    hooks:
      - id: collect-stats
        name: Collect commit statistics
        entry: python .claude/hooks/collect_stats.py
        language: python
        stages: [post-commit]
        always_run: true
        pass_filenames: false
EOF

pre-commit install --hook-type post-commit
```

### 3. Git Checkpoint Aliases (30 minutes)

```bash
# Add to ~/.gitconfig
git config --global alias.save '!f() { \
    git add -A && \
    git commit -m "CHECKPOINT: ${1:-$(date +%Y-%m-%d_%H:%M:%S)}" && \
    git tag "save-$(date +%s)" && \
    git reset HEAD~1; \
}; f'

git config --global alias.saves '!git tag -l "save-*" | sort -r | head -10'

git config --global alias.load '!f() { \
    git stash && \
    git checkout $1 && \
    git reset --soft HEAD~1; \
}; f'

# Usage:
# git save "Experimenting with feature X"
# git saves  # List checkpoints
# git load save-1729334625  # Restore
```

---

## Telemetry Best Practices

### The 6 Principles

1. **Be Intentional**: Create tracking plan (what & why)
2. **Transparency**: Document in README, show notice
3. **Easy Opt-out**: Env var, CLI flag, config file
4. **Don't Slow Down**: Best-effort, non-blocking
5. **Collect Environment**: OS, version (not PII)
6. **Prepare for Scale**: Local logs first

### Opt-In vs Opt-Out

- **Local logs**: Opt-OUT (default enabled, `UTXORACLE_TELEMETRY=0` to disable)
- **Cloud telemetry**: Opt-IN (explicit consent required)

### Storage Format

Use **JSONL** (JSON Lines):

```jsonl
{"timestamp":"2025-10-19T10:23:45Z","event":"command","command":"utxoracle","duration_sec":2.34}
{"timestamp":"2025-10-19T10:25:12Z","event":"test_run","tests_passed":23,"tests_failed":0}
```

---

## Checkpoint Patterns

### When to Checkpoint vs Commit

| Situation | Checkpoint | Commit |
|-----------|------------|--------|
| Code doesn't compile | ✅ | ❌ |
| Experiment/prototype | ✅ | ❌ |
| Tests passing | ❌ | ✅ |
| Ready to share | ❌ | ✅ |

### Agent Checkpoints (LangGraph)

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

checkpointer = InMemorySaver()
agent = create_react_agent(
    model="claude-3-7-sonnet",
    tools=[my_tool],
    checkpointer=checkpointer,
)

config = {"configurable": {"thread_id": "session_001"}}
response = agent.invoke({"messages": [...]}, config)
```

---

## Context Management

### 3 Strategies

1. **Compaction**: Summarize old context, keep recent
2. **Trimming**: Keep last N messages only
3. **External Memory**: Store facts outside context

### Anthropic's Memory Pattern

```python
# Store outside context
agent.write_file(".claude/memory/config.txt", "...")

# Retrieve later (doesn't use context window)
config = agent.read_file(".claude/memory/config.txt")
```

---

## Self-Improvement Patterns

### Reflection Loop

```
Execute Task → Collect Feedback → Analyze Patterns → Update Strategy → Repeat
```

### Improvement Triggers

- **Error threshold**: Same error 3+ times
- **Performance**: Latency >2x baseline
- **Confidence**: <0.7 on 5+ tasks

### Example

```python
def auto_improve():
    stats = analyze_recent_stats(hours=24)

    if stats["error_rate"] > 0.05:  # >5% errors
        error_analysis = analyze_error_patterns()
        apply_improvement(error_analysis["most_common_error"])

    if stats["avg_duration"] > stats["baseline_duration"] * 1.5:
        run_profiler()
        suggest_optimizations()
```

---

## Metrics to Collect

### ✅ Safe to Collect

- Commit frequency
- Files changed (count)
- Test results (pass/fail, duration)
- Command usage
- Performance metrics
- Error types (no stack traces)

### ❌ Never Collect

- File contents
- Full commit messages (may contain secrets)
- Author names/emails
- Branch names (may be sensitive)
- Diff output
- Stack traces

---

## Tools Comparison

| Tool | Purpose | Best For | Language |
|------|---------|----------|----------|
| **pre-commit** | Hook management | Python projects | Python |
| Husky | Hook management | JS/Node projects | JavaScript |
| Lefthook | Fast hooks | Any project | Go |
| git-stats | Git analytics | Personal tracking | JavaScript |

**Recommendation**: `pre-commit` (Python-native, zero JS deps)

---

## Quick Commands

```bash
# Pre-commit
pre-commit install                    # Setup hooks
pre-commit run --all-files            # Run on all files
pre-commit run --hook-stage post-commit  # Test post-commit hooks
pre-commit autoupdate                 # Update hook versions

# Git checkpoints
git save "Experiment: WebGL renderer" # Save checkpoint
git saves                             # List checkpoints
git load save-1729334625              # Restore checkpoint
git rmsave save-1729334625            # Delete checkpoint

# Analytics
python .claude/scripts/analyze_stats.py  # Analyze tool usage
cat .claude/logs/tool_usage.jsonl | jq  # Pretty-print logs

# Telemetry opt-out
export UTXORACLE_TELEMETRY=0          # Disable logging
```

---

## Resources

- **Full Report**: `.claude/research/web_best_practices.md`
- **Pre-commit Docs**: https://pre-commit.com
- **Anthropic Context Engineering**: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- **LangGraph Checkpoints**: https://langchain-ai.github.io/langgraph/agents/agents/
- **Telemetry Best Practices**: https://marcon.me/articles/cli-telemetry-best-practices/

---

## Next Steps

1. [ ] Implement pre-commit framework (Quick Win #1)
2. [ ] Add post-commit stats hook (Quick Win #2)
3. [ ] Setup Git checkpoint aliases (Quick Win #3)
4. [ ] Create tracking plan document
5. [ ] Add telemetry opt-out to README
6. [ ] Implement basic reflection pattern in agents

**Total Estimated Time**: 3.5 hours
**Expected ROI**: 60-80% reduction in manual tracking, automated quality
