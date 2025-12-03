# Feature Specification: Real-time Mempool Whale Detection

**Feature Branch**: `005-mempool-whale-realtime`
**Created**: 2025-11-07
**Status**: Draft
**Input**: User description: "Build a real-time mempool whale detection system that analyzes unconfirmed Bitcoin transactions to provide predictive whale flow signals 10-20 minutes before block confirmation. The system should leverage the existing local mempool.space WebSocket API (ws://localhost:8999/ws/track-mempool-tx) to monitor incoming transactions in real-time, classify them using the existing WhaleFlowDetector logic, and emit alerts for significant whale movements (>100 BTC). The system must provide: 1) WebSocket client for real-time mempool transaction stream, 2) Integration with existing whale flow classification logic, 3) Predictive signals with confidence scores based on fee urgency and RBF status, 4) Dashboard extension showing pending whale flows separate from confirmed ones, 5) Historical correlation tracking between mempool predictions and actual confirmed flows. Key requirements: Zero additional infrastructure (reuse existing mempool.space stack), <1 second latency from transaction broadcast to signal generation, memory-efficient streaming architecture that doesn't store full mempool, graceful degradation if mempool.space WebSocket is unavailable."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Real-time Whale Movement Detection (Priority: P1)

As a trader monitoring Bitcoin markets, I want to receive immediate alerts when large whale transactions (>100 BTC) appear in the mempool, so I can anticipate market movements 10-20 minutes before these transactions are confirmed on-chain and potentially impact prices.

**Why this priority**: This is the core MVP functionality that delivers immediate value - providing predictive signals that give traders a 10-20 minute advance warning of significant capital movements. Without this, there is no predictive advantage over existing confirmed block analysis.

**Independent Test**: Can be fully tested by broadcasting a test transaction to the mempool and verifying that an alert is generated within 1 second, delivering predictive value before block confirmation.

**Acceptance Scenarios**:

1. **Given** the mempool monitoring system is active, **When** a transaction involving exchange addresses with value >100 BTC enters the mempool, **Then** a whale alert is generated within 1 second with classification (inflow/outflow/internal)
2. **Given** a whale transaction is detected in mempool, **When** the transaction is later confirmed in a block, **Then** the predicted flow direction matches the actual confirmed flow direction
3. **Given** multiple whale transactions enter mempool simultaneously, **When** processing the stream, **Then** all transactions >100 BTC generate alerts without missing any

---

### User Story 2 - Fee-based Urgency Scoring (Priority: P2)

As a trader analyzing whale movements, I want to understand the urgency of each whale transaction based on its fee rate and Replace-By-Fee (RBF) status, so I can prioritize which signals are most likely to confirm quickly and impact the market sooner.

**Why this priority**: Fee urgency provides crucial context about when a whale movement will likely confirm. High-fee transactions indicate urgency and will confirm in the next 1-2 blocks, while low-fee transactions might take hours or get dropped, making this essential for timing trading decisions.

**Independent Test**: Can be tested by submitting transactions with different fee rates and verifying that urgency scores correctly reflect expected confirmation times.

**Acceptance Scenarios**:

1. **Given** a whale transaction with high fee rate (>50 sat/vB), **When** calculating urgency score, **Then** the signal shows high urgency (>0.8) and estimated confirmation within 1-2 blocks
2. **Given** a whale transaction with low fee rate (<5 sat/vB), **When** calculating urgency score, **Then** the signal shows low urgency (<0.3) with warning about potential non-confirmation
3. **Given** a whale transaction with RBF enabled, **When** displaying the alert, **Then** the signal indicates the transaction could be replaced and confidence is adjusted accordingly

---

### User Story 3 - Dashboard Visualization of Pending vs Confirmed Flows (Priority: P2)

As a trader using the whale detection dashboard, I want to see pending mempool whale flows displayed separately from confirmed flows, with clear visual distinction and real-time updates as transactions move from pending to confirmed status.

**Why this priority**: Visual separation of predictive (mempool) vs confirmed signals is critical for traders to understand which signals are actionable predictions vs historical data. This transparency builds trust in the predictive system.

