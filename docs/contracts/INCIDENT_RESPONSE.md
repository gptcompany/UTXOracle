# INCIDENT_RESPONSE.md
# Defines the operator procedures and structured incident reporting for tier-1 surfaces.
# Frozen per spec-059.

## Overview
This document defines how to respond to critical and fatal alerts affecting tier-1 execution surfaces. Every incident of `critical` or `fatal` severity must be documented using the structured incident artifact model defined here.

## Minimum Runbook Set

### 1. Stale Live Snapshot
- **Trigger**: `live_snapshot_freshness` >= 30s
- **Severity**: `fatal`
- **Immediate Action**:
    1. Check `utxoracle-live-compose.service` logs.
    2. Verify Bitcoin Core RPC responsiveness (`bitcoin-cli getblockchaininfo`).
    3. Check `source_clients.py` status for connectivity issues to Electrum servers.
- **Recovery Confirmation**: `live_snapshot_freshness` < 15s for 2 consecutive reads.
- **Execution Consequence**: Immediate transition to `halted`.

### 2. Tier-1 Endpoint Failure
- **Trigger**: Any tier-1 endpoint returns 5xx or is unreachable for > 30s.
- **Severity**: `fatal`
- **Immediate Action**:
    1. Check `utxoracle-api.service` status and logs.
    2. Verify uvicorn/gunicorn process is running.
    3. Review upstream dependencies (QuestDB, Bitcoin Core).
- **Recovery Confirmation**: Endpoint returns 200 with valid payload for 3 consecutive reads.
- **Execution Consequence**: Immediate transition to `halted`.

### 3. Bundle or Signal Sequence Gap
- **Trigger**: `sequence_id` non-monotonic or gap > 1.
- **Severity**: `fatal`
- **Immediate Action**:
    1. Verify `bundle_writer` or `signal_writer` processes.
    2. Check QuestDB write logs for errors.
    3. Inspect the last known good sequence ID in storage.
- **Recovery Confirmation**: Monotonic sequence resumes for 5 consecutive writes/reads.
- **Execution Consequence**: Immediate transition to `halted`.

### 4. Upstream Divergence Spike
- **Trigger**: Local vs upstream price/metric disagreement exceeds threshold.
- **Severity**: `critical`
- **Immediate Action**:
    1. Check BRK (Block Repository) sync status.
    2. Verify electrs/index responsiveness.
    3. Compare data with external explorers (mempool.space).
- **Recovery Confirmation**: Divergence falls within allowed threshold for 3 consecutive checks.
- **Execution Consequence**: Transitions to `manage_only`.

### 5. QuestDB Unavailable
- **Trigger**: QuestDB health check fails or query timeout > 5s.
- **Severity**: `critical`
- **Immediate Action**:
    1. Check QuestDB process and resource usage (CPU, Disk).
    2. Verify disk space on the QuestDB data volume.
    3. Check connection pool status in the API logs.
- **Recovery Confirmation**: QuestDB responds within 1s for 3 consecutive health checks.
- **Execution Consequence**: Transitions to `manage_only` (materialized data may be stale).

### 6. Restatement Affecting Execution
- **Trigger**: Restatement artifact with severity `critical` published for tier-1 surface.
- **Severity**: `critical`
- **Immediate Action**:
    1. Review the restatement artifact to understand the scope of the error.
    2. Assess impact on current positions in Nautilus Trader.
    3. Decide whether to accept the risk or wait for full data correction.
- **Recovery Confirmation**: Restatement resolved or explicitly accepted with documented risk and expiration.
- **Execution Consequence**: Transitions to `manage_only` until resolved or accepted.

### 7. Execution Status Inconsistent
- **Trigger**: `/api/execution/btc/status` unavailable or `execution_mode` contradicts tier-1 input evidence.
- **Severity**: `fatal`
- **Immediate Action**:
    1. Verify execution-state derivation logic in `api/routes/live.py`.
    2. Manually check tier-1 input freshness/integrity.
    3. Compare individual input states with the aggregate status.
- **Recovery Confirmation**: Execution status returns consistent state matching tier-1 evidence for 3 consecutive reads.
- **Execution Consequence**: Immediate transition to `halted`.

## Incident Artifact Model

Every critical or fatal incident must produce a structured JSON artifact.

### Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "IncidentArtifact",
  "type": "object",
  "required": [
    "incident_id",
    "started_at",
    "trigger",
    "severity",
    "affected_surfaces",
    "execution_consequence",
    "operator_action",
    "recovery_confirmation"
  ],
  "properties": {
    "incident_id": {
      "type": "string",
      "description": "Unique identifier (e.g., INC-YYYYMMDD-NNN)"
    },
    "started_at": {
      "type": "string",
      "format": "date-time"
    },
    "ended_at": {
      "type": "string",
      "format": "date-time"
    },
    "trigger": {
      "type": "string",
      "description": "The alert name and metric value that triggered the incident."
    },
    "severity": {
      "enum": ["critical", "fatal"]
    },
    "affected_surfaces": {
      "type": "array",
      "items": { "type": "string" }
    },
    "execution_consequence": {
      "type": "string",
      "description": "Mode transition taken (e.g., trade_enabled -> halted)."
    },
    "operator_action": {
      "type": "string",
      "description": "Summary of actions taken by the operator."
    },
    "recovery_confirmation": {
      "type": "string",
      "description": "Evidence that recovery criteria were met."
    },
    "followup": {
      "type": "string",
      "description": "Fix applied, or explicit accepted-risk with expiration date."
    }
  }
}
```

## Evidence Requirements
Closure of an incident requires:
1. All recovery confirmation criteria for the triggered runbook are met.
2. The incident artifact is fully populated.
3. If risk was accepted, a follow-up ticket or expiration date must be recorded.
