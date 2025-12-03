# Quick Start Guide: Whale Detection Dashboard

**Feature**: Real-Time Whale Detection Dashboard
**Time to First View**: ~5 minutes

## Prerequisites

- Python 3.11+ installed
- Node.js 16+ (for npm packages if needed)
- Running UTXOracle backend with whale detection
- Modern browser (Chrome 90+, Firefox 88+, Safari 14+)

## Backend Status Check

First, verify the whale detection backend is operational:

```bash
# Check if whale detection is running
ps aux | grep whale_detection_orchestrator

# Verify API is responding
curl http://localhost:8001/api/whale/latest | jq .

# Expected response:
# {
#   "whale_net_flow": 0.0,
#   "whale_direction": "NEUTRAL",
#   "action": "HOLD",
#   "combined_signal": 0.30
# }
```

## Quick Dashboard Setup (5 minutes)

### Step 1: Create Dashboard Files

```bash
# Navigate to frontend directory
cd /media/sam/1TB/UTXOracle/frontend

# Create whale dashboard HTML
cat > whale_dashboard.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UTXOracle - Whale Detection Dashboard</title>
    <style>
        body {
            background: #0a0a0a;
            color: #00ff00;
            font-family: 'Monaco', monospace;
            margin: 0;
            padding: 20px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px;
            border-bottom: 2px solid #00ff00;
        }
        .net-flow {
            font-size: 48px;
            text-align: center;
            padding: 40px;
        }
        .direction {
            font-size: 24px;
            text-align: center;
            padding: 20px;
        }
        .BUY { color: #00ff00; }
        .SELL { color: #ff0000; }
        .NEUTRAL { color: #ffff00; }
        .transaction-feed {
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid #00ff00;
            padding: 10px;
            margin: 20px;
        }
        .transaction {
            padding: 10px;
            border-bottom: 1px solid #333;
        }
        .high-urgency {
            background: rgba(255, 0, 0, 0.2);
            border-left: 4px solid #ff0000;
        }
        .status {
            position: fixed;
            top: 10px;
            right: 10px;
            padding: 10px;
            background: #000;
            border: 1px solid #00ff00;
        }
        .connected { color: #00ff00; }
        .disconnected { color: #ff0000; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🐋 Whale Detection Dashboard</h1>
        <div class="status" id="connection-status">
            <span class="disconnected">● Disconnected</span>
        </div>
    </div>

    <div class="net-flow" id="net-flow">
        Loading...
    </div>

    <div class="direction" id="direction">
        Waiting for data...
    </div>

    <div id="chart-container" style="height: 400px; margin: 20px;"></div>

    <div class="transaction-feed" id="transaction-feed">
        <h3>Recent Whale Transactions</h3>
    </div>

    <!-- Load Plotly for charts -->
    <script src="https://cdn.plot.ly/plotly-basic-latest.min.js"></script>

    <script>
        // Quick implementation for testing
        class WhaleDashboard {
            constructor() {
                this.transactions = [];
                this.netFlowHistory = [];
                this.connect();
                this.pollAPI(); // Fallback to polling for MVP
            }

            async pollAPI() {
                try {
                    const response = await fetch('/api/whale/latest');
                    const data = await response.json();
                    this.updateNetFlow(data);

                    // Poll every 5 seconds
                    setTimeout(() => this.pollAPI(), 5000);
                } catch (error) {
                    console.error('API poll error:', error);
                    setTimeout(() => this.pollAPI(), 10000);
                }
            }

            updateNetFlow(data) {
                const flowEl = document.getElementById('net-flow');
                const directionEl = document.getElementById('direction');

                flowEl.textContent = `${data.whale_net_flow.toFixed(2)} BTC`;
                directionEl.textContent = `Direction: ${data.whale_direction}`;
                directionEl.className = `direction ${data.whale_direction}`;

                // Add to history for chart
                this.netFlowHistory.push({
                    time: new Date(),
                    value: data.whale_net_flow,
                    direction: data.whale_direction
                });

                // Keep last 100 points
                if (this.netFlowHistory.length > 100) {
                    this.netFlowHistory.shift();
                }

                this.updateChart();
            }

            updateChart() {
                const trace = {
                    x: this.netFlowHistory.map(d => d.time),
                    y: this.netFlowHistory.map(d => d.value),
                    type: 'scatter',
                    mode: 'lines',
                    line: { color: '#00ff00', width: 2 }
                };

                const layout = {
                    title: 'Whale Net Flow (5-min intervals)',
                    paper_bgcolor: '#0a0a0a',
                    plot_bgcolor: '#0a0a0a',
                    font: { color: '#00ff00' },
                    xaxis: { gridcolor: '#333' },
                    yaxis: { gridcolor: '#333', title: 'BTC' }
                };

                Plotly.newPlot('chart-container', [trace], layout);
            }

            connect() {
                // WebSocket connection (to be implemented)
                const statusEl = document.getElementById('connection-status');
                statusEl.innerHTML = '<span class="connected">● Connected (API)</span>';
            }

            addTransaction(tx) {
                const feed = document.getElementById('transaction-feed');
                const txEl = document.createElement('div');
                txEl.className = 'transaction';
                if (tx.urgency_score > 75) {
                    txEl.className += ' high-urgency';
                }

                txEl.innerHTML = `
                    <strong>${tx.amount_btc} BTC</strong> -
                    ${tx.direction} -
                    Urgency: ${tx.urgency_score}/100 -
                    ${new Date(tx.timestamp).toLocaleTimeString()}
                `;

                feed.insertBefore(txEl, feed.firstChild.nextSibling);

                // Keep max 50 transactions
                while (feed.children.length > 51) {
                    feed.removeChild(feed.lastChild);
                }
            }
        }

        // Start dashboard
        const dashboard = new WhaleDashboard();
    </script>
</body>
</html>
EOF

echo "✅ Dashboard created at frontend/whale_dashboard.html"
```

### Step 2: Serve the Dashboard

```bash
# Option A: Use existing FastAPI server (recommended)
# The dashboard should be served at http://localhost:8001/whale

# Option B: Quick Python server for testing
cd /media/sam/1TB/UTXOracle/frontend
python3 -m http.server 8080

# Dashboard available at http://localhost:8080/whale_dashboard.html
```

### Step 3: Open in Browser

```bash
# Auto-open in default browser
xdg-open http://localhost:8001/whale_dashboard.html  # Linux
open http://localhost:8001/whale_dashboard.html      # macOS
```

## Full Implementation Setup

### Step 1: Install Backend Security Modules

```bash
cd /media/sam/1TB/UTXOracle

# Create auth module
cat > api/whale_auth.py << 'EOF'
from fastapi import HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta

SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"

security = HTTPBearer()

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=1)
    payload = {
        "user_id": user_id,
        "exp": expire,
        "permissions": ["whale_view"]
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def verify_websocket_token(token: str = Query()):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except:
        return None
EOF

# Create rate limiter
cat > api/whale_security.py << 'EOF'
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Request

def setup_rate_limiting(app: FastAPI):
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return limiter
EOF

echo "✅ Security modules created"
```

### Step 2: Create WebSocket Handler

```bash
# Add to existing API
cat >> api/main.py << 'EOF'

from fastapi import WebSocket, WebSocketDisconnect
from api.whale_auth import verify_websocket_token
import asyncio
import json

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket, token: str):
        user = await verify_websocket_token(token)
        if not user:
            await websocket.close(code=4001, reason="Unauthorized")
            return False

        await websocket.accept()
        self.active_connections.append(websocket)
        return True

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws/whale-alerts")
async def websocket_endpoint(websocket: WebSocket, token: str):
    if not await manager.connect(websocket, token):
        return

    try:
        while True:
            # Keep connection alive and handle messages
            data = await websocket.receive_text()
            message = json.loads(data)

            if message["type"] == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": int(time.time() * 1000)
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
EOF

echo "✅ WebSocket handler added"
```

### Step 3: Create Frontend Modules

```bash
cd /media/sam/1TB/UTXOracle/frontend

# Create directories
mkdir -p js css assets/icons

# WebSocket client
cat > js/whale_client.js << 'EOF'
class WhaleWebSocketClient {
    constructor(token) {
        this.token = token;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.callbacks = {};
    }

    connect() {
        const wsUrl = `ws://localhost:8001/ws/whale-alerts?token=${this.token}`;
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
            this.subscribe(['transactions', 'netflow', 'alerts']);
            this.startHeartbeat();
        };

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.reconnect();
        };
    }

    reconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), 30000);
            this.reconnectAttempts++;
            console.log(`Reconnecting in ${delay}ms...`);
            setTimeout(() => this.connect(), delay);
        }
    }

    subscribe(channels) {
        this.send({
            type: 'subscribe',
            channels: channels,
            filters: {
                min_amount: 100,
                urgency_threshold: 0
            }
        });
    }

    send(message) {
        if (this.ws.readyState === WebSocket.OPEN) {
            message.timestamp = Date.now();
            this.ws.send(JSON.stringify(message));
        }
    }

    handleMessage(message) {
        const callback = this.callbacks[message.type];
        if (callback) {
            callback(message.data);
        }
    }

    on(messageType, callback) {
        this.callbacks[messageType] = callback;
    }

    startHeartbeat() {
        setInterval(() => {
            this.send({ type: 'ping' });
        }, 30000);
    }
}

