# Phase 0: Research & Design Decisions

**Feature**: Real-Time Whale Detection Dashboard
**Date**: 2025-11-25

## Executive Summary

This document resolves all technical clarifications identified in the implementation plan. Decisions prioritize simplicity (Constitution I), security (Constitution V), and consistency with existing UTXOracle patterns (Constitution III).

---

## 1. WebSocket Authentication Strategy

### Decision: Token-Based Authentication

**Selected Approach**: JWT tokens with 1-hour expiry and refresh mechanism

**Rationale**:
- Stateless authentication aligns with scalability needs
- JWT allows embedding user context without database lookups
- Industry standard for real-time financial applications

**Implementation Details**:
```python
# Token structure
{
  "user_id": "uuid",
  "exp": 1234567890,  # 1 hour from issue
  "permissions": ["whale_view"]
}
```

**Alternatives Considered**:
- Session-based auth: Rejected due to state management complexity
- API keys: Rejected as less secure for browser contexts
- OAuth2: Rejected as overkill for single dashboard

**Token Lifecycle**:
1. Initial auth via `/api/auth/token` endpoint (existing auth system)
2. Token sent in WebSocket connection query params
3. Auto-refresh 5 minutes before expiry
4. Graceful reconnection on token expiry

---

## 2. Rate Limiting Parameters

### Decision: Tiered Rate Limiting

**Selected Approach**:
- HTTP API: 100 requests/minute per IP
- WebSocket: 20 messages/second per connection
- Burst handling: Token bucket algorithm with 10-request burst capacity

**Rationale**:
- Prevents abuse while allowing legitimate real-time usage
- Token bucket handles burst traffic gracefully
- Aligns with 100 concurrent user target

**Implementation**:
```python
# Using existing FastAPI rate limiter
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.websocket("/ws/whale-alerts")
@limiter.limit("20/second")
async def websocket_endpoint(websocket: WebSocket):
    ...
```

**Alternatives Considered**:
- Fixed window: Rejected due to thundering herd problem
- Sliding window: Rejected as more complex than needed
- No rate limiting: Rejected per Constitution V security requirements

---

## 3. Browser Testing Approach

### Decision: Hybrid Testing Strategy

**Selected Approach**:
- **MVP Phase**: Manual test checklist (immediate implementation)
- **Production Phase**: Playwright E2E tests (future iteration)

**Manual Test Checklist**:
```markdown
## Whale Dashboard Test Checklist

### Load Performance
- [ ] Dashboard loads in <3 seconds
- [ ] All charts render within 1 second
- [ ] No JavaScript errors in console

### Real-time Updates
- [ ] WebSocket connects on load
- [ ] Transactions appear within 5 seconds
- [ ] Auto-reconnection works after disconnect

### Cross-browser
- [ ] Chrome 90+ verified
- [ ] Firefox 88+ verified
- [ ] Safari 14+ verified
```

**Rationale**:
- Manual testing sufficient for MVP per YAGNI principle
- Automated tests added when user base grows
- Follows existing UTXOracle manual testing pattern

**Alternatives Considered**:
- Selenium: Rejected as heavyweight for simple dashboard
- Jest + React Testing Library: Rejected (no React framework)
- Cypress: Rejected for MVP, consider for production

---

## 4. Chart Library Decision

### Decision: Plotly.js (Minimal Bundle)

**Selected Approach**: Plotly.js basic bundle (plotly-basic.min.js)
- Size: ~1MB gzipped
- Features: Line charts, scatter plots, basic interactivity
- CDN delivery with local fallback

**Rationale**:
- Proven in financial dashboards
- Built-in zoom/pan crucial for time series analysis
- Smaller than full Plotly bundle (3.4MB)
- Better than Chart.js for financial data

**Usage Pattern**:
```javascript
// Lazy load Plotly only when needed
if (!window.Plotly) {
    const script = document.createElement('script');
    script.src = 'https://cdn.plot.ly/plotly-basic-latest.min.js';
    script.onerror = () => loadLocalPlotly();  // Fallback
    document.head.appendChild(script);
}
```

