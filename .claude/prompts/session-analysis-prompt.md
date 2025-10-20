# Session Analysis Prompt Template

**Purpose**: Analyze Claude Code session metrics to identify patterns, inefficiencies, and optimization opportunities.

**Input Data**: `.claude/stats/session_metrics.jsonl` (JSONL format)

---

## How to Use This Prompt

1. **Copy metrics data**:
   ```bash
   cat .claude/stats/session_metrics.jsonl | jq -s '.'
   ```

2. **Paste into any LLM** (Claude, ChatGPT, Gemini, etc.)

3. **Use one of the analysis templates below**

---

## Analysis Template 1: Single Session Review

```
Analyze this Claude Code session and provide insights.

**Session Metrics (JSONL)**:
[paste output from: cat .claude/stats/session_metrics.jsonl]

**Analysis Required**:

1. **Session Overview**
   - Total duration and cost
   - Token usage breakdown (input/output/cache)
   - Context consumption pattern

2. **Efficiency Analysis**
   - Cost per minute
   - Token efficiency (output/input ratio)
   - Cache hit rate

3. **Bottleneck Detection**
   - When did cost spike? (look at timestamps)
   - High context usage points (>80%)
   - Low productivity periods (high cost, no code changes)

4. **Recommendations**
   - Should I have used /compact earlier?
   - Are there token-wasting patterns?
   - Optimal session length for this task type?

**Output Format**: Markdown report with metrics table + 3-5 actionable recommendations.
```

---

## Analysis Template 2: Multi-Session Comparison

```
Compare multiple Claude Code sessions to identify trends and best practices.

**Sessions Data**:
[paste last N sessions or full file]

**Comparative Analysis**:

1. **Session Categorization**
   - Group by: session duration (<15m, 15-30m, >30m)
   - Group by: cost range (<$0.10, $0.10-$0.50, >$0.50)
   - Group by: task type (if identifiable from metadata)

2. **Pattern Detection**
   - Best session: highest productivity/cost ratio
   - Worst session: highest cost with minimal output
   - Average cost per productive minute

3. **Trends Over Time**
   - Is cost per session increasing/decreasing?
   - Are sessions getting longer or shorter?
   - Cache usage improving over time?

4. **Optimization Opportunities**
   - Which sessions should have been split into multiple?
   - Which sessions used too much cache creation?
   - Identify "sweet spot" session duration

**Output Format**: Comparison table + trend chart (ASCII art) + top 5 learnings.
```

---

## Analysis Template 3: Cost Optimization

```
Analyze session costs and provide optimization strategies.

**Cost Data**:
[paste session_metrics.jsonl]

**Cost Breakdown Required**:

1. **Token Economics**
   - Total spent: sum(cost_usd)
   - Average cost per session
   - Most expensive session (why?)
   - Cheapest productive session (how?)

2. **Cost Drivers**
   - Cache creation vs cache read ratio
   - Output tokens vs input tokens
   - Context bloat over time

3. **Savings Opportunities**
   - Estimated savings if cache_read > cache_creation
   - Potential savings from earlier /compact
   - Cost reduction from shorter sessions

4. **Budget Forecasting**
   - At current rate, monthly cost projection
   - Recommended session frequency
   - Cost per feature/task estimate

**Output Format**: Cost breakdown table + 3 specific actions to reduce costs by 20-40%.
```

---

## Analysis Template 4: Productivity Metrics

```
Analyze productivity and code output relative to session cost.

**Productivity Data**:
[paste session_metrics.jsonl]

**Metrics to Calculate**:

1. **Code Productivity**
   - Lines changed per dollar spent
   - Lines changed per minute
   - Net lines (additions - deletions) trend

2. **Time Efficiency**
   - Active coding time vs idle time (infer from timestamp gaps)
   - Average time per message/interaction
   - Session "sweet spot" (most productive duration)

3. **Value Analysis**
   - Which sessions had best ROI?
   - Correlation: duration vs productivity
   - Correlation: cost vs lines changed

4. **Recommendations**
   - Optimal session length for maximum productivity
   - When to take breaks (based on efficiency drop)
   - Task types best suited for Claude Code

**Output Format**: Productivity dashboard (ASCII) + efficiency score (0-100) + 5 actionable tips.
```

---

## Analysis Template 5: Quick Summary (One-Liner Queries)

Use these for quick insights without full analysis:

