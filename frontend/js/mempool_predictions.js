/**
 * Mempool Whale Predictions - WebSocket Client with JWT Authentication
 * Task: T030a/b - Authenticated WebSocket client for real-time whale alerts
 *
 * Features:
 * - JWT token authentication on connection
 * - Automatic reconnection with exponential backoff
 * - Real-time whale alert display
 * - Connection status monitoring
 * - Message queuing during disconnection
 * - Error handling and user feedback
 */

class MempoolWhaleClient {
    constructor(wsUrl = 'ws://localhost:8765') {
        this.wsUrl = wsUrl;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 1000; // Start with 1 second
        this.maxReconnectDelay = 30000; // Max 30 seconds
        this.isIntentionalClose = false;
        this.messageQueue = [];
        this.connectionStatus = 'disconnected';
        this.onWhaleAlert = null; // Callback for whale alerts
        this.onStatusChange = null; // Callback for connection status changes
    }

    /**
     * Connect to WebSocket server with JWT authentication
     */
    async connect() {
        // Check if authenticated
        if (!authManager.isAuthenticated() || authManager.isTokenExpired()) {
            console.error('Cannot connect to WebSocket - not authenticated');
            this.updateStatus('unauthorized');
            authManager.redirectToLogin();
            return;
        }

        try {
            this.updateStatus('connecting');
            console.log(`🔌 Connecting to whale alert server: ${this.wsUrl}`);

            // Create WebSocket connection
            this.ws = new WebSocket(this.wsUrl);

            // Connection opened
            this.ws.onopen = () => {
                console.log('✅ WebSocket connection established');
                this.updateStatus('authenticating');

                // Send JWT token for authentication
                const token = authManager.getToken();
                const authMessage = {
                    type: 'auth',
                    token: token
                };

                this.ws.send(JSON.stringify(authMessage));
                console.log('🔑 Sent authentication token');
            };

            // Handle incoming messages
            this.ws.onmessage = (event) => {
                this.handleMessage(event.data);
            };

            // Connection closed
            this.ws.onclose = (event) => {
                console.log(`🔌 WebSocket connection closed (code: ${event.code})`);
                this.updateStatus('disconnected');

                // Attempt reconnection unless intentionally closed
                if (!this.isIntentionalClose) {
                    this.scheduleReconnect();
                }
            };

            // Connection error
            this.ws.onerror = (error) => {
                console.error('❌ WebSocket error:', error);
                this.updateStatus('error');
            };

        } catch (error) {
            console.error('❌ Failed to connect to WebSocket:', error);
            this.updateStatus('error');
            this.scheduleReconnect();
        }
    }

    /**
     * Handle incoming WebSocket messages
     */
    handleMessage(data) {
        try {
            const message = JSON.parse(data);

            switch (message.type) {
                case 'auth_success':
                    console.log('✅ Authentication successful');
                    this.updateStatus('connected');
                    this.reconnectAttempts = 0; // Reset counter on successful connection
                    this.reconnectDelay = 1000; // Reset delay
                    this.processMessageQueue(); // Send queued messages
                    break;

                case 'auth_failed':
                    console.error('❌ Authentication failed:', message.reason);
                    this.updateStatus('unauthorized');
                    authManager.clearToken();
                    authManager.redirectToLogin();
                    this.close();
                    break;

                case 'whale_alert':
                    console.log('🐋 Whale alert received:', message.data);
                    if (this.onWhaleAlert) {
                        this.onWhaleAlert(message.data);
                    }
                    break;

                case 'ping':
                    // Respond to ping to keep connection alive
                    this.send({ type: 'pong' });
                    break;

                case 'error':
                    console.error('Server error:', message.message);
                    break;

                default:
                    console.warn('Unknown message type:', message.type);
            }

        } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
        }
    }

    /**
     * Send message to server
     */
    send(message) {
        if (this.connectionStatus === 'connected' && this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            // Queue message for later if not connected
            console.warn('WebSocket not connected - queueing message');
            this.messageQueue.push(message);
        }
    }

    /**
     * Process queued messages after reconnection
     */
    processMessageQueue() {
        if (this.messageQueue.length > 0) {
            console.log(`📤 Processing ${this.messageQueue.length} queued messages`);
            while (this.messageQueue.length > 0) {
                const message = this.messageQueue.shift();
                this.send(message);
            }
        }
    }

    /**
     * Schedule reconnection with exponential backoff
     */
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('❌ Max reconnection attempts reached');
            this.updateStatus('failed');
            return;
        }

        this.reconnectAttempts++;

        // Calculate delay with exponential backoff
        const delay = Math.min(
            this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
            this.maxReconnectDelay
        );

        console.log(
            `🔄 Reconnecting in ${delay / 1000}s (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
        );

        setTimeout(() => {
            this.connect();
        }, delay);
    }

    /**
     * Update connection status
     */
    updateStatus(status) {
        const oldStatus = this.connectionStatus;
        this.connectionStatus = status;

        console.log(`📊 Status change: ${oldStatus} → ${status}`);

        if (this.onStatusChange) {
            this.onStatusChange(status, oldStatus);
        }
    }

    /**
     * Close connection gracefully
     */
    close() {
        this.isIntentionalClose = true;
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.updateStatus('disconnected');
        console.log('🔌 WebSocket connection closed intentionally');
    }

    /**
     * Get current connection status
     */
    getStatus() {
        return this.connectionStatus;
    }

    /**
     * Check if connected
     */
    isConnected() {
        return this.connectionStatus === 'connected' &&
               this.ws &&
               this.ws.readyState === WebSocket.OPEN;
    }
}

// Export singleton instance
const whaleClient = new MempoolWhaleClient();

// Auto-connect on page load if authenticated
document.addEventListener('DOMContentLoaded', () => {
    console.log('🔐 Mempool Whale Client initialized');
    console.log('Authentication status:', authManager.getTokenInfo());

    // Only auto-connect if authenticated
    if (authManager.isAuthenticated() && !authManager.isTokenExpired()) {
        console.log('✅ User authenticated - auto-connecting to whale alerts');
        whaleClient.connect();
    } else {
        console.warn('⚠️ User not authenticated - cannot connect to whale alerts');
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    whaleClient.close();
});