**Independent Test**: Can be tested by verifying that the dashboard shows two distinct sections - one for pending mempool transactions and one for confirmed transactions, with transactions moving between sections when confirmed.

**Acceptance Scenarios**:

1. **Given** whale transactions exist in both mempool and confirmed states, **When** viewing the dashboard, **Then** pending transactions appear in a separate "Mempool Predictions" section with different visual styling
2. **Given** a pending whale transaction gets confirmed, **When** the block is mined, **Then** the transaction moves from "Mempool Predictions" to "Confirmed Flows" within 10 seconds
3. **Given** a pending transaction is replaced via RBF or dropped, **When** this occurs, **Then** the transaction is removed from "Mempool Predictions" with appropriate status update

---

### User Story 4 - Historical Correlation Tracking (Priority: P3)

As a system operator evaluating prediction accuracy, I want to track the historical correlation between mempool predictions and actual confirmed flows, so I can measure the system's predictive accuracy and identify patterns in false positives or changes.

**Why this priority**: While not essential for MVP operation, correlation tracking is crucial for building confidence in the system and optimizing prediction thresholds based on real performance data.

**Independent Test**: Can be tested by running the system for 24 hours and verifying that correlation metrics are calculated correctly by comparing logged predictions against confirmed outcomes.

**Acceptance Scenarios**:

1. **Given** the system has been running for 24+ hours, **When** viewing correlation metrics, **Then** the dashboard shows prediction accuracy percentage, false positive rate, and average prediction lead time
2. **Given** 100 mempool predictions have been made, **When** analyzing outcomes, **Then** the system reports what percentage confirmed as predicted, changed, or were dropped
3. **Given** historical correlation data exists, **When** a new prediction is made, **Then** the confidence score is adjusted based on recent prediction accuracy for similar transaction patterns

---

### User Story 5 - Graceful Degradation (Priority: P3)

As a system operator, I want the whale detection system to gracefully handle unavailability of the mempool WebSocket connection, falling back to polling or alerting operators while maintaining confirmed block analysis functionality.

**Why this priority**: While the real-time WebSocket is the primary data source, the system must remain partially operational if this connection fails, ensuring core whale detection on confirmed blocks continues.

**Independent Test**: Can be tested by disconnecting the WebSocket connection and verifying that appropriate alerts are generated and confirmed block analysis continues.

**Acceptance Scenarios**:

1. **Given** the WebSocket connection is lost, **When** attempting to reconnect, **Then** the system retries with exponential backoff and logs warnings about degraded predictive capability
2. **Given** WebSocket is unavailable for >5 minutes, **When** operating in degraded mode, **Then** the dashboard clearly indicates "Mempool Predictions Unavailable" while confirmed analysis continues
3. **Given** WebSocket connection is restored, **When** reconnection succeeds, **Then** mempool monitoring resumes automatically with a log entry noting service restoration

---

### Edge Cases

- What happens when a whale transaction is detected but then replaced via RBF with different parameters? → System updates the existing prediction with new parameters and flags it as "modified"
- How does the system handle reorg scenarios where confirmed transactions become unconfirmed again?
- What occurs if mempool size exceeds memory limits during high congestion periods? → System drops low-fee transactions when memory reaches 400MB (80% of 500MB limit)
- How are potential double-spend attempts by whales identified and flagged?
- What happens if the fee market suddenly spikes, affecting all urgency calculations?

## Clarifications

### Session 2025-11-07

- Q: When a whale transaction is detected in the mempool, how should alerts be delivered to traders? → A: Push notifications to dashboard (WebSocket broadcast) with optional webhooks (future: Redis pub/sub for NautilusTrader)
- Q: Which specific mempool.space API endpoint should be used for real-time transaction monitoring? → A: WebSocket API /ws/track-mempool-tx (transaction events)
- Q: How long should mempool prediction history be retained for correlation analysis? → A: 90 days (quarterly performance metrics)
- Q: When a whale transaction with RBF enabled is replaced with different parameters, how should the system handle the prediction? → A: Update existing prediction with new parameters and flag as "modified"
- Q: At what memory usage level should the system begin dropping low-priority (low-fee) whale transactions to maintain performance? → A: 400MB (80% of 500MB limit)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST monitor real-time mempool transactions via WebSocket connection to mempool.space /ws/track-mempool-tx endpoint
- **FR-002**: System MUST classify transactions as whale movements when value exceeds 100 BTC threshold
- **FR-003**: System MUST identify whether whale transactions involve known exchange addresses
- **FR-004**: System MUST generate predictive signals within 1 second of transaction entering mempool and broadcast via WebSocket to connected dashboard clients
- **FR-005**: System MUST calculate confidence scores based on transaction fee rate and RBF status
- **FR-006**: System MUST track correlation between mempool predictions and eventual confirmed outcomes
- **FR-007**: System MUST visually distinguish pending mempool predictions from confirmed flows in dashboard
- **FR-008**: System MUST maintain memory usage under 500MB limit by streaming rather than storing full mempool, dropping low-fee transactions at 400MB threshold
- **FR-009**: System MUST provide graceful degradation when WebSocket connection is unavailable
- **FR-010**: System MUST estimate confirmation time based on current fee market conditions
- **FR-011**: System MUST update pending transactions to confirmed status when blocks are mined
- **FR-012**: System MUST remove or flag transactions that are dropped from mempool
- **FR-013**: System MUST calculate and display urgency scores (0.0-1.0) for each whale transaction
- **FR-014**: System MUST persist prediction history for correlation analysis with 90-day retention for quarterly performance metrics
- **FR-015**: System MUST alert operators if prediction accuracy falls below acceptable threshold
- **FR-016**: System MUST support optional webhook notifications for external system integration (future: Redis pub/sub for NautilusTrader compatibility)
- **FR-017**: System MUST update existing predictions when RBF transactions are replaced, flagging them as "modified" while preserving prediction continuity
- **FR-018**: System MUST implement memory pressure handling by dropping low-fee transactions at 400MB threshold to prevent exceeding 500MB limit

### Key Entities *(include if feature involves data)*

- **MempoolWhaleSignal**: Represents a predictive whale signal from unconfirmed transaction (transaction_id, flow_type, btc_value, fee_rate, urgency_score, rbf_enabled, detection_timestamp, predicted_confirmation_block)
- **PredictionOutcome**: Tracks result of each prediction (prediction_id, predicted_flow, actual_outcome, confirmation_time, accuracy_score)
- **UrgencyMetrics**: Real-time fee market data for urgency calculation (current_block_height, fee_percentiles, estimated_blocks_to_confirmation)
- **CorrelationStats**: Aggregated accuracy metrics (time_period, total_predictions, confirmed_as_predicted, false_positives, average_lead_time)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Whale transactions (>100 BTC) are detected and alerts generated within 1 second of mempool entry in 95% of cases
- **SC-002**: Predictive signals provide 10-20 minute advance warning before block confirmation for 90% of whale transactions
- **SC-003**: System processes continuous mempool stream while maintaining memory usage below 500MB
- **SC-004**: Prediction accuracy (correlation between predicted and actual flow direction) exceeds 80% over 7-day period
- **SC-005**: Dashboard updates pending transaction status to confirmed within 10 seconds of block confirmation
- **SC-006**: High-urgency transactions (top 10% fee rate) confirm within predicted timeframe 85% of the time
- **SC-007**: System successfully reconnects and resumes monitoring within 30 seconds of WebSocket availability
- **SC-008**: False positive rate (whale signals that don't confirm or change direction) remains below 20%
- **SC-009**: Operators receive alerts within 1 minute when prediction accuracy drops below 70% threshold
- **SC-010**: Historical correlation data loads and displays within 2 seconds for any selected time period up to 90 days

## Assumptions

- Fee market conditions follow typical patterns (sudden 10x spikes are rare)
- Exchange address list remains relatively stable (updates weekly, not minutely)
- Mempool size stays within typical ranges (<300MB in extreme congestion)
- WebSocket connection has reasonable stability (brief outages, not hours-long)
- RBF usage patterns remain consistent with current Bitcoin network behavior
- Block time averages ~10 minutes (not considering significant hashrate changes)