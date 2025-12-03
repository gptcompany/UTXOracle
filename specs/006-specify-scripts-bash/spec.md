# Feature Specification: Real-Time Whale Detection Dashboard

**Feature Branch**: `006-specify-scripts-bash`
**Created**: 2025-11-25
**Status**: Draft
**Input**: User description: "Create a real-time whale detection dashboard to visualize Bitcoin whale transactions (>100 BTC) with live WebSocket updates, net flow charts, urgency scoring gauge, and transaction feed table. The dashboard should display whale activity from the existing backend API endpoints, show buy/sell pressure trends, and provide real-time alerts for significant whale movements."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Current Whale Activity (Priority: P1)

As a trader, I want to see the current whale transaction activity and net flow direction so I can understand if whales are accumulating or distributing Bitcoin.

**Why this priority**: This is the core value proposition - users need to immediately see whale activity to make informed trading decisions.

**Independent Test**: Can be fully tested by loading the dashboard and verifying that current whale flow data is displayed with the latest net flow value and direction indicator.

**Acceptance Scenarios**:

1. **Given** the dashboard is loaded, **When** I view the main display, **Then** I see the current whale net flow value in BTC
2. **Given** whale transactions are occurring, **When** the net flow changes, **Then** the display updates to show buy/sell pressure direction (positive = buying, negative = selling)
3. **Given** no whale activity in the last hour, **When** I view the dashboard, **Then** I see "NEUTRAL" status clearly indicated

---

### User Story 2 - Monitor Real-Time Whale Transactions (Priority: P1)

As a trader, I want to see individual whale transactions as they happen so I can spot significant movements immediately.

**Why this priority**: Real-time visibility of large transactions is critical for immediate market awareness and decision-making.

**Independent Test**: Can be tested by verifying that new whale transactions appear in the feed within 5 seconds of detection.

**Acceptance Scenarios**:

1. **Given** the dashboard is open, **When** a new whale transaction (>100 BTC) is detected, **Then** it appears in the transaction feed within 5 seconds
2. **Given** multiple whale transactions occur, **When** viewing the feed, **Then** transactions are displayed in chronological order with newest first
3. **Given** a transaction is displayed, **When** I view it, **Then** I see transaction size in BTC, USD value, timestamp, and transaction type (incoming/outgoing)

---

### User Story 3 - Analyze Historical Whale Flow Trends (Priority: P2)

As an analyst, I want to see historical whale flow patterns over time so I can identify accumulation and distribution phases.

**Why this priority**: Historical trend analysis provides context for current activity and helps identify patterns.

**Independent Test**: Can be tested by selecting different time ranges and verifying that the chart updates to show the corresponding historical data.

**Acceptance Scenarios**:

1. **Given** the dashboard has historical data, **When** I select a time range (1h/24h/7d/30d), **Then** the chart displays whale net flow for that period
2. **Given** I'm viewing the historical chart, **When** I hover over a data point, **Then** I see detailed information including exact timestamp, net flow value, and dominant direction
3. **Given** significant whale movements occurred, **When** viewing the chart, **Then** I can clearly distinguish between accumulation (green) and distribution (red) periods

---

### User Story 4 - Monitor Transaction Urgency (Priority: P2)

As a trader, I want to see the urgency level of whale transactions so I can prioritize which movements require immediate attention.

**Why this priority**: Urgency scoring helps users focus on the most time-sensitive transactions based on fee rates and other factors.

**Independent Test**: Can be tested by verifying that each transaction displays an urgency score and that high-urgency transactions are visually emphasized.

**Acceptance Scenarios**:

1. **Given** whale transactions are displayed, **When** I view them, **Then** each shows an urgency score from 0-100
2. **Given** a high-urgency transaction (>75) occurs, **When** it appears, **Then** it is visually highlighted with warning colors
3. **Given** multiple transactions exist, **When** viewing the feed, **Then** I can sort by urgency level to see most urgent first

---

### User Story 5 - Receive Critical Whale Alerts (Priority: P3)

As a user, I want to receive visual alerts for extreme whale movements so I don't miss critical market events even when not actively watching.

**Why this priority**: Alerts enhance user experience but the core value is delivered through the real-time display.

**Independent Test**: Can be tested by triggering a large whale movement and verifying that a visual notification appears on the dashboard.

**Acceptance Scenarios**:

1. **Given** the dashboard is open in background, **When** an extreme whale movement (>500 BTC) occurs, **Then** a visual notification appears on screen
2. **Given** an alert is shown, **When** I click on it, **Then** it takes me to the specific transaction details
3. **Given** multiple alerts occur, **When** viewing them, **Then** I can see a history of recent alerts with timestamps

---

### Edge Cases

- What happens when the connection to the data source is lost?
- How does the system handle periods with no whale activity?
- What displays when historical data is unavailable for selected timeframe?
- How are simultaneous large transactions aggregated in the net flow calculation?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display current whale net flow value in both BTC and USD equivalent
- **FR-002**: System MUST update whale flow data in real-time without page refresh
- **FR-003**: Dashboard MUST show whale transaction direction as BUY, SELL, or NEUTRAL
- **FR-004**: System MUST display individual whale transactions above 100 BTC threshold
- **FR-005**: Transaction feed MUST show timestamp, amount, USD value, and type for each transaction
- **FR-006**: System MUST provide time range selection for historical data (1h, 24h, 7d, 30d minimum)
- **FR-007**: Dashboard MUST display urgency score (0-100 scale) for each whale transaction
- **FR-008**: System MUST visually distinguish high-urgency transactions (score >75)
- **FR-009**: Historical chart MUST differentiate accumulation (positive flow) from distribution (negative flow) periods
- **FR-010**: Dashboard MUST handle connection interruptions gracefully with clear status indicators
- **FR-011**: System MUST aggregate net flow by 5-minute intervals for real-time display (with 1-minute updates for live ticker)
- **FR-012**: System MUST retain transaction history for 30 days in both UI and API for comprehensive historical analysis
- **FR-013**: System MUST provide multi-channel alert notifications for extreme whale movements (>500 BTC critical threshold)

### Key Entities *(include if feature involves data)*

- **Whale Transaction**: Represents a Bitcoin transaction exceeding threshold, includes amount, timestamp, direction, urgency score, USD value
- **Net Flow Metric**: Aggregated buy minus sell volume over a time period, indicates overall whale sentiment
- **Urgency Score**: Calculated metric (0-100) based on transaction fee rate and other factors indicating time sensitivity
- **Alert**: Notification triggered by extreme whale movements, includes transaction reference and severity level

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can view current whale net flow status within 3 seconds of dashboard load
- **SC-002**: Real-time updates appear on screen within 5 seconds of whale transaction detection
- **SC-003**: Dashboard supports at least 100 concurrent users without performance degradation
- **SC-004**: Users can switch between time ranges and see updated charts within 2 seconds
- **SC-005**: 95% of users can successfully interpret whale flow direction on first view
- **SC-006**: Transaction feed can display at least 50 transactions without pagination impacting performance
- **SC-007**: High-urgency transactions (>75 score) are noticed by users within 10 seconds of appearance
- **SC-008**: System maintains real-time connection for at least 99% of user session duration