/**
 * UTXOracle Live - Frontend Visualization (T056-T059)
 * 
 * Implements:
 * - T056: WebSocket client connection
 * - T057: Price display update  
 * - T058: Connection status indicator
 * - T059: Reconnection logic with exponential backoff
 * - T069-T074: Canvas 2D scatter plot visualization
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
        this.statActiveElement.textContent = stats.active_in_window || 0;

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
 * MempoolVisualizer - Canvas 2D scatter plot visualization (T069-T074)
 */
class MempoolVisualizer {
    constructor(canvasId = 'mempool-canvas') {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) {
            console.error('[MempoolVisualizer] Canvas element not found:', canvasId);
            return;
        }

        this.ctx = this.canvas.getContext('2d');

        // Canvas dimensions
        this.width = 1000;
        this.height = 660;

        // Colors
        this.backgroundColor = '#000000';
        this.pointColor = '#FF8C00';  // Orange
        this.axisColor = '#FFFFFF';   // White
        this.textColor = '#FFFFFF';
        this.tooltipBgColor = 'rgba(0, 0, 0, 0.9)';
        this.tooltipBorderColor = '#FF8C00';

        // Point rendering
        this.pointRadius = 2;

        // Margins
        this.marginLeft = 80;
        this.marginRight = 20;
        this.marginTop = 20;
        this.marginBottom = 60;

        // Plot area dimensions
        this.plotWidth = this.width - this.marginLeft - this.marginRight;
        this.plotHeight = this.height - this.marginTop - this.marginBottom;

        // Data
        this.transactions = [];
        this.priceMin = 0;
        this.priceMax = 100000;
        this.timeMin = Date.now() / 1000;
        this.timeMax = Date.now() / 1000 + 300;  // 5 minutes ahead

        // Hover state
        this.hoveredTransaction = null;
        this.tooltipThreshold = 10;  // pixels

        // Animation
        this.animationFrameId = null;

        // Initialize
        this.enableTooltips();
        this.startRendering();

