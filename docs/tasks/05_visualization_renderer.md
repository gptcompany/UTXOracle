# Task 05: Visualization Renderer Module

**Assigned Agent**: `general-purpose`

**Duration**: MVP 2 weeks | Production 4-6 weeks

**Dependencies**: Task 04 (Data Streamer)

---

## Objective

Create browser-based real-time visualization of mempool price data with two phases:

- **Phase 1 (MVP)**: Canvas 2D scatter plot (<2000 points)
- **Phase 2 (Production)**: Three.js WebGL rendering (10k-100k points @ 60fps)

---

## Phase 1: Canvas 2D MVP (2 weeks)

### Requirements

**Functional**:
1. Real-time scatter plot of mempool transactions
2. Display current price estimate (large text)
3. Show confirmed on-chain price (3hr window) for comparison
4. Mouseover tooltip (price, timestamp)
5. Auto-scaling axes

**Non-Functional**:
1. **Performance**: 30fps with <2000 points
2. **Dependencies**: Zero (vanilla JS + Canvas API)
3. **Bundle size**: <50KB total (no build step)
4. **Browser support**: Chrome, Firefox, Safari (modern versions)

---

### Implementation Details

#### File Structure
```
live/frontend/
├── index.html          # Main page
├── mempool-viz.js      # Canvas 2D renderer
└── styles.css          # Minimal styling
```

#### HTML Structure

```html
<!-- live/frontend/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UTXOracle Live</title>
    <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
    <header>
        <h1>
            <span class="cyan">UTXOracle</span>
            <span class="lime">Live</span>
        </h1>
        <div class="subtitle">
            Bitcoin price from 100% on-chain data. No banks, no paper trading.
        </div>
    </header>

    <main>
        <div class="chart-container">
            <div class="price-display">
                <div class="label">Mempool</div>
                <div class="price" id="mempool-price">$---,---</div>
                <div class="confidence">Confidence: <span id="confidence">--</span>%</div>
            </div>

            <canvas id="mempool-chart" width="1000" height="660"></canvas>

            <div id="tooltip" class="tooltip"></div>
        </div>

        <div class="stats">
            <div class="stat">
                <div class="stat-label">Active TXs</div>
                <div class="stat-value" id="stat-active">---</div>
            </div>
            <div class="stat">
                <div class="stat-label">Total Received</div>
                <div class="stat-value" id="stat-total">---</div>
            </div>
            <div class="stat">
                <div class="stat-label">Filtered</div>
                <div class="stat-value" id="stat-filtered">---</div>
            </div>
            <div class="stat">
                <div class="stat-label">Uptime</div>
                <div class="stat-value" id="stat-uptime">---</div>
            </div>
        </div>
    </main>

    <script src="/static/mempool-viz.js"></script>
</body>
</html>
```

#### Canvas 2D Renderer

```javascript
// live/frontend/mempool-viz.js

class MempoolVisualizer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');

        this.width = this.canvas.width;
        this.height = this.canvas.height;

        this.margin = { left: 120, right: 90, top: 100, bottom: 120 };
        this.plotWidth = this.width - this.margin.left - this.margin.right;
        this.plotHeight = this.height - this.margin.top - this.margin.bottom;

        // Data
        this.transactions = [];
        this.currentPrice = 0;
        this.confidence = 0;

        // WebSocket
        this.ws = null;
        this.connectWebSocket();

        // Mouse interaction
        this.setupMouseEvents();
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/mempool`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.updateData(data);
            this.render();
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        this.ws.onclose = () => {
            console.log('WebSocket closed, reconnecting in 5s...');
            setTimeout(() => this.connectWebSocket(), 5000);
        };
    }

    updateData(data) {
        this.transactions = data.transactions;
        this.currentPrice = data.price;
        this.confidence = data.confidence;

        // Update stats
        document.getElementById('mempool-price').textContent =
            `$${this.currentPrice.toLocaleString()}`;
        document.getElementById('confidence').textContent =
            Math.round(this.confidence * 100);
        document.getElementById('stat-active').textContent =
            data.stats.active_in_window.toLocaleString();
        document.getElementById('stat-total').textContent =
            data.stats.total_received.toLocaleString();
        document.getElementById('stat-filtered').textContent =
            data.stats.total_filtered.toLocaleString();
        document.getElementById('stat-uptime').textContent =
            this.formatUptime(data.stats.uptime_seconds);
    }

    render() {
        // Clear canvas
        this.ctx.fillStyle = 'black';
        this.ctx.fillRect(0, 0, this.width, this.height);

        if (this.transactions.length === 0) {
            this.drawNoData();
            return;
        }

        // Calculate scales
        const timestamps = this.transactions.map(t => t.timestamp);
        const prices = this.transactions.map(t => t.price);

        this.xmin = Math.min(...timestamps);
        this.xmax = Math.max(...timestamps);
        this.ymin = Math.min(...prices);
        this.ymax = Math.max(...prices);

        // Draw axes
        this.drawAxes();

        // Draw points
        this.drawPoints();

        // Draw average line
        this.drawAverageLine();
    }

    scaleX(timestamp) {
        return this.margin.left + ((timestamp - this.xmin) / (this.xmax - this.xmin)) * this.plotWidth;
    }

    scaleY(price) {
        return this.margin.top + (1 - (price - this.ymin) / (this.ymax - this.ymin)) * this.plotHeight;
    }

    drawAxes() {
        this.ctx.strokeStyle = 'white';
        this.ctx.lineWidth = 1;

        // Y axis
        this.ctx.beginPath();
        this.ctx.moveTo(this.margin.left, this.margin.top);
        this.ctx.lineTo(this.margin.left, this.margin.top + this.plotHeight);
        this.ctx.stroke();

        // X axis
        this.ctx.beginPath();
        this.ctx.moveTo(this.margin.left, this.margin.top + this.plotHeight);
        this.ctx.lineTo(this.margin.left + this.plotWidth, this.margin.top + this.plotHeight);
        this.ctx.stroke();

        // Y ticks
        this.ctx.fillStyle = 'white';
        this.ctx.font = '16px Arial';
        this.ctx.textAlign = 'right';

        for (let i = 0; i <= 5; i++) {
            const price = this.ymin + (this.ymax - this.ymin) * i / 5;
            const y = this.scaleY(price);

            this.ctx.fillText(`$${Math.round(price).toLocaleString()}`, this.margin.left - 10, y + 4);
        }

        // X ticks (timestamps)
        this.ctx.textAlign = 'center';
        for (let i = 0; i <= 5; i++) {
            const ts = this.xmin + (this.xmax - this.xmin) * i / 5;
            const x = this.scaleX(ts);

            const date = new Date(ts * 1000);
            const timeLabel = `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')} UTC`;

            this.ctx.fillText(timeLabel, x, this.margin.top + this.plotHeight + 30);
        }
    }

    drawPoints() {
        this.ctx.fillStyle = 'orange';

        for (const tx of this.transactions) {
            const x = this.scaleX(tx.timestamp);
            const y = this.scaleY(tx.price);

            this.ctx.fillRect(x, y, 2, 2);
        }
    }

    drawAverageLine() {
        const y = this.scaleY(this.currentPrice);

        this.ctx.strokeStyle = 'cyan';
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([5, 5]);

        this.ctx.beginPath();
        this.ctx.moveTo(this.margin.left, y);
        this.ctx.lineTo(this.margin.left + this.plotWidth, y);
        this.ctx.stroke();

        this.ctx.setLineDash([]);

        // Label
        this.ctx.fillStyle = 'cyan';
        this.ctx.font = '18px Arial';
        this.ctx.textAlign = 'left';
        this.ctx.fillText(`Avg: $${this.currentPrice.toLocaleString()}`, this.margin.left + this.plotWidth + 5, y + 5);
    }

    drawNoData() {
        this.ctx.fillStyle = 'white';
        this.ctx.font = '24px Arial';
        this.ctx.textAlign = 'center';
        this.ctx.fillText('Waiting for mempool data...', this.width / 2, this.height / 2);
    }

    setupMouseEvents() {
        const tooltip = document.getElementById('tooltip');

        this.canvas.addEventListener('mousemove', (event) => {
            const rect = this.canvas.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;

            // Check if inside plot area
            if (x < this.margin.left || x > this.margin.left + this.plotWidth ||
                y < this.margin.top || y > this.margin.top + this.plotHeight) {
                tooltip.style.opacity = 0;
                return;
            }

            // Find nearest transaction
            const timestamp = this.xmin + ((x - this.margin.left) / this.plotWidth) * (this.xmax - this.xmin);
            const price = this.ymax - ((y - this.margin.top) / this.plotHeight) * (this.ymax - this.ymin);

            tooltip.innerHTML = `
                <strong>Price:</strong> $${Math.round(price).toLocaleString()}<br>
                <strong>Time:</strong> ${new Date(timestamp * 1000).toLocaleTimeString('en-US', { timeZone: 'UTC', hour12: false })} UTC
            `;

            tooltip.style.left = `${event.clientX + 10}px`;
            tooltip.style.top = `${event.clientY - 60}px`;
            tooltip.style.opacity = 1;
        });

        this.canvas.addEventListener('mouseleave', () => {
            tooltip.style.opacity = 0;
        });
    }

    formatUptime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${minutes}m`;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    new MempoolVisualizer('mempool-chart');
});
```

