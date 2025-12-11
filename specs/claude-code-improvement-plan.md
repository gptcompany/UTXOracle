# Claude Code Configuration Improvement Plan

**Date**: 2025-12-11
**Scope**: UTXOracle, nautilus_dev, LiquidationHeatmap
**Reference**: Official Anthropic Claude Code Documentation

---

## Executive Summary

Cross-validation analysis of 3 repositories against official Anthropic documentation reveals **6 critical issues** and **4 recommendations** for improvement.

---

## Round 1: Critical Issues (Must Fix)

### Issue 1: Missing YAML Fields in Agent
**Repo**: UTXOracle
**File**: `.claude/agents/verbalized-sampling-analyzer.md`
**Problem**: Missing `model:` and `color:` fields in YAML frontmatter
**Impact**: Agent may use default model instead of opus; no visual distinction
**Fix**:
```yaml
---
name: verbalized-sampling-analyzer
description: ...
tools: Bash, Read
model: opus      # ADD
color: yellow    # ADD (unique color)
---
```

### Issue 2: Wrong Default Model in Settings
**Repo**: LiquidationHeatmap
**File**: `.claude/settings.local.json` (line 38)
**Problem**: `"model": "sonnet"` instead of `"model": "opus"`
**Impact**: Inconsistent with other repos; potentially lower capability
**Fix**: Change `"model": "sonnet"` to `"model": "opus"`

### Issue 3: Wrong Project References in Skills
**Repo**: LiquidationHeatmap
**Files**:
- `.claude/skills/github-workflow/SKILL.md`
- `.claude/skills/github-workflow/templates/pr_template.md`
- `.claude/skills/pydantic-model-generator/SKILL.md`
**Problem**: Skills reference "UTXOracle" instead of "LiquidationHeatmap"
**Impact**: Generated code/templates contain wrong project name
**Fix**: Replace all "UTXOracle" references with "LiquidationHeatmap"

### Issue 4: Missing Command File
**Repo**: LiquidationHeatmap
**File**: `.claude/commands/speckit.taskstoissues.md` (MISSING)
**Problem**: Command exists in UTXOracle and nautilus_dev but not LiquidationHeatmap
**Impact**: Cannot convert tasks to GitHub issues
**Fix**: Copy from UTXOracle `.claude/commands/speckit.taskstoissues.md`

---

## Round 2: Consistency Issues (Should Fix)

### Issue 5: Duplicate Agent Colors
**All Repos**: Multiple agents share same colors
**Impact**: Harder to visually distinguish agents in logs/UI

| Repo | Duplicate Colors |
|------|------------------|
| UTXOracle | green (2), purple (2) |
| nautilus_dev | blue (2), green (2), purple (2) |
| LiquidationHeatmap | green (2) |

**Recommendation**: Assign unique colors per repo:

**UTXOracle Proposed Colors**:
| Agent | Current | Proposed |
|-------|---------|----------|
| alpha-debug | purple | purple |
| alpha-evolve | green | green |
| alpha-visual | magenta | magenta |
| bitcoin-onchain-expert | orange | orange |
| data-streamer | blue | blue |
| mempool-analyzer | green | **teal** |
| tdd-guard | red | red |
| transaction-processor | purple | **indigo** |
| verbalized-sampling-analyzer | (none) | **yellow** |
| visualization-renderer | cyan | cyan |

**nautilus_dev Proposed Colors**:
| Agent | Current | Proposed |
|-------|---------|----------|
| alpha-debug | purple | purple |
| alpha-evolve | green | green |
| alpha-visual | magenta | magenta |
| nautilus-coder | purple | **indigo** |
| nautilus-data-pipeline-operator | green | **teal** |
| nautilus-docs-specialist | blue | blue |
| nautilus-live-operator | cyan | cyan |
| tdd-guard | red | red |
| test-runner | blue | **yellow** |

**LiquidationHeatmap Proposed Colors**:
| Agent | Current | Proposed |
|-------|---------|----------|
| alpha-debug | purple | purple |
| alpha-evolve | green | green |
| alpha-visual | magenta | magenta |
| data-engineer | green | **teal** |
| quant-analyst | blue | blue |
| tdd-guard | red | red |
| visualization-renderer | cyan | cyan |

### Issue 6: Inconsistent Agent Counts
**Analysis**:
| Repo | Agent Count | Purpose |
|------|-------------|---------|
| UTXOracle | 10 | Bitcoin price oracle |
| nautilus_dev | 9 | Trading strategies |
| LiquidationHeatmap | 7 | Liquidation visualization |

**Assessment**: Agent counts appropriate for each project scope. No action needed.

---

## Round 3: Best Practice Recommendations

### Recommendation 1: Add `permissionMode` to Security-Sensitive Agents
**Affected Agents**: alpha-debug, alpha-evolve (all repos)
**Reason**: These agents can write/edit code; explicit permission control recommended
**Proposed Addition**:
```yaml
permissionMode: default  # Explicit permission for code changes
```

### Recommendation 2: Standardize Agent Description Format
**Current State**: Mixed use of "Use proactively" vs "Use when"
**Best Practice (from official docs)**:
> Include both: (1) What it does (2) When to use it

**Template**:
```
"[Role description]. Use [proactively/when] [trigger condition]."
```

**Example Improvements**:
- Before: `"Data ingestion and pipeline specialist..."`
- After: `"Data ingestion and pipeline specialist. Use proactively for DuckDB schema design and ETL optimization."`

### Recommendation 3: Add `skills` Field to Complex Agents
**Affected**: visualization-renderer, data-streamer
**Reason**: These agents could benefit from auto-loading related skills
**Example**:
```yaml
skills: github-workflow, pytest-test-generator
```

### Recommendation 4: Create Shared Agent Base
**Proposal**: Extract common agents (alpha-debug, alpha-evolve, alpha-visual, tdd-guard) to a shared location
**Benefit**: Single source of truth for cross-repo agents
**Implementation Options**:
1. Symlinks to `/media/sam/1TB/claude-hooks-shared/agents/`
2. Git submodule
3. Copy script in CI/CD

---

## Implementation Priority Matrix

| Priority | Issue | Effort | Impact |
|----------|-------|--------|--------|
| P0 (Critical) | Issue 1: Missing YAML fields | Low | High |
| P0 (Critical) | Issue 2: Wrong model in settings | Low | High |
| P0 (Critical) | Issue 3: Wrong project references | Medium | High |
| P0 (Critical) | Issue 4: Missing command file | Low | Medium |
| P1 (Important) | Issue 5: Duplicate colors | Low | Low |
| P2 (Nice-to-have) | Rec 1: permissionMode | Low | Low |
| P2 (Nice-to-have) | Rec 2: Description format | Medium | Low |
| P3 (Future) | Rec 3: skills field | Low | Low |
| P3 (Future) | Rec 4: Shared agent base | High | Medium |

---

## Validation Checklist

After implementation, verify:

- [ ] All agents have `name`, `description`, `tools`, `model`, `color` fields
- [ ] All `model:` fields are `opus`
- [ ] No duplicate colors within same repo
- [ ] All skills reference correct project name
- [ ] All speckit commands present in all repos
- [ ] `settings.local.json` has `model: opus` in all repos
- [ ] Hooks infrastructure identical across repos

---

## Appendix: Official Documentation Reference

### Required Agent Fields
- `name`: lowercase, hyphens, max 64 chars
- `description`: max 1024 chars, include action + trigger

### Optional Agent Fields
- `tools`: comma-separated (omit to inherit all)
- `model`: `sonnet`, `opus`, `haiku`, or `inherit`
- `color`: visual distinction in UI
- `permissionMode`: `default`, `acceptEdits`, `bypassPermissions`, `plan`, `ignore`
- `skills`: comma-separated skill names to auto-load