export default WhaleWebSocketClient;
EOF

echo "✅ Frontend modules created"
```

## Testing the Dashboard

### Manual Test Checklist

```bash
# Create test checklist
cat > test_checklist.md << 'EOF'
## Whale Dashboard Test Checklist

### Initial Load
- [ ] Dashboard loads in <3 seconds
- [ ] Net flow value displays
- [ ] Direction indicator shows (BUY/SELL/NEUTRAL)
- [ ] Chart renders properly
- [ ] No JavaScript errors in console (F12)

### Real-time Updates
- [ ] API polling works (check Network tab)
- [ ] Values update every 5 seconds
- [ ] Chart updates with new data points
- [ ] Status indicator shows "Connected"

### Transaction Feed
- [ ] Transactions appear in feed
- [ ] High urgency transactions highlighted
- [ ] Timestamps display correctly
- [ ] Maximum 50 transactions maintained

### Responsive Design
- [ ] Dashboard scales on mobile (F12 → Mobile view)
- [ ] Charts remain readable
- [ ] Text doesn't overflow

### Cross-Browser
- [ ] Works in Chrome
- [ ] Works in Firefox
- [ ] Works in Safari

### Performance
- [ ] CPU usage acceptable
- [ ] Memory usage stable
- [ ] No memory leaks after 10 minutes
EOF

echo "✅ Test checklist created"
```

## Production Deployment

### Step 1: Environment Configuration

```bash
# Create production config
cat > .env.production << 'EOF'
# API Configuration
API_HOST=0.0.0.0
API_PORT=8001
WORKERS=4

# Security
JWT_SECRET_KEY=<generate-secure-key>
CORS_ORIGINS=["https://yourdomain.com"]

# Rate Limiting
RATE_LIMIT_PER_MINUTE=100
WS_RATE_LIMIT_PER_SECOND=20

# WebSocket
WS_HEARTBEAT_INTERVAL=30
WS_MAX_CONNECTIONS=100

# Database
DUCKDB_PATH=/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db
EOF
```

### Step 2: Systemd Service

```bash
# Create service file
sudo cat > /etc/systemd/system/whale-dashboard.service << 'EOF'
[Unit]
Description=UTXOracle Whale Detection Dashboard
After=network.target utxoracle-api.service

[Service]
Type=simple
User=sam
WorkingDirectory=/media/sam/1TB/UTXOracle
Environment="PYTHONPATH=/media/sam/1TB/UTXOracle"
ExecStart=/media/sam/1TB/UTXOracle/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8001 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Start service
sudo systemctl enable whale-dashboard.service
sudo systemctl start whale-dashboard.service
sudo systemctl status whale-dashboard.service
```

### Step 3: Nginx Reverse Proxy

```nginx
server {
    listen 443 ssl http2;
    server_name whale.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # WebSocket support
    location /ws/ {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # API endpoints
    location /api/ {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Static files
    location / {
        root /media/sam/1TB/UTXOracle/frontend;
        try_files $uri $uri/ /whale_dashboard.html;
    }
}
```

## Troubleshooting

### Common Issues

#### WebSocket Won't Connect
```bash
# Check if port is open
sudo netstat -tlnp | grep 8001

# Check firewall
sudo ufw status

# Check CORS settings
curl -I http://localhost:8001/ws/whale-alerts
```

#### No Data Showing
```bash
# Verify backend is running
ps aux | grep whale_detection

# Check API response
curl http://localhost:8001/api/whale/latest

# Check database
ls -lh /media/sam/2TB-NVMe/prod/apps/utxoracle/data/
```

#### Performance Issues
```bash
# Check CPU/Memory
htop

# Check WebSocket connections
netstat -an | grep 8001 | grep ESTABLISHED | wc -l

# Check rate limiting
tail -f /var/log/nginx/error.log
```

## Next Steps

1. **Enhance Security**:
   - Implement proper JWT refresh mechanism
   - Add CSRF protection
   - Enable SSL/TLS for WebSocket

2. **Improve UX**:
   - Add loading animations
   - Implement toast notifications
   - Add sound alerts for critical movements

3. **Add Features**:
   - Historical data viewer
   - Export functionality
   - Custom alert thresholds
   - Multi-timeframe charts

4. **Optimize Performance**:
   - Implement virtual scrolling for transaction feed
   - Add data aggregation for older points
   - Use Web Workers for heavy calculations

---

**Support**: For issues, check logs at:
- API logs: `journalctl -u whale-dashboard.service -f`
- Whale detection: `tail -f /tmp/whale_detection.log`
- Nginx: `tail -f /var/log/nginx/error.log`