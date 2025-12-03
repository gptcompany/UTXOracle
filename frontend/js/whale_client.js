/**
 * UTXOracle WebSocket Client
 * Handles real-time whale transaction streaming via WebSocket
 *
 * Tasks Implemented:
 * - T049: WebSocket client module
 * - T050: Connection with JWT authentication
 * - T051: Channel subscription handling
 *
 * Features:
 * - Automatic reconnection with exponential backoff
 * - Heartbeat/ping mechanism (30s interval)
 * - Event-based message handling
 * - Connection state management
 * - Rate limiting awareness
 */

// ============================================
// Configuration
// ============================================

const WS_CONFIG = {
    // WebSocket endpoint (protocol determined by page protocol)
    endpoint: '/ws/whale-alerts',

    // Reconnection strategy
    reconnect: {
        baseDelay: 1000,        // 1 second
        maxDelay: 30000,        // 30 seconds
        factor: 1.5,            // Exponential backoff factor
        maxRetries: 10,         // Maximum retry attempts
        jitterRange: 0.4        // ±20% jitter
    },

    // Heartbeat configuration
    heartbeat: {
        pingInterval: 30000,    // 30 seconds
        pongTimeout: 5000,      // 5 seconds
        maxMissedPongs: 3       // Connection dead after 3 missed pongs
    },

    // Subscription defaults
    defaultChannels: ['transactions', 'netflow'],
    defaultFilters: {
        min_amount: 100,
        max_amount: null,
        urgency_threshold: 0
    }
};

// ============================================
// Connection States
// ============================================

const ConnectionState = {
    DISCONNECTED: 'disconnected',
    CONNECTING: 'connecting',
    CONNECTED: 'connected',
    RECONNECTING: 'reconnecting',
    ERROR: 'error'
};

// ============================================
// Event Types
// ============================================

const EventType = {
    // Connection events
    CONNECTING: 'connecting',
    CONNECTED: 'connected',
    DISCONNECTED: 'disconnected',
    ERROR: 'error',

    // Data events
    TRANSACTION: 'transaction',
    NETFLOW: 'netflow',
    ALERT: 'alert',
    HISTORICAL: 'historical',

    // System events
    SUBSCRIPTION_ACK: 'subscription_ack',
    RATE_LIMITED: 'rate_limited',
    TOKEN_EXPIRED: 'token_expired'
};

// ============================================
// Reconnection Strategy
// ============================================

class ReconnectionStrategy {
    constructor(config) {
        this.config = config;
        this.attemptCount = 0;
    }

    reset() {
        this.attemptCount = 0;
    }

    calculateDelay() {
        const { baseDelay, maxDelay, factor, jitterRange } = this.config;

        // Exponential backoff
        const delay = Math.min(
            baseDelay * Math.pow(factor, this.attemptCount),
            maxDelay
        );

        // Add jitter (±20%)
        const jitter = 1 + (Math.random() - 0.5) * 2 * jitterRange;

        this.attemptCount++;
        return Math.floor(delay * jitter);
    }

    canRetry() {
        return this.attemptCount < this.config.maxRetries;
    }
}

// ============================================
// Event Emitter
// ============================================

class EventEmitter {
    constructor() {
        this.listeners = {};
    }

    on(event, callback) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        this.listeners[event].push(callback);
    }

    off(event, callback) {
        if (!this.listeners[event]) return;
        this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    }

    emit(event, data) {
        if (!this.listeners[event]) return;
        this.listeners[event].forEach(callback => {
            try {
                callback(data);
            } catch (error) {
                console.error(`Error in event listener for ${event}:`, error);
            }
        });
    }

    once(event, callback) {
        const onceWrapper = (data) => {
            callback(data);
            this.off(event, onceWrapper);
        };
        this.on(event, onceWrapper);
    }
}

// ============================================
// WhaleWebSocketClient
// ============================================

class WhaleWebSocketClient extends EventEmitter {
    constructor(jwtToken, config = WS_CONFIG) {
        super();

        this.jwtToken = jwtToken;
        this.config = config;

        // Connection state
        this.state = ConnectionState.DISCONNECTED;
        this.ws = null;

        // Message sequence tracking
        this.clientSequence = 0;
        this.serverSequence = 0;

        // Reconnection management
        this.reconnectionStrategy = new ReconnectionStrategy(config.reconnect);
        this.reconnectTimer = null;
        this.shouldReconnect = true;

        // Heartbeat management
        this.pingTimer = null;
        this.pongTimer = null;
        this.missedPongs = 0;

        // Subscription state
        this.subscribedChannels = [];
        this.subscriptionFilters = { ...config.defaultFilters };

        // Statistics
        this.stats = {
            messagesReceived: 0,
            messagesSent: 0,
            reconnectCount: 0,
            connectionTime: null,
            lastMessageTime: null
        };
    }