```
1. "What was my total spend across all sessions?"
   → sum(cost_usd) from session_metrics.jsonl

2. "What's my average cost per session?"
   → mean(cost_usd) from session_metrics.jsonl

3. "Which session had the highest context usage?"
   → max(context_percent) from session_metrics.jsonl

4. "How many total tokens have I used?"
   → sum(tokens.total) from session_metrics.jsonl

5. "What's my cache hit rate?"
   → sum(cache_read) / sum(cache_creation) from session_metrics.jsonl

6. "Most expensive session?"
   → session with max(cost_usd) - include timestamp and duration

7. "Longest session?"
   → session with max(duration_minutes)

8. "Am I getting more efficient over time?"
   → Compare avg(cost_usd) for first 10 vs last 10 sessions
```

---

## Data Extraction Examples

For LLMs that need structured data, use these commands:

```bash
# Last session only
cat .claude/stats/session_metrics.jsonl | tail -1 | jq .

# Last N sessions
cat .claude/stats/session_metrics.jsonl | tail -5 | jq -s '.'

# All sessions (if file is large, summarize first)
cat .claude/stats/session_metrics.jsonl | jq -s '.'

# Summary statistics (pre-computed)
cat .claude/stats/session_metrics.jsonl | jq -s '
{
  total_sessions: length,
  total_cost: (map(.cost_usd) | add),
  total_tokens: (map(.tokens.total) | add),
  avg_cost: (map(.cost_usd) | add / length),
  avg_duration: (map(.duration_minutes) | add / length),
  max_context: (map(.context_percent) | max)
}'

# Group by date
cat .claude/stats/session_metrics.jsonl | jq -s 'group_by(.timestamp[:10]) | map({date: .[0].timestamp[:10], sessions: length, total_cost: (map(.cost_usd) | add)})'
```

---

## Advanced Analysis: Custom Queries

If you want specific insights, adapt this template:

```
Analyze this Claude Code session data for [SPECIFIC GOAL].

**Data**:
[paste session_metrics.jsonl]

**Question**:
[Your specific question, e.g., "Why did session X cost 3x more than session Y?"]

**Context** (optional):
[Any additional context about what you were working on]

**Output Required**:
- Root cause analysis
- Quantitative comparison
- 2-3 actionable recommendations
```

---

## Automated Insights (Optional)

If you want recurring analysis, save this as a script:

```bash
#!/bin/bash
# .claude/scripts/quick-stats.sh
# Usage: ./quick-stats.sh

echo "📊 Quick Session Stats"
echo "====================="

TOTAL_COST=$(jq -s 'map(.cost_usd) | add' .claude/stats/session_metrics.jsonl)
TOTAL_SESSIONS=$(jq -s 'length' .claude/stats/session_metrics.jsonl)
AVG_COST=$(jq -s 'map(.cost_usd) | add / length' .claude/stats/session_metrics.jsonl)
TOTAL_TOKENS=$(jq -s 'map(.tokens.total) | add' .claude/stats/session_metrics.jsonl)

echo "Total sessions: $TOTAL_SESSIONS"
echo "Total cost: \$$TOTAL_COST"
echo "Avg cost/session: \$$AVG_COST"
echo "Total tokens: $TOTAL_TOKENS"

echo ""
echo "💡 Paste into LLM for deeper analysis:"
echo "cat .claude/stats/session_metrics.jsonl | jq -s '.'"
```

---

## Best Practices

1. **Analyze weekly** (not after every session) → More meaningful trends
2. **Save LLM insights** → Create `.claude/reports/analysis_YYYY-MM-DD.md`
3. **Track changes** → Compare reports over time
4. **Act on recommendations** → Adjust workflow based on findings

---

## Example Report Structure

When LLM generates analysis, save in this format:

```markdown
# Session Analysis Report - 2025-10-20

## 📊 Summary Statistics

| Metric | Value |
|--------|-------|
| Sessions analyzed | 12 |
| Total cost | $0.37 |
| Avg cost/session | $0.03 |
| Total tokens | 1,012,000 |
| Avg duration | 3.5 min |

## 🔍 Key Findings

1. **High cache creation in early sessions** → 82k tokens cached
2. **Good cache reuse in later messages** → Cache read: 82k tokens
3. **Low code output** → 0 lines changed (analysis/discussion task)

## 💡 Recommendations

1. ✅ **Continue current cache strategy** (creation → reuse working well)
2. ⚠️ **Consider /compact at 70% context** (currently reaching 42%)
3. 💰 **Session cost is optimal** ($0.37 for 3.5min = $0.11/min)

## 📈 Trend

Costs stable, cache usage efficient. No action needed.
```

---

## Summary

**Data Location**: `.claude/stats/session_metrics.jsonl`

**Analysis Workflow**:
1. Extract data → `cat .claude/stats/session_metrics.jsonl | jq -s '.'`
2. Choose template (above)
3. Paste into any LLM
4. Save insights to `.claude/reports/`
5. Act on recommendations

**LLM Agnostic**: ✅ Works with Claude, ChatGPT, Gemini, local models, etc.
