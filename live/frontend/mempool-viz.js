/**
 * UTXOracle Live - Frontend Visualization (T056-T059 + T074a-T074c + T107-T109)
 *
 * Implements:
 * - T056: WebSocket client connection
 * - T057: Price display update
 * - T058: Connection status indicator
 * - T059: Reconnection logic with exponential backoff
 * - T069-T074: Canvas 2D scatter plot visualization
 * - T074a: Timeline scrolling (fixed 5-min window)
 * - T074b: Variable point size (scaled by tx USD value)
 * - T074c: Fade-out for old points
 * - T107: Render baseline points (cyan)
 * - T108: Add baseline price line indicator
 * - T109: Dual timeline split (LEFT=baseline, RIGHT=mempool)
 */

class MempoolWebSocketClient {
    constructor(wsUrl = 'ws://localhost:8000/ws/mempool') {
        this.wsUrl = wsUrl;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.baseReconnectDelay = 1000;
        this.reconnectTimeout = null;
        this.isIntentionallyClosed = false;

        this.onMessageCallback = null;
        this.onConnectCallback = null;
        this.onDisconnectCallback = null;
    }

    connect() {
        if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
            console.log('[WebSocket] Already connected or connecting');
            return;
        }

        console.log(`[WebSocket] Connecting to ${this.wsUrl}...`);
        this.isIntentionallyClosed = false;

        try {
            this.ws = new WebSocket(this.wsUrl);

            this.ws.onopen = () => {
                console.log('[WebSocket] Connected');
                this.reconnectAttempts = 0;
                
                if (this.onConnectCallback) {
                    this.onConnectCallback();
                }
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (this.onMessageCallback) {
                        this.onMessageCallback(data);
                    }
                } catch (err) {
                    console.error('[WebSocket] Failed to parse message:', err);
                }
            };

            this.ws.onclose = (event) => {
                console.log('[WebSocket] Disconnected:', event.code, event.reason);
                
                if (this.onDisconnectCallback) {
                    this.onDisconnectCallback();
                }

                if (!this.isIntentionallyClosed) {
                    this.scheduleReconnect();
                }
            };

            this.ws.onerror = (error) => {
                console.error('[WebSocket] Error:', error);
            };

        } catch (err) {
            console.error('[WebSocket] Connection failed:', err);
            this.scheduleReconnect();
        }
    }

    scheduleReconnect() {
        if (this.isIntentionallyClosed) {
            return;
        }

        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[WebSocket] Max reconnect attempts reached.');
            return;
        }

        const delay = Math.min(
            this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts),
            30000
        );

        this.reconnectAttempts++;
        console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);

        this.reconnectTimeout = setTimeout(() => {
            this.connect();
        }, delay);
    }

    disconnect() {
        console.log('[WebSocket] Disconnecting...');
        this.isIntentionallyClosed = true;

        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
            this.reconnectTimeout = null;
        }

        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    onMessage(callback) {
        this.onMessageCallback = callback;
    }

    onConnect(callback) {
        this.onConnectCallback = callback;
    }

    onDisconnect(callback) {
        this.onDisconnectCallback = callback;
    }
}

class UIController {
    constructor() {
        this.priceElement = document.getElementById('price');
        this.confidenceElement = document.getElementById('confidence');
        this.confidenceLabelElement = document.getElementById('confidence-label');
        this.connectionStatusElement = document.getElementById('connection-status');
        this.confidenceWarningElement = document.getElementById('confidence-warning');
        
        this.statReceivedElement = document.getElementById('stat-received');
        this.statFilteredElement = document.getElementById('stat-filtered');
        this.statActiveElement = document.getElementById('stat-active');
        this.statUptimeElement = document.getElementById('stat-uptime');
    }

    updatePrice(price) {
        if (!price || price <= 0) {
            this.priceElement.textContent = '$--,---';
            return;
        }

        const formatted = '$' + price.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        this.priceElement.textContent = formatted;
    }

    updateConfidence(confidence) {
        if (confidence === null || confidence === undefined) {
            this.confidenceElement.textContent = '--';
            this.confidenceLabelElement.textContent = '(--)';
            if (this.confidenceWarningElement) {
                this.confidenceWarningElement.classList.remove('show');
            }
            return;
        }

        this.confidenceElement.textContent = confidence.toFixed(2);

        let label, colorClass;
        if (confidence >= 0.8) {
            label = 'High';
            colorClass = 'confidence-high';
        } else if (confidence >= 0.5) {
            label = 'Medium';
            colorClass = 'confidence-medium';
        } else {
            label = 'Low';
            colorClass = 'confidence-low';
        }

        this.confidenceLabelElement.textContent = `(${label})`;
        this.confidenceLabelElement.className = `confidence-label ${colorClass}`;

        // T080: Show/hide low confidence warning
        if (this.confidenceWarningElement) {
            if (confidence < 0.5) {
                this.confidenceWarningElement.classList.add('show');
            } else {
                this.confidenceWarningElement.classList.remove('show');
            }
        }
    }

    updateConnectionStatus(isConnected) {
        if (isConnected) {
            this.connectionStatusElement.textContent = '● Connected';
            this.connectionStatusElement.className = 'status-indicator status-connected';
        } else {
            this.connectionStatusElement.textContent = '● Disconnected';
            this.connectionStatusElement.className = 'status-indicator status-disconnected';
        }
    }

    updateReconnectingStatus() {
        this.connectionStatusElement.textContent = '● Reconnecting...';
        this.connectionStatusElement.className = 'status-indicator status-reconnecting';
    }

    updateStats(stats) {
        if (!stats) return;

        this.statReceivedElement.textContent = stats.total_received || 0;
        this.statFilteredElement.textContent = stats.total_filtered || 0;
        this.statActiveElement.textContent = stats.active_tx_count || 0;

        const uptime = stats.uptime_seconds || 0;
        this.statUptimeElement.textContent = this.formatUptime(uptime);
    }

    formatUptime(seconds) {
        if (seconds < 60) {
            return `${Math.floor(seconds)}s`;
        } else if (seconds < 3600) {
            const minutes = Math.floor(seconds / 60);
            return `${minutes}m`;
        } else {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            return `${hours}h ${minutes}m`;
        }
    }
}

/**
 * MempoolVisualizer - Canvas 2D scatter plot (T074a-c: scrolling + variable size + fade-out)
 */
class MempoolVisualizer {
    constructor(canvasId = 'mempool-canvas') {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) {
            console.error('[MempoolVisualizer] Canvas element not found:', canvasId);
            return;
        }

        this.ctx = this.canvas.getContext('2d');

        this.width = 1000;
        this.height = 660;

        this.backgroundColor = '#000000';
        this.pointColor = '#FF8C00';
        this.axisColor = '#FFFFFF';
        this.textColor = '#FFFFFF';
        this.tooltipBgColor = 'rgba(0, 0, 0, 0.9)';
        this.tooltipBorderColor = '#FF8C00';

        // T074b: Variable point size
        // BUGFIX 2025-10-23: Increased maxRadius from 8 to 20 to allow visible size variation
        // (Most transactions were clamped to 8, making all points look the same)
        this.pointMinRadius = 1;
        this.pointMaxRadius = 20;

        this.marginLeft = 80;
        this.marginRight = 20;
        this.marginTop = 40;  // Increased for dual panel labels
        this.marginBottom = 60;

        this.plotWidth = this.width - this.marginLeft - this.marginRight;
        this.plotHeight = this.height - this.marginTop - this.marginBottom;

        // T109: Dual panel split (LEFT=baseline 40%, RIGHT=mempool 60%)
        this.panelSplitRatio = 0.4;
        this.baselineWidth = this.plotWidth * this.panelSplitRatio;
        this.mempoolWidth = this.plotWidth * (1 - this.panelSplitRatio);

        this.transactions = [];
        this.priceMin = 0;
        this.priceMax = 100000;

        // T107-T109: Baseline data storage and colors
        this.baseline = null;
        this.baselineColor = '#00FFFF';  // Cyan for baseline points
        this.baselineLineColor = 'rgba(0, 255, 255, 0.5)';  // Cyan with 50% opacity

        // T074a: Fixed 5-minute scrolling window
        this.timeWindowSeconds = 300;  // 5 minutes

        this.hoveredTransaction = null;
        this.tooltipThreshold = 10;

        this.animationFrameId = null;

        this.enableTooltips();
        this.startRendering();

        console.log('[MempoolVisualizer] Initialized with scrolling timeline');
    }

    updateData(transactions, baseline = null) {
        // T107-T109: Store baseline data if provided
        if (baseline) {
            this.baseline = baseline;

            // BUGFIX 2025-10-23: Cache min/max timestamps to avoid recalculating every frame
            // (Bug #1: Performance issue with 10k points × 30 FPS = 9M ops/sec)
            if (baseline.transactions && baseline.transactions.length > 0) {
                const timestamps = baseline.transactions.map(tx => tx.timestamp);
                this.baselineTimeMin = Math.min(...timestamps);
                this.baselineTimeMax = Math.max(...timestamps);
            }
        }

        if (!transactions || transactions.length === 0) {
            return;
        }

        // T074a: Filter transactions outside time window
        const now = Date.now() / 1000;
        this.transactions = transactions.filter(tx =>
            tx.timestamp >= (now - this.timeWindowSeconds)
        );


        if (this.transactions.length === 0) {
            return;
        }
        // T109: Use baseline price range for Y-axis scaling if available
        // BUGFIX 2025-10-22: Must include BOTH baseline AND mempool transaction prices
        const prices = this.transactions.map(tx => tx.price);
        let rawMin = Math.min(...prices);
        let rawMax = Math.max(...prices);
        
        if (this.baseline && this.baseline.price_min && this.baseline.price_max) {
            // Expand range to include baseline
            rawMin = Math.min(rawMin, this.baseline.price_min);
            rawMax = Math.max(rawMax, this.baseline.price_max);
        }
        
        const padding = (rawMax - rawMin) * 0.05;
        this.priceMin = rawMin - padding;
        this.priceMax = rawMax + padding;
    }

    scaleY(price) {
        const priceRange = this.priceMax - this.priceMin;
        if (priceRange === 0) return this.marginTop + this.plotHeight / 2;

        const normalized = (price - this.priceMin) / priceRange;
        return this.marginTop + this.plotHeight - (normalized * this.plotHeight);
    }

    // T074a: Scrolling timeline (right=now, left=5min ago)
    scaleX(timestamp) {
        const now = Date.now() / 1000;
        const timeMin = now - this.timeWindowSeconds;
        const timeMax = now;

        const normalized = (timestamp - timeMin) / (timeMax - timeMin);
        return this.marginLeft + (normalized * this.plotWidth);
    }

    // T074b: Variable point size based on tx USD value
    // T074b: Variable point size based on tx USD value
    // BUGFIX 2025-10-22: TransactionPoint model only has timestamp and price (no btc_amount)
    // Using constant point size until btc_amount is added to model (see VISUALIZATION_BUG_REPORT.md)
    getPointSize(tx) {
        if (!tx.btc_amount) {
            // DEBUG: Log why sizing failed
            if (Math.random() < 0.01) { // 1% sampling
                console.log('[getPointSize] No btc_amount:', {
                    hasField: 'btc_amount' in tx,
                    value: tx.btc_amount,
                    type: typeof tx.btc_amount,
                    allKeys: Object.keys(tx)
                });
            }
            return 2; // Default size if btc_amount is missing
        }

        // Logarithmic scale for better visual distribution
        // Adjust the multiplier (e.g., 1.5) to control the size range
        const size = Math.log(tx.btc_amount * 1e8) * 1.5;

        return Math.max(this.pointMinRadius, Math.min(this.pointMaxRadius, size));
    }

    // T074c: Fade-out for old points
    getPointOpacity(timestamp) {
        const now = Date.now() / 1000;
        const age = now - timestamp;
        const maxAge = this.timeWindowSeconds;

        // Fade out over last 20% of time window
        const fadeStartAge = maxAge * 0.8;

        if (age < fadeStartAge) {
            return 1.0;
        }

        // Linear fade from 1.0 to 0.3
        const fadeProgress = (age - fadeStartAge) / (maxAge - fadeStartAge);
        return Math.max(0.3, 1.0 - (fadeProgress * 0.7));
    }

    startRendering() {
        const renderLoop = () => {
            this.render();
            this.animationFrameId = requestAnimationFrame(renderLoop);
        };
        renderLoop();
    }

    stopRendering() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }
    }

    render() {
        this.clear();
        this.drawAxes();
        this.drawPanelLabels();  // T109: Add panel labels

        // T108: Draw baseline price line BEFORE points (so points render on top)
        if (this.baseline) {
            this.drawBaselineLine();
        }

        // T109: Draw baseline points on left panel
        this.drawBaselinePoints();

        // Draw mempool points on right panel
        this.drawPoints();

        if (this.hoveredTransaction) {
            const x = this.scaleXMempool(this.hoveredTransaction.timestamp);
            const y = this.scaleY(this.hoveredTransaction.price);
            this.showTooltip(x, y, this.hoveredTransaction);
        }
    }

    clear() {
        this.ctx.fillStyle = this.backgroundColor;
        this.ctx.fillRect(0, 0, this.width, this.height);
    }

    // T108: Draw baseline price line indicator (horizontal reference)
    drawBaselineLine() {
        if (!this.baseline || !this.baseline.price) {
            return;
        }

        const y = this.scaleY(this.baseline.price);

        // Draw dashed horizontal line across canvas
        this.ctx.save();
        this.ctx.strokeStyle = this.baselineLineColor;
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([5, 5]);

        this.ctx.beginPath();
        this.ctx.moveTo(this.marginLeft, y);
        this.ctx.lineTo(this.marginLeft + this.plotWidth, y);
        this.ctx.stroke();

        this.ctx.setLineDash([]);
        this.ctx.restore();

        // Draw label at right edge
        this.ctx.save();
        this.ctx.fillStyle = this.baselineColor;
        this.ctx.font = '12px monospace';
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'middle';

        const label = `Baseline: $${Math.round(this.baseline.price).toLocaleString()}`;
        const labelX = this.marginLeft + this.plotWidth + 5;
        this.ctx.fillText(label, labelX, y);

        this.ctx.restore();
    }

    drawAxes() {
        this.ctx.strokeStyle = this.axisColor;
        this.ctx.fillStyle = this.textColor;
        this.ctx.lineWidth = 1;

        // Y axis
        this.ctx.beginPath();
        this.ctx.moveTo(this.marginLeft, this.marginTop);
        this.ctx.lineTo(this.marginLeft, this.marginTop + this.plotHeight);
        this.ctx.stroke();

        // X axis
        this.ctx.beginPath();
        this.ctx.moveTo(this.marginLeft, this.marginTop + this.plotHeight);
        this.ctx.lineTo(this.marginLeft + this.plotWidth, this.marginTop + this.plotHeight);
        this.ctx.stroke();

        // Y ticks
        this.ctx.font = '12px monospace';
        this.ctx.textAlign = 'right';
        this.ctx.textBaseline = 'middle';

        const yTicks = 5;
        for (let i = 0; i <= yTicks; i++) {
            const price = this.priceMin + (this.priceMax - this.priceMin) * i / yTicks;
            const y = this.scaleY(price);

            this.ctx.beginPath();
            this.ctx.moveTo(this.marginLeft - 5, y);
            this.ctx.lineTo(this.marginLeft, y);
            this.ctx.stroke();

            this.ctx.fillStyle = this.textColor;
            this.ctx.fillText('$' + Math.round(price).toLocaleString(), this.marginLeft - 10, y);
        }

        // Axis labels
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'top';
        this.ctx.fillStyle = this.textColor;
        this.ctx.fillText('Time →', this.marginLeft + this.plotWidth / 2, this.marginTop + this.plotHeight + 40);

        this.ctx.save();
        this.ctx.translate(15, this.marginTop + this.plotHeight / 2);
        this.ctx.rotate(-Math.PI / 2);
        this.ctx.textAlign = 'center';
        this.ctx.fillText('Price (USD) ↑', 0, 0);
        this.ctx.restore();
    }

    // T074b+T074c: Variable size + fade-out
    drawPoints() {
        if (this.transactions.length === 0) {
            return;
        }

        // DEBUG: Log first transaction to see btc_amount
        if (!this._debugLogged && this.transactions.length > 0) {
            console.log('[drawPoints] First transaction:', {
                tx: this.transactions[0],
                btc_amount: this.transactions[0].btc_amount,
                pointSize: this.getPointSize(this.transactions[0])
            });
            this._debugLogged = true;
        }

        for (const tx of this.transactions) {
            const x = this.scaleXMempool(tx.timestamp);
            const y = this.scaleY(tx.price);

            if (x >= this.marginLeft && x <= this.marginLeft + this.plotWidth &&
                y >= this.marginTop && y <= this.marginTop + this.plotHeight) {

                const pointSize = this.getPointSize(tx);
                const opacity = this.getPointOpacity(tx.timestamp);

                // Orange with opacity
                const r = 255;
                const g = 140;
                const b = 0;
                this.ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${opacity})`;

                this.ctx.beginPath();
                this.ctx.arc(x, y, pointSize, 0, 2 * Math.PI);
                this.ctx.fill();
            }
        }
    }

    // T109: Draw baseline points (cyan) on left panel
    drawBaselinePoints() {
        if (!this.baseline || !this.baseline.price) {
            return;
        }

        // BUGFIX 2025-10-22: Backend now sends baseline.transactions (10k points)
        if (this.baseline.transactions && this.baseline.transactions.length > 0) {
            for (const tx of this.baseline.transactions) {
                const baseX = this.scaleXBaseline(tx.timestamp);
                // BUGFIX 2025-10-23: Add horizontal jitter to prevent vertical stripes
                // (many transactions share same timestamp from same block)
                const jitter = (Math.random() - 0.5) * 4; // ±2 pixels
                const x = baseX + jitter;
                const y = this.scaleY(tx.price);

                // Cyan point
                this.ctx.fillStyle = 'rgba(0, 255, 255, 0.7)';
                this.ctx.beginPath();
                this.ctx.arc(x, y, 2, 0, 2 * Math.PI);
                this.ctx.fill();
            }
        } else {
            // Synthetic fallback (only if no data)
            const baselineY = this.scaleY(this.baseline.price);
            const numPoints = 50;
            const baselineStartX = this.marginLeft;

            for (let i = 0; i < numPoints; i++) {
                const x = baselineStartX + (i / numPoints) * this.baselineWidth;
                const verticalSpread = ((this.baseline.price_max - this.baseline.price_min) / (this.priceMax - this.priceMin)) * this.plotHeight;
                const yOffset = (Math.random() - 0.5) * verticalSpread;
                const y = baselineY + yOffset;

                this.ctx.fillStyle = 'rgba(0, 255, 255, 0.7)';
                this.ctx.beginPath();
                this.ctx.arc(x, y, 2, 0, 2 * Math.PI);
                this.ctx.fill();
            }
        }
    }

    // T109: Scale X for baseline panel (left side)
    scaleXBaseline(timestamp) {
        if (!this.baseline || !this.baseline.transactions || this.baseline.transactions.length === 0) {
            return this.marginLeft;
        }

        // BUGFIX 2025-10-23: Use cached min/max timestamps (calculated once in updateData)
        // Avoids 9M operations/sec (10k points × 30 FPS × 2 array passes)
        const minTime = this.baselineTimeMin;
        const maxTime = this.baselineTimeMax;

        // Avoid division by zero
        if (maxTime === minTime) {
            return this.marginLeft + this.baselineWidth / 2;
        }

        // Map to left panel (0 to baselineWidth)
        const normalized = (timestamp - minTime) / (maxTime - minTime);
        return this.marginLeft + (normalized * this.baselineWidth);
    }

    // T109: Scale X for mempool panel (right side)
    scaleXMempool(timestamp) {
        const now = Date.now() / 1000;
        const timeMin = now - this.timeWindowSeconds;
        const timeMax = now;

        const normalized = (timestamp - timeMin) / (timeMax - timeMin);

        // Map to right panel (mempool side)
        const mempoolStartX = this.marginLeft + this.baselineWidth;
        return mempoolStartX + (normalized * this.mempoolWidth);
    }

    // T109: Draw panel labels (LEFT: confirmed, RIGHT: mempool)
    drawPanelLabels() {
        this.ctx.save();
        this.ctx.font = '14px sans-serif';
        this.ctx.textBaseline = 'top';

        // LEFT panel label: "Confirmed On-Chain (3hr)" in cyan
        this.ctx.fillStyle = this.baselineColor;  // #00FFFF (cyan)
        this.ctx.textAlign = 'left';
        const leftLabelX = this.marginLeft + 10;
        const leftLabelY = 10;
        this.ctx.fillText('Confirmed On-Chain (3hr)', leftLabelX, leftLabelY);

        // RIGHT panel label: "Mempool" in orange
        this.ctx.fillStyle = this.pointColor;  // #FF8C00 (orange)
        this.ctx.textAlign = 'right';
        const rightLabelX = this.marginLeft + this.plotWidth - 10;
        const rightLabelY = 10;
        this.ctx.fillText('Mempool', rightLabelX, rightLabelY);

        // RIGHT panel average price (if available)
        if (this.transactions.length > 0) {
            const avgPrice = this.transactions.reduce((sum, tx) => sum + tx.price, 0) / this.transactions.length;
            const avgText = `Avg: $${Math.round(avgPrice).toLocaleString()}`;
            this.ctx.fillText(avgText, rightLabelX, rightLabelY + 20);
        }

        this.ctx.restore();
    }

    enableTooltips() {
        this.canvas.addEventListener('mousemove', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const scaleX = this.canvas.width / rect.width;
            const scaleY = this.canvas.height / rect.height;
            const mouseX = (e.clientX - rect.left) * scaleX;
            const mouseY = (e.clientY - rect.top) * scaleY;

            this.hoveredTransaction = this.findNearestPoint(mouseX, mouseY);
        });

        this.canvas.addEventListener('mouseleave', () => {
            this.hoveredTransaction = null;
        });
    }

    findNearestPoint(mouseX, mouseY) {
        if (this.transactions.length === 0) {
            return null;
        }

        let nearestTx = null;
        let minDistance = this.tooltipThreshold;

        for (const tx of this.transactions) {
            const x = this.scaleX(tx.timestamp);
            const y = this.scaleY(tx.price);

            const distance = Math.sqrt(
                Math.pow(mouseX - x, 2) + Math.pow(mouseY - y, 2)
            );

            if (distance < minDistance) {
                minDistance = distance;
                nearestTx = tx;
            }
        }

        return nearestTx;
    }

    showTooltip(x, y, transaction) {
        const padding = 8;
        const lineHeight = 16;

        const priceText = `$${transaction.price.toFixed(2)}`;
        const timeText = new Date(transaction.timestamp * 1000).toLocaleTimeString();
        const btcText = `TX Point`;  // BUGFIX: No btc_amount available

        this.ctx.font = '12px monospace';
        const textWidth = Math.max(
            this.ctx.measureText(priceText).width,
            this.ctx.measureText(timeText).width,
            this.ctx.measureText(btcText).width
        );

        const tooltipWidth = textWidth + padding * 2;
        const tooltipHeight = lineHeight * 3 + padding * 2;

        let tooltipX = x + 15;
        let tooltipY = y - tooltipHeight - 10;

        if (tooltipX + tooltipWidth > this.width - 10) {
            tooltipX = x - tooltipWidth - 15;
        }

        if (tooltipY < 10) {
            tooltipY = y + 15;
        }

        this.ctx.fillStyle = this.tooltipBgColor;
        this.ctx.fillRect(tooltipX, tooltipY, tooltipWidth, tooltipHeight);

        this.ctx.strokeStyle = this.tooltipBorderColor;
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(tooltipX, tooltipY, tooltipWidth, tooltipHeight);

        this.ctx.fillStyle = this.textColor;
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'top';

        this.ctx.fillText(priceText, tooltipX + padding, tooltipY + padding);
        this.ctx.fillText(timeText, tooltipX + padding, tooltipY + padding + lineHeight);
        this.ctx.fillText(btcText, tooltipX + padding, tooltipY + padding + lineHeight * 2);

        const pointSize = this.getPointSize(transaction);
        this.ctx.strokeStyle = this.tooltipBorderColor;
        this.ctx.lineWidth = 2;
        this.ctx.beginPath();
        this.ctx.arc(x, y, pointSize + 2, 0, 2 * Math.PI);
        this.ctx.stroke();
    }

    destroy() {
        this.stopRendering();
        this.transactions = [];
    }
}

class UTXOracleLive {
    constructor() {
        this.wsClient = new MempoolWebSocketClient();
        this.uiController = new UIController();
        this.visualizer = new MempoolVisualizer('mempool-canvas');

        this.wsClient.onConnect(() => {
            console.log('[App] WebSocket connected');
            this.uiController.updateConnectionStatus(true);
        });

        this.wsClient.onDisconnect(() => {
            console.log('[App] WebSocket disconnected');
            this.uiController.updateConnectionStatus(false);
            this.uiController.updateReconnectingStatus();
        });

        this.wsClient.onMessage((message) => {
            this.handleMempoolUpdate(message);
        });
    }

    start() {
        console.log('[App] Starting UTXOracle Live...');
        this.wsClient.connect();
    }

    stop() {
        console.log('[App] Stopping UTXOracle Live...');
        this.wsClient.disconnect();
        if (this.visualizer) {
            this.visualizer.destroy();
        }
    }

    handleMempoolUpdate(message) {
        if (message.type !== 'mempool_update') {
            console.warn('[App] Unknown message type:', message.type);
            return;
        }

        const data = message.data;

        this.uiController.updatePrice(data.price);
        this.uiController.updateConfidence(data.confidence);
        this.uiController.updateStats(data.stats);

        // T107-T109: Pass baseline data to visualizer along with transactions
        if (data.transactions && data.transactions.length > 0) {
            this.visualizer.updateData(data.transactions, data.baseline || null);
        }

        if (Math.random() < 0.1) {
            console.log('[App] Mempool update:', {
                price: data.price,
                confidence: data.confidence,
                active: data.stats?.active_in_window,
                transactions: data.transactions?.length || 0,
                baseline: data.baseline ? `$${Math.round(data.baseline.price).toLocaleString()}` : 'none'
            });
        }
    }
}

let app;

document.addEventListener('DOMContentLoaded', () => {
    console.log('[UTXOracle Live] Initializing...');
    
    app = new UTXOracleLive();
    app.start();

    window.addEventListener('beforeunload', () => {
        app.stop();
    });
});

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        MempoolWebSocketClient,
        UIController,
        MempoolVisualizer,
        UTXOracleLive
    };
}