    // ========================================
    // Connection Management
    // ========================================

    connect() {
        if (this.state === ConnectionState.CONNECTED ||
            this.state === ConnectionState.CONNECTING) {
            console.warn('Already connected or connecting');
            return;
        }

        this.updateState(ConnectionState.CONNECTING);

        try {
            const wsUrl = this.buildWebSocketURL();
            console.log('Connecting to WebSocket:', wsUrl.replace(/token=.*/, 'token=***'));

            this.ws = new WebSocket(wsUrl);
            this.setupWebSocketHandlers();

        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.handleConnectionError(error);
        }
    }

    disconnect() {
        console.log('Disconnecting WebSocket...');
        this.shouldReconnect = false;
        this.cleanup();

        if (this.ws) {
            this.ws.close(1000, 'Client disconnect');
            this.ws = null;
        }

        this.updateState(ConnectionState.DISCONNECTED);
    }

    reconnect() {
        if (!this.shouldReconnect) {
            console.log('Reconnection disabled');
            return;
        }

        if (!this.reconnectionStrategy.canRetry()) {
            console.error('Max reconnection attempts reached');
            this.updateState(ConnectionState.ERROR);
            this.emit(EventType.ERROR, {
                message: 'Max reconnection attempts exceeded',
                retries: this.reconnectionStrategy.attemptCount
            });
            return;
        }

        const delay = this.reconnectionStrategy.calculateDelay();
        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectionStrategy.attemptCount})...`);

        this.updateState(ConnectionState.RECONNECTING);
        this.stats.reconnectCount++;

        this.reconnectTimer = setTimeout(() => {
            this.connect();
        }, delay);
    }

    // ========================================
    // WebSocket Event Handlers
    // ========================================

    setupWebSocketHandlers() {
        this.ws.onopen = this.handleOpen.bind(this);
        this.ws.onmessage = this.handleMessage.bind(this);
        this.ws.onerror = this.handleError.bind(this);
        this.ws.onclose = this.handleClose.bind(this);
    }

    handleOpen() {
        console.log('WebSocket connected successfully');

        this.updateState(ConnectionState.CONNECTED);
        this.reconnectionStrategy.reset();
        this.stats.connectionTime = new Date();

        // Subscribe to default channels
        this.subscribe(this.config.defaultChannels, this.config.defaultFilters);

        // Start heartbeat
        this.startHeartbeat();

        this.emit(EventType.CONNECTED, {
            connectionTime: this.stats.connectionTime
        });
    }

    handleMessage(event) {
        this.stats.messagesReceived++;
        this.stats.lastMessageTime = new Date();

        try {
            const message = JSON.parse(event.data);

            // Track server sequence
            if (message.sequence !== undefined) {
                this.serverSequence = message.sequence;
            }

            this.routeMessage(message);

        } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
        }
    }

    handleError(error) {
        console.error('WebSocket error:', error);
        this.emit(EventType.ERROR, {
            message: 'WebSocket error occurred',
            error: error
        });
    }

    handleClose(event) {
        console.log('WebSocket closed:', {
            code: event.code,
            reason: event.reason,
            wasClean: event.wasClean
        });

        this.cleanup();

        // Handle different close codes
        if (event.code === 1000) {
            // Normal closure
            this.updateState(ConnectionState.DISCONNECTED);
            this.emit(EventType.DISCONNECTED, { reason: event.reason });
        } else if (event.code === 1008 || event.code === 4001) {
            // Policy violation / Auth failed
            this.shouldReconnect = false;
            this.updateState(ConnectionState.ERROR);
            this.emit(EventType.TOKEN_EXPIRED);
        } else {
            // Abnormal closure - attempt reconnect
            this.reconnect();
        }
    }

    handleConnectionError(error) {
        console.error('Connection error:', error);
        this.cleanup();
        this.reconnect();
    }

    // ========================================
    // Message Routing
    // ========================================

    routeMessage(message) {
        switch (message.type) {
            case 'transaction':
                this.emit(EventType.TRANSACTION, message.data);
                break;

            case 'netflow':
                this.emit(EventType.NETFLOW, message.data);
                break;

            case 'alert':
                this.emit(EventType.ALERT, message.data);
                break;

            case 'historical_response':
                this.emit(EventType.HISTORICAL, message.data);
                break;

            case 'ack':
                this.handleAcknowledgment(message);
                break;

            case 'pong':
                this.handlePong(message);
                break;

            case 'error':
                this.handleServerError(message.error);
                break;

            case 'batch':
                this.handleBatch(message.messages);
                break;

            default:
                console.warn('Unknown message type:', message.type);
        }
    }

    handleAcknowledgment(message) {
        if (message.status === 'success') {
            this.subscribedChannels = message.subscribed_channels || [];
            console.log('Subscription acknowledged:', this.subscribedChannels);

            this.emit(EventType.SUBSCRIPTION_ACK, {
                channels: this.subscribedChannels,
                serverTime: message.server_time
            });
        }
    }

    handleServerError(error) {
        console.error('Server error:', error);

        if (error.code === 'RATE_LIMIT') {
            this.emit(EventType.RATE_LIMITED, {
                retryAfter: error.retry_after,
                limit: error.limit,
                window: error.window
            });
        } else if (error.code === 'TOKEN_EXPIRED') {
            this.emit(EventType.TOKEN_EXPIRED);
            this.disconnect();
        }

        this.emit(EventType.ERROR, { error });
    }

    handleBatch(messages) {
        messages.forEach(msg => this.routeMessage(msg));
    }

    // ========================================
    // Message Sending
    // ========================================

    send(message) {
        if (this.state !== ConnectionState.CONNECTED) {
            console.warn('Cannot send message - not connected');
            return false;
        }

        try {
            message.timestamp = Date.now();
            message.sequence = ++this.clientSequence;

            this.ws.send(JSON.stringify(message));
            this.stats.messagesSent++;

            return true;
        } catch (error) {
            console.error('Failed to send message:', error);
            return false;
        }
    }

    subscribe(channels, filters = null) {
        const message = {
            type: 'subscribe',
            channels: channels,
            filters: filters || this.subscriptionFilters
        };

        return this.send(message);
    }

    unsubscribe(channels) {
        const message = {
            type: 'unsubscribe',
            channels: channels
        };

        return this.send(message);
    }

    requestHistorical(dataType, timeRange) {
        const message = {
            type: 'historical_request',
            data_type: dataType,
            time_range: timeRange
        };

        return this.send(message);
    }

    // ========================================
    // Heartbeat Management
    // ========================================

    startHeartbeat() {
        this.stopHeartbeat();

        this.pingTimer = setInterval(() => {
            this.sendPing();
        }, this.config.heartbeat.pingInterval);
    }

    stopHeartbeat() {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
            this.pingTimer = null;
        }

        if (this.pongTimer) {
            clearTimeout(this.pongTimer);
            this.pongTimer = null;
        }
    }

    sendPing() {
        if (!this.send({ type: 'ping' })) {
            return;
        }

        // Set timeout for pong response
        this.pongTimer = setTimeout(() => {
            this.handleMissedPong();
        }, this.config.heartbeat.pongTimeout);
    }

    handlePong(message) {
        // Clear pong timeout
        if (this.pongTimer) {
            clearTimeout(this.pongTimer);
            this.pongTimer = null;
        }

        this.missedPongs = 0;
    }

    handleMissedPong() {
        this.missedPongs++;
        console.warn(`Missed pong ${this.missedPongs}/${this.config.heartbeat.maxMissedPongs}`);

        if (this.missedPongs >= this.config.heartbeat.maxMissedPongs) {
            console.error('Connection dead - too many missed pongs');
            this.ws.close(1006, 'Connection timeout');
        }
    }

    // ========================================
    // Utility Methods
    // ========================================

    updateState(newState) {
        if (this.state !== newState) {
            const oldState = this.state;
            this.state = newState;
            console.log(`Connection state: ${oldState} → ${newState}`);
        }
    }

    buildWebSocketURL() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const endpoint = this.config.endpoint;
        const token = encodeURIComponent(this.jwtToken);

        return `${protocol}//${host}${endpoint}?token=${token}`;
    }

    cleanup() {
        this.stopHeartbeat();

        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }

    getState() {
        return this.state;
    }

    getStats() {
        return { ...this.stats };
    }

    isConnected() {
        return this.state === ConnectionState.CONNECTED;
    }
}

// ============================================
// Export
// ============================================

export { WhaleWebSocketClient, ConnectionState, EventType, WS_CONFIG };