### Valid Colors
`red`, `orange`, `yellow`, `green`, `teal`, `blue`, `indigo`, `purple`, `magenta`, `cyan`

---

## Implementation Log

### Implemented (2025-12-11)

| Item | Status | Notes |
|------|--------|-------|
| Issue 1: Missing YAML fields | ✅ Done | Added `model: opus`, `color: yellow` to verbalized-sampling-analyzer.md |
| Issue 2: Wrong model in settings | ✅ Done | Changed LiquidationHeatmap to `model: opus` |
| Issue 3: Wrong project references | ✅ Done | Updated github-workflow and pydantic-model-generator skills |
| Issue 4: Missing command file | ✅ Done | Copied speckit.taskstoissues.md to LiquidationHeatmap |
| Issue 5: Duplicate colors | ✅ Done | Unique colors per repo now |
| Rec 1: permissionMode | ✅ Done | Added to all alpha-* agents (9 files) |
| Rec 2: Description format | ⏭️ Skipped | Descriptions are fine per official docs |
| Rec 3: skills field | ✅ Done | Added to visualization-renderer, data-streamer |
| Rec 4: Shared agent base | 📝 Documented | See below |

### Color Mapping After Fix

**UTXOracle** (10 agents - all unique):
- alpha-debug: purple
- alpha-evolve: green
- alpha-visual: magenta
- bitcoin-onchain-expert: orange
- data-streamer: blue
- mempool-analyzer: **teal** (was green)
- tdd-guard: red
- transaction-processor: **indigo** (was purple)
- verbalized-sampling-analyzer: **yellow** (new)
- visualization-renderer: cyan

**nautilus_dev** (9 agents - all unique):
- alpha-debug: purple
- alpha-evolve: green
- alpha-visual: magenta
- nautilus-coder: **indigo** (was purple)
- nautilus-data-pipeline-operator: **teal** (was green)
- nautilus-docs-specialist: blue
- nautilus-live-operator: cyan
- tdd-guard: red
- test-runner: **yellow** (was blue)

**LiquidationHeatmap** (7 agents - all unique):
- alpha-debug: purple
- alpha-evolve: green
- alpha-visual: magenta
- data-engineer: **teal** (was green)
- quant-analyst: blue
- tdd-guard: red
- visualization-renderer: cyan

### Shared Agent Strategy (Rec 4)

**Current State**: Common agents (alpha-debug, alpha-evolve, alpha-visual, tdd-guard) are duplicated across repos.

**Recommended Future Approach**:

```
/media/sam/1TB/claude-hooks-shared/
├── hooks/          # Already shared
├── scripts/        # Already shared
└── agents/         # NEW - shared agents
    ├── alpha-debug.md
    ├── alpha-evolve.md
    ├── alpha-visual.md
    └── tdd-guard.md
```

**Implementation Options**:

1. **Symlinks** (Simplest):
   ```bash
   ln -sf /media/sam/1TB/claude-hooks-shared/agents/alpha-debug.md \
          /media/sam/1TB/UTXOracle/.claude/agents/alpha-debug.md
   ```
   - Pros: Zero maintenance, instant sync
   - Cons: Git doesn't follow symlinks well

2. **Copy Script** (Recommended):
   ```bash
   # sync-shared-agents.sh
   for repo in UTXOracle nautilus_dev LiquidationHeatmap; do
     cp /media/sam/1TB/claude-hooks-shared/agents/*.md \
        /media/sam/1TB/$repo/.claude/agents/
   done
   ```
   - Pros: Works with git, explicit control
   - Cons: Manual sync required

3. **Git Submodule** (Enterprise):
   - Pros: Version controlled
   - Cons: Complex for local-only repos

**Decision**: Defer to future. Current duplication is manageable for 3 repos.

---

*Generated by Claude Code Cross-Validation Analysis*
*Last updated: 2025-12-11*
