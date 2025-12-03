# Self-Improvement System Design

**Purpose**: Automated session analysis pipeline for continuous improvement through data-driven insights.

**Created**: 2025-10-20
**Status**: Design Phase
**Next**: SpecKit planning + Implementation

---

## 🎯 What (Objectives)

### Primary Goal
Build an automated system that captures, analyzes, and learns from every Claude Code session to identify improvement opportunities and prevent recurring issues.

### Key Capabilities

1. **Data Collection** (Automatic)
   - Token usage metrics (input, output, cache)
   - Cost tracking per session
   - Code changes (lines added/removed)
   - Context metadata (branch, task, agent)
   - Error events (blocks, failures, timeouts)
   - Tool usage patterns

2. **Data Correlation** (Automatic)
   - Join metrics + context bundles + events by `session_id`
   - Persist to queryable database (PostgreSQL)
   - Enable historical analysis across sessions

3. **Pattern Analysis** (LLM-powered)
   - Detect error patterns (recurring TDD blocks, test failures)
   - Identify cost inefficiencies (high token/low output)
   - Classify session outcomes (SUCCESS/PARTIAL/BLOCKED/FAILED)
   - Generate actionable learnings

4. **Continuous Feedback** (Automated)
   - Discord notifications for session summaries
   - Flagging of sessions needing human review
   - Optional Claude-powered deep analysis for complex cases

---

## 🤔 Why (Motivation)

### Problems Being Solved

#### Problem 1: Lost Context
**Current**: Dopo 1 mese, vedi solo numeri senza storia
```json
{"cost_usd": 2.50, "lines_changed": {"added": 0}}
```
❓ Perché ho speso $2.50 senza output?

**Solution**: Rich context capture
```json
{
  "cost_usd": 2.50,
  "context": {
    "task": "Debug TDD guard issue",
    "git_branch": "002-mempool-live-oracle"
  },
  "events": [
    {"type": "tdd_block", "count": 5}
  ],
  "outcome": "BLOCKED",
  "summary": "TDD guard blocked, switched to .txt rename approach",
  "learnings": ["TDD guard blocks non-production code"]
}
```
✅ Tra 1 mese: Sappiamo esattamente cosa è successo e perché!

#### Problem 2: Recurring Issues
**Current**: Same error happens multiple sessions, no detection

**Solution**: Pattern detection across sessions
- "TDD guard blocks refactoring without tests" (detected 8/10 sessions)
- "WebSocket tests timeout after 5 retries" (pattern: missing await)
- "Mempool analysis costs 3x average" (inefficient approach)

#### Problem 3: No Cost Attribution
**Current**: "$50/month on Claude Code" - but why?

**Solution**: Granular cost analysis
- Debugging sessions: $15 (30%)
- Feature implementation: $25 (50%)
- Documentation: $10 (20%)
- **Insight**: Debugging costs 2x per line vs implementation

#### Problem 4: Manual Post-Mortems
**Current**: After failure, manually try to remember what went wrong

**Solution**: Automated analysis
- Gemini analyzes every session (free, fast)
- Flags complex cases for Claude review
- Generates learnings database automatically

---

## 🛠️ Tech Stack

### Infrastructure

#### Data Storage
- **Files** (current):
  - `.claude/stats/session_metrics.jsonl` - Token/cost/context
  - `.claude/context_bundles/*.json` - Tool operations
  - `.claude/stats/session_events.jsonl` - Errors/blocks (NEW)

- **Database** (proposed):
  - **PostgreSQL** (local, self-hosted)
  - Location: `/media/sam/1TB/N8N_dev/postgres/`
  - Schema: 3 tables (sessions, operations, events)
  - Views: Aggregated analytics

#### Workflow Orchestration
- **n8n** (local instance)
- Location: `/media/sam/1TB/N8N_dev/`
- Tunnel: Cloudflare for webhook access
- Workflows: JSON-defined, version controlled

### Data Collection Layer

#### 1. StatusLine Monitor (Real-time)
- **File**: `.claude/scripts/context-monitor.py`
- **Trigger**: Every statusline refresh (~1-2 sec)
- **Captures**: Token usage, context %, cost, duration
- **Output**: Appends to `session_metrics.jsonl`

#### 2. Event Tracker (Error Capture)
- **File**: `.claude/hooks/session-outcome-tracker.py`
- **Trigger**: PostToolUse hook (after every tool)
- **Captures**: Errors, TDD blocks, hook blocks, timeouts
- **Output**: Appends to `session_events.jsonl`

#### 3. Context Bundle Builder (Existing)
- **File**: `.claude/hooks/context_bundle_builder.py`
- **Trigger**: PostToolUse hook
- **Captures**: Tool name, command, description, timestamp
- **Output**: Updates `context_bundles/<session_id>.json`

#### 4. Manual Outcome (Optional)
- **File**: `.claude/.session_outcome`
- **Trigger**: User creates at session end
- **Format**: Plain text or structured
- **Example**: `✅ SUCCESS: Implemented feature X`

### Analysis Layer