---

## Phase 2: Three.js WebGL Production (4-6 weeks)

**Note**: Implement this phase ONLY when Canvas 2D performance becomes inadequate (>2000 points causing lag).

### Requirements

**Performance**:
- 60fps with 10k-100k points
- Smooth point fade-out (age-based alpha)
- GPU-accelerated rendering

### Implementation

```javascript
// live/frontend/mempool-viz-webgl.js

import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js';

class MempoolVisualizerWebGL {
    constructor(containerId) {
        this.container = document.getElementById(containerId);

        // Scene setup
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x000000);

        // Camera (orthographic for 2D plot)
        this.camera = new THREE.OrthographicCamera(
            0, 1000, 660, 0, 0.1, 1000
        );
        this.camera.position.z = 1;

        // Renderer
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(1000, 660);
        this.container.appendChild(this.renderer.domElement);

        // Points geometry
        this.geometry = new THREE.BufferGeometry();
        this.material = new THREE.PointsMaterial({
            size: 2,
            vertexColors: true,
            sizeAttenuation: false
        });
        this.points = new THREE.Points(this.geometry, this.material);
        this.scene.add(this.points);

        // Start animation loop
        this.animate();
    }

    updateData(transactions) {
        const positions = new Float32Array(transactions.length * 3);
        const colors = new Float32Array(transactions.length * 3);

        transactions.forEach((tx, i) => {
            // Position
            const x = this.scaleX(tx.timestamp);
            const y = this.scaleY(tx.price);

            positions[i * 3] = x;
            positions[i * 3 + 1] = y;
            positions[i * 3 + 2] = 0;

            // Color (orange, with age-based fade)
            const age = Date.now() / 1000 - tx.timestamp;
            const alpha = Math.max(0, 1 - age / 3600);  // Fade over 1 hour

            colors[i * 3] = 1.0;      // R
            colors[i * 3 + 1] = 0.4 * alpha;  // G
            colors[i * 3 + 2] = 0.0;  // B
        });

        this.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        this.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        this.renderer.render(this.scene, this.camera);
    }

    scaleX(timestamp) {
        // Map timestamp to [120, 910] (plot area)
        return 120 + ((timestamp - this.xmin) / (this.xmax - this.xmin)) * 790;
    }

    scaleY(price) {
        // Map price to [100, 560] (plot area, inverted Y)
        return 560 - ((price - this.ymin) / (this.ymax - this.ymin)) * 460;
    }
}
```

---

## Deliverables

### Phase 1 (MVP)
- [ ] `live/frontend/index.html`
- [ ] `live/frontend/mempool-viz.js` (Canvas 2D)
- [ ] `live/frontend/styles.css`
- [ ] Browser compatibility tests (Chrome, Firefox, Safari)

### Phase 2 (Production)
- [ ] `live/frontend/mempool-viz-webgl.js` (Three.js)
- [ ] Performance benchmark (10k-100k points @ 60fps)
- [ ] Fallback logic (WebGL → Canvas if GPU unavailable)

---

## Acceptance Criteria

✅ **MVP (Phase 1)**:
1. Real-time scatter plot updates
2. 30fps with <2000 points
3. Tooltip shows price/time on hover
4. Zero dependencies (vanilla JS)

✅ **Production (Phase 2)**:
1. 60fps with 50k points
2. Point fade-out over time
3. Smooth zoom/pan (optional)

---

**Status**: NOT STARTED
**Dependencies**: Task 04 complete
**Target MVP**: __________ (2 weeks)
**Target Production**: __________ (6 weeks)