        console.log('[MempoolVisualizer] Initialized', {
            canvas: canvasId,
            dimensions: `${this.width}x${this.height}`,
            plotArea: `${this.plotWidth}x${this.plotHeight}`
        });
    }

    /**
     * Update transaction data and recalculate scales
     */
    updateData(transactions) {
        if (!transactions || transactions.length === 0) {
            return;
        }

        this.transactions = transactions;

        // Calculate price range with 5% padding
        const prices = transactions.map(tx => tx.price);
        const rawMin = Math.min(...prices);
        const rawMax = Math.max(...prices);
        const padding = (rawMax - rawMin) * 0.05;

        this.priceMin = rawMin - padding;
        this.priceMax = rawMax + padding;

        // Calculate time range
        const timestamps = transactions.map(tx => tx.timestamp);
        this.timeMin = Math.min(...timestamps);
        this.timeMax = Math.max(...timestamps);

        // Ensure minimum time range of 60 seconds
        if (this.timeMax - this.timeMin < 60) {
            this.timeMax = this.timeMin + 60;
        }

        console.log('[MempoolVisualizer] Data updated:', {
            count: transactions.length,
            priceRange: [this.priceMin.toFixed(2), this.priceMax.toFixed(2)],
            timeRange: [new Date(this.timeMin * 1000).toISOString(), new Date(this.timeMax * 1000).toISOString()]
        });
    }

    /**
     * Scale price to Y coordinate
     */
    scaleY(price) {
        const priceRange = this.priceMax - this.priceMin;
        if (priceRange === 0) return this.marginTop + this.plotHeight / 2;

        const normalized = (price - this.priceMin) / priceRange;
        return this.marginTop + this.plotHeight - (normalized * this.plotHeight);
    }

    /**
     * Scale timestamp to X coordinate
     */
    scaleX(timestamp) {
        const timeRange = this.timeMax - this.timeMin;
        if (timeRange === 0) return this.marginLeft;

        const normalized = (timestamp - this.timeMin) / timeRange;
        return this.marginLeft + (normalized * this.plotWidth);
    }

    /**
     * Start rendering loop
     */
    startRendering() {
        const renderLoop = () => {
            this.render();
            this.animationFrameId = requestAnimationFrame(renderLoop);
        };
        renderLoop();
    }

    /**
     * Stop rendering loop
     */
    stopRendering() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }
    }

    /**
     * Main render method
     */
    render() {
        this.clear();
        this.drawAxes();
        this.drawPoints();

        if (this.hoveredTransaction) {
            const x = this.scaleX(this.hoveredTransaction.timestamp);
            const y = this.scaleY(this.hoveredTransaction.price);
            this.showTooltip(x, y, this.hoveredTransaction);
        }
    }

    /**
     * Clear canvas with black background
     */
    clear() {
        this.ctx.fillStyle = this.backgroundColor;
        this.ctx.fillRect(0, 0, this.width, this.height);
    }

    /**
     * Draw axes and labels
     */
    drawAxes() {
        this.ctx.strokeStyle = this.axisColor;
        this.ctx.fillStyle = this.textColor;
        this.ctx.lineWidth = 1;

        // Y axis (left)
        this.ctx.beginPath();
        this.ctx.moveTo(this.marginLeft, this.marginTop);
        this.ctx.lineTo(this.marginLeft, this.marginTop + this.plotHeight);
        this.ctx.stroke();

        // X axis (bottom)
        this.ctx.beginPath();
        this.ctx.moveTo(this.marginLeft, this.marginTop + this.plotHeight);
        this.ctx.lineTo(this.marginLeft + this.plotWidth, this.marginTop + this.plotHeight);
        this.ctx.stroke();

        // Y axis ticks and labels
        this.ctx.font = '12px monospace';
        this.ctx.textAlign = 'right';
        this.ctx.textBaseline = 'middle';

        const yTicks = 5;
        for (let i = 0; i <= yTicks; i++) {
            const price = this.priceMin + (this.priceMax - this.priceMin) * i / yTicks;
            const y = this.scaleY(price);

            // Tick mark
            this.ctx.beginPath();
            this.ctx.moveTo(this.marginLeft - 5, y);
            this.ctx.lineTo(this.marginLeft, y);
            this.ctx.stroke();

            // Label
            this.ctx.fillStyle = this.textColor;
            this.ctx.fillText('$' + Math.round(price).toLocaleString(), this.marginLeft - 10, y);
        }

        // X axis labels (time)
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'top';
        this.ctx.fillStyle = this.textColor;
        this.ctx.fillText('Time →', this.marginLeft + this.plotWidth / 2, this.marginTop + this.plotHeight + 40);

        // Y axis label (price)
        this.ctx.save();
        this.ctx.translate(15, this.marginTop + this.plotHeight / 2);
        this.ctx.rotate(-Math.PI / 2);
        this.ctx.textAlign = 'center';
        this.ctx.fillText('Price (USD) ↑', 0, 0);
        this.ctx.restore();
    }

    /**
     * Draw transaction scatter points
     */
    drawPoints() {
        if (this.transactions.length === 0) {
            return;
        }

        this.ctx.fillStyle = this.pointColor;

        for (const tx of this.transactions) {
            const x = this.scaleX(tx.timestamp);
            const y = this.scaleY(tx.price);

            // Only draw if within plot bounds
            if (x >= this.marginLeft && x <= this.marginLeft + this.plotWidth &&
                y >= this.marginTop && y <= this.marginTop + this.plotHeight) {

                this.ctx.beginPath();
                this.ctx.arc(x, y, this.pointRadius, 0, 2 * Math.PI);
                this.ctx.fill();
            }
        }
    }

    /**
     * Enable hover tooltips
     */
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

    /**
     * Find nearest transaction point to mouse coordinates
     */
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

    /**
     * Show tooltip for hovered transaction
     */
    showTooltip(x, y, transaction) {
        const padding = 8;
        const lineHeight = 16;

        // Format text
        const priceText = `$${transaction.price.toFixed(2)}`;
        const timeText = new Date(transaction.timestamp * 1000).toLocaleTimeString();
        const btcText = `${transaction.btc_amount.toFixed(8)} BTC`;

        // Calculate tooltip dimensions
        this.ctx.font = '12px monospace';
        const textWidth = Math.max(
            this.ctx.measureText(priceText).width,
            this.ctx.measureText(timeText).width,
            this.ctx.measureText(btcText).width
        );

        const tooltipWidth = textWidth + padding * 2;
        const tooltipHeight = lineHeight * 3 + padding * 2;

        // Position tooltip (avoid edges)
        let tooltipX = x + 15;
        let tooltipY = y - tooltipHeight - 10;

        if (tooltipX + tooltipWidth > this.width - 10) {
            tooltipX = x - tooltipWidth - 15;
        }

        if (tooltipY < 10) {
            tooltipY = y + 15;
        }

        // Draw tooltip background
        this.ctx.fillStyle = this.tooltipBgColor;
        this.ctx.fillRect(tooltipX, tooltipY, tooltipWidth, tooltipHeight);

        // Draw tooltip border
        this.ctx.strokeStyle = this.tooltipBorderColor;
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(tooltipX, tooltipY, tooltipWidth, tooltipHeight);

        // Draw tooltip text
        this.ctx.fillStyle = this.textColor;
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'top';

        this.ctx.fillText(priceText, tooltipX + padding, tooltipY + padding);
        this.ctx.fillText(timeText, tooltipX + padding, tooltipY + padding + lineHeight);
        this.ctx.fillText(btcText, tooltipX + padding, tooltipY + padding + lineHeight * 2);

        // Highlight the point
        this.ctx.strokeStyle = this.tooltipBorderColor;
        this.ctx.lineWidth = 2;
        this.ctx.beginPath();
        this.ctx.arc(x, y, this.pointRadius + 2, 0, 2 * Math.PI);
        this.ctx.stroke();
    }

    /**
     * Cleanup
     */
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

        // Update visualization with transaction history (T073-T074)
        if (data.transactions && data.transactions.length > 0) {
            this.visualizer.updateData(data.transactions);
        }

        if (Math.random() < 0.1) {
            console.log('[App] Mempool update:', {
                price: data.price,
                confidence: data.confidence,
                active: data.stats?.active_in_window,
                transactions: data.transactions?.length || 0
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