#### Phase 1: Gemini Analysis (Automatic, Free)
- **Trigger**: Webhook from SessionEnd hook or manual
- **Model**: Gemini 1.5 Flash (free tier, 1500 req/day)
- **Input**: Merged session data (metrics + bundles + events)
- **Output**: JSON analysis
  - `outcome`: SUCCESS/PARTIAL/BLOCKED/FAILED
  - `cost_efficiency`: Rating + cost per line
  - `error_analysis`: Patterns, root cause, retry count
  - `learnings`: Actionable insights (3-5 items)
  - `recommendations`: What to do next
  - `flags`: Needs review, high cost, pattern alert

#### Phase 2: Claude Review (Conditional, On-demand)
- **Trigger**: Manual or `flags.needs_claude_review == true`
- **Model**: Claude 4.5 Sonnet (current session context)
- **Input**: Gemini draft + transcript excerpts
- **Output**: Enhanced summary with narrative context
- **Token Cost**: ~500-2000 (only for 10% of sessions)

### Integration Layer

#### n8n Workflow Pipeline

```
┌─────────────────────────────────────────┐
│   WEBHOOK TRIGGER                       │
│   POST /webhook/claude-session-analysis │
│   Body: {session_id, trigger: auto}    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   1. DATA COLLECTION (Python)           │
│   - Read session_metrics.jsonl          │
│   - Read context_bundle JSON            │
│   - Read session_events.jsonl           │
│   - Merge by session_id                 │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   2. DB INGESTION (PostgreSQL)          │
│   - UPSERT sessions table               │
│   - INSERT operations (bulk)            │
│   - INSERT events (bulk)                │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   3. CONDITIONAL: Analyze?              │
│   If events ≥ 3 OR manual → YES         │
│   Else → Skip to notification           │
└──────────────┬──────────────────────────┘
               │
               ▼ (if YES)
┌─────────────────────────────────────────┐
│   4. GEMINI ANALYSIS (LLM)              │
│   - Build prompt with merged data       │
│   - Call Gemini API                     │
│   - Parse JSON response                 │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   5. SAVE ANALYSIS                      │
│   - Write .claude/reports/session_*.md  │
│   - UPDATE sessions.outcome_summary     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│   6. DISCORD NOTIFICATION               │
│   - Format embed (color by outcome)     │
│   - Post to #claude-sessions            │
└─────────────────────────────────────────┘
```

#### Webhook Receiver
- **File**: `.claude/hooks/webhook-trigger.sh` (SessionEnd)
- **Action**: `curl -X POST https://tunnel.example.com/webhook/...`
- **Payload**: `{session_id, timestamp, trigger_type}`

#### Database Schema
```sql
-- Core tables
sessions (session_id PK, metrics, context, outcome)
operations (id PK, session_id FK, operation details)
events (id PK, session_id FK, error/block details)

-- Analytics view
v_session_summary (aggregated stats + counts)
```

---

## 📊 Data Flow

### Correlation Strategy

**Primary Key**: `session_id` (UUID, consistent across all sources)

**Sources**:
1. `session_metrics.jsonl`: Latest entry with `session_id`
2. `context_bundles/20_oct_session_<session_id>.json`: Full session_id in object
3. `session_events.jsonl`: All entries with matching `session_id`
4. `.session_outcome`: Linked by timing (same session)

**Join Logic** (PostgreSQL):
```sql
SELECT
  s.*,
  COUNT(o.id) as ops_count,
  COUNT(e.id) as events_count,
  STRING_AGG(DISTINCT e.event_type, ', ') as event_types
FROM sessions s
LEFT JOIN operations o ON s.session_id = o.session_id
LEFT JOIN events e ON s.session_id = e.session_id
GROUP BY s.session_id;
```

---

## 🎯 Decision: Hybrid Two-Phase Analysis

### Why Hybrid?

**Problem**: Claude has full session context, external LLM doesn't

**Solution**: Use both strategically
- **Gemini** (90% of sessions): Fast, free, good for pattern/numerical analysis
- **Claude** (10% of sessions): Contextual understanding for complex cases

### Decision Tree

```
Session End
    │
    ▼
Gemini Analysis (automatic)
    │
    ├─ Simple success (lines >0, errors 0)
    │  └─> Discord notification → DONE
    │
    ├─ Complex/Blocked (errors >3 OR failed)
    │  └─> Save draft + flag for Claude review
    │
    └─ Manual review request
       └─> /review-session SESSIONID
           (Claude reads Gemini draft + adds context)
```

### Example Distribution

| Session Type | Frequency | Handler | Token Cost |
|--------------|-----------|---------|------------|
| Clean implementation | 60% | Gemini only | 0 |
| Minor issues (1-2 errors) | 25% | Gemini only | 0 |
| Debugging (3-5 errors) | 10% | Gemini + flag | 0 |
| Blocked/Failed (>5 errors) | 5% | Gemini → Claude | ~1000 |

**Total Token Savings**: ~90% vs Claude-only approach

---

## 🚀 Implementation Plan (for SpecKit)

### Phase 1: Data Collection (Week 1)
- [ ] Finalize `context-monitor.py` v2 (with metadata)
- [ ] Implement `session-outcome-tracker.py` (event capture)
- [ ] Test correlation across all 3 data sources
- [ ] Verify `session_id` consistency

### Phase 2: Database Setup (Week 1-2)
- [ ] PostgreSQL setup in `/media/sam/1TB/N8N_dev/`
- [ ] Run migration script (create tables)
- [ ] Test data ingestion from JSONL files
- [ ] Create analytics views

### Phase 3: n8n Workflow (Week 2)
- [ ] Build workflow nodes (6 nodes total)
- [ ] Test webhook trigger
- [ ] Configure Gemini API node
- [ ] Set up Discord notification
- [ ] Test end-to-end flow

### Phase 4: Gemini Integration (Week 2-3)
- [ ] Implement prompt template
- [ ] Test analysis quality on historical sessions
- [ ] Tune classification logic
- [ ] Validate JSON parsing

### Phase 5: Claude Review (Week 3)
- [ ] Create `/review-session` slash command
- [ ] Implement Gemini draft reader
- [ ] Test hybrid analysis
- [ ] Document when to use each

### Phase 6: Monitoring & Iteration (Week 4)
- [ ] Run on 20+ sessions
- [ ] Analyze Gemini accuracy
- [ ] Tune thresholds (when to flag for Claude)
- [ ] Document learnings

---

## 📈 Success Metrics

### Quantitative
- **Data Capture Rate**: 100% of sessions have all 3 data sources
- **Correlation Success**: 100% sessions joinable by `session_id`
- **Analysis Coverage**: 90%+ sessions auto-analyzed by Gemini
- **Token Savings**: 85-90% vs Claude-only approach
- **Cost per Analysis**: <$0.01 avg (mostly free via Gemini)

### Qualitative
- **Pattern Detection**: Identify recurring issues within 3 sessions
- **Actionability**: 80%+ learnings are specific and actionable
- **Time to Insight**: <5min from session end to Discord notification
- **Review Quality**: Claude-reviewed sessions have richer context

---

## 🔍 Inspiration: claude-flow

**Reference**: https://github.com/ruvnet/claude-flow/issues/419

**What to Learn**:
- How they implement session tracking
- Workflow automation patterns
- LLM integration approach
- Data persistence strategies

**Action**: Sub-agent analysis of `/media/sam/1TB/UTXOracle/CLAUDE_FLOW/`

---

## 🎯 Key Differentiators

### vs Manual Post-Mortems
- ✅ Automatic (zero manual effort)
- ✅ Consistent (same analysis criteria)
- ✅ Scalable (handles 100s of sessions)

### vs Claude-Only Analysis
- ✅ 90% token savings (Gemini handles bulk)
- ✅ Faster (Gemini Flash = 2-3 sec)
- ✅ Context where needed (Claude for complex 10%)

### vs Simple Logging
- ✅ Correlation (joins metrics + context + events)
- ✅ Pattern detection (across sessions)
- ✅ Actionable insights (not just data dumps)

---

## 📝 Open Questions (for SpecKit)

1. **DB Hosting**: PostgreSQL in Docker or native install?
2. **Webhook Security**: Token-based auth or Cloudflare Access?
3. **Retention Policy**: How long to keep raw JSONL vs DB entries?
4. **Gemini vs Claude**: Fine-tune threshold (when to escalate)?
5. **Discord Format**: Rich embeds or simple text?
6. **Historical Backfill**: Analyze past 672 sessions or start fresh?

---

## 🛡️ Security Considerations

### Data Sensitivity
- Session data may contain code snippets, file paths
- Store locally (not cloud DB)
- Webhook over Cloudflare tunnel (encrypted)

### API Keys
- Gemini API key in `.env` (not committed)
- Discord webhook URL in n8n config (not exposed)
- DB password in n8n credentials store

### Access Control
- PostgreSQL: localhost only (no external access)
- n8n: Cloudflare Access for webhook protection
- Discord: Private channel (#claude-sessions)

---

## 📚 References

### Internal Docs
- `.claude/scripts/CONTEXT_USAGE.md` - Context monitor v2 guide
- `.claude/scripts/OUTCOME_TRACKING.md` - Event tracking guide
- `.claude/prompts/session-analysis-prompt.md` - LLM analysis templates

### External
- [claude-flow Issue #419](https://github.com/ruvnet/claude-flow/issues/419)
- [Gemini API Docs](https://ai.google.dev/docs)
- [n8n Workflow Docs](https://docs.n8n.io/)

---

## 🎬 Next Steps

1. **Review this document** with fresh eyes
2. **Analyze claude-flow** implementation (sub-agent task)
3. **Create SpecKit spec** (`.specify/` format)
4. **Prioritize phases** (what to build first?)
5. **Prototype** Gemini analysis on 1 session manually
6. **Iterate** based on results

---

**Status**: Ready for SpecKit planning
**Owner**: ultrathink + Claude Code
**Timeline**: 4 weeks (phased rollout)