**Alternatives Considered**:
- Chart.js: Good but less financial-specific features
- D3.js: Too low-level, violates KISS principle
- Pure Canvas 2D: Insufficient for interactive time series
- Highcharts: Commercial license required

---

## 5. Alert Notification Method

### Decision: Progressive Enhancement Strategy

**Selected Approach**:
1. **Primary**: In-page toast notifications (always works)
2. **Enhanced**: Browser Notification API (if permitted)
3. **Fallback**: Visual + audio cue for critical alerts

**Implementation**:
```javascript
class WhaleAlertSystem {
    async notify(alert) {
        // Always show in-page toast
        this.showToast(alert);

        // Try browser notification if permitted
        if (Notification.permission === 'granted') {
            new Notification('Whale Alert', {
                body: `${alert.amount} BTC ${alert.direction}`,
                icon: '/assets/icons/whale.png'
            });
        }

        // Critical alerts (>500 BTC) get audio
        if (alert.amount > 500) {
            this.playAlertSound();
        }
    }
}
```

**Rationale**:
- Progressive enhancement ensures functionality for all users
- In-page notifications work without permissions
- Audio alerts for critical events match trader expectations

**Alternatives Considered**:
- Push notifications: Rejected as too complex for MVP
- Email alerts: Rejected as not real-time enough
- SMS alerts: Rejected due to cost and complexity

---

## Architecture Decisions Summary

| Component | Decision | Justification |
|-----------|----------|---------------|
| **Auth** | JWT tokens (1hr expiry) | Stateless, scalable, secure |
| **Rate Limit** | 100 req/min HTTP, 20 msg/s WS | Prevents abuse, allows bursts |
| **Testing** | Manual checklist → Playwright | MVP simplicity, future automation |
| **Charts** | Plotly.js basic bundle | Financial features, reasonable size |
| **Alerts** | Toast + Browser API + Audio | Progressive enhancement |

---

## Security Considerations

### WebSocket Security Hardening

1. **Connection Validation**:
   - Validate JWT on every connection
   - Check token expiry before each message
   - Rate limit connection attempts (5/minute per IP)

2. **Message Sanitization**:
   - Pydantic models for all WebSocket messages
   - HTML escape all user-visible content
   - Validate numeric ranges for amounts

3. **Client-Side Security**:
   - Content Security Policy headers
   - Subresource Integrity for CDN assets
   - No eval() or innerHTML usage

---

## Performance Optimizations

### Frontend Optimizations

1. **Lazy Loading**:
   - Load Plotly.js only when charts needed
   - Defer non-critical CSS
   - Use Intersection Observer for below-fold content

2. **Data Management**:
   - Limit transaction feed to 50 items (ring buffer)
   - Aggregate old data points for charts (>1hr)
   - Use requestAnimationFrame for smooth updates

3. **WebSocket Efficiency**:
   - Binary protocol for high-frequency updates
   - Message batching (100ms window)
   - Compression via permessage-deflate

---

## Implementation Priority

### Phase 1A: Core Dashboard (Week 1)
1. Basic HTML structure
2. WebSocket connection (no auth)
3. Transaction feed display
4. Net flow indicator

### Phase 1B: Charts & Auth (Week 2)
1. JWT authentication
2. Plotly.js integration
3. Historical chart
4. Rate limiting

### Phase 1C: Polish & Alerts (Week 3)
1. Alert system
2. Responsive design
3. Cross-browser testing
4. Performance optimization

---

## Next Steps

With all clarifications resolved, proceed to Phase 1:
1. Generate `data-model.md` with message schemas
2. Create `contracts/websocket.md` specifications
3. Write `quickstart.md` developer guide
4. Update agent context with frontend specifics

All decisions align with Constitution principles:
- ✅ Simplicity (vanilla JS, minimal deps)
- ✅ Testing (defined strategy)
- ✅ UX Consistency (follows UTXOracle patterns)
- ✅ Performance (specific targets met)
- ✅ Security (auth + rate limiting + sanitization)