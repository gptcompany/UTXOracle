/**
 * UTXOracle Whale Detection Dashboard
 * Main JavaScript module for real-time whale activity monitoring
 *
 * Tasks Implemented:
 * - T041: Net flow display component (BTC + USD values)
 * - T042: Direction indicator (accumulation/distribution/neutral)
 * - T043: API endpoint connection
 * - T044: 5-second polling mechanism
 * - T045: Loading states and error handling
 * - T046: Number formatting (K, M, B suffixes)
 * - T049-T051: WebSocket client integration
 * - T052-T055: Transaction feed with ring buffer and auto-scroll
 */

// ============================================
// Imports
// ============================================

import { WhaleWebSocketClient, ConnectionState, EventType } from './whale_client.js';
import { TransactionFeed } from './whale_feed.js';
import { TransactionModal } from './whale_modal.js';
import { WhaleAudioNotifier } from './whale_audio.js';
import { WhaleChart } from './whale_charts.js';
import { WhaleAlertSystem } from './whale_alerts.js';

// ============================================
// Configuration
// ============================================

const CONFIG = {
    apiEndpoint: '/api/whale/latest',
    pollInterval: 5000, // 5 seconds
    maxRetries: 3,
    retryDelay: 2000,
    enableWebSocket: false, // Enable when JWT auth is configured
    jwtToken: null, // Will be fetched from auth endpoint
};

// ============================================
// Utility Functions
// ============================================

/**
 * Format large numbers with K, M, B suffixes
 * @param {number} num - Number to format
 * @param {number} decimals - Decimal places
 * @returns {string} Formatted number
 */
function formatNumber(num, decimals = 2) {
    if (num === null || num === undefined || isNaN(num)) return '0';

    const absNum = Math.abs(num);

    if (absNum >= 1e9) {
        return (num / 1e9).toFixed(decimals) + 'B';
    } else if (absNum >= 1e6) {
        return (num / 1e6).toFixed(decimals) + 'M';
    } else if (absNum >= 1e3) {
        return (num / 1e3).toFixed(decimals) + 'K';
    } else {
        return num.toFixed(decimals);
    }
}

/**
 * Format BTC amount with proper precision
 * @param {number} btc - BTC amount
 * @returns {string} Formatted BTC string
 */
function formatBTC(btc) {
    if (btc === null || btc === undefined || isNaN(btc)) return '0.00';
    return parseFloat(btc).toFixed(2);
}

/**
 * Format USD amount with commas
 * @param {number} usd - USD amount
 * @returns {string} Formatted USD string
 */
function formatUSD(usd) {
    if (usd === null || usd === undefined || isNaN(usd)) return '$0';
    return '$' + formatNumber(usd, 0);
}

/**
 * Get human-readable timestamp
 * @returns {string} Formatted timestamp
 */
function getTimestamp() {
    const now = new Date();
    return now.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// ============================================
// Dashboard State
// ============================================

class DashboardState {
    constructor() {
        this.connected = false;
        this.loading = true;
        this.error = null;
        this.lastUpdate = null;
        this.retryCount = 0;
        this.pollTimer = null;

        this.netFlowData = {
            btc: 0,
            usd: 0,
            direction: 'NEUTRAL',
            timestamp: null
        };
    }

    updateNetFlow(data) {
        this.netFlowData = {
            btc: data.whale_net_flow || 0,
            usd: (data.whale_net_flow || 0) * (data.btc_price || 40000), // Approximate
            direction: data.whale_direction || 'NEUTRAL',
            timestamp: new Date()
        };
        this.lastUpdate = new Date();
        this.error = null;
        this.retryCount = 0;
    }

    markError(error) {
        this.error = error;
        this.retryCount++;
    }

    reset() {
        this.error = null;
        this.retryCount = 0;
    }
}

// ============================================
// UI Controller
// ============================================

class UIController {
    constructor() {
        this.elements = {
            // Status bar
            connectionStatus: document.getElementById('connection-status'),
            lastUpdate: document.getElementById('last-update'),

            // Net flow display
            netFlowLoading: document.getElementById('net-flow-loading'),
            netFlowContent: document.getElementById('net-flow-content'),
            netFlowError: document.getElementById('net-flow-error'),

            valueBTC: document.getElementById('value-btc'),
            valueUSD: document.getElementById('value-usd'),

            // Direction indicator
            directionIndicator: document.getElementById('direction-indicator'),
            directionArrow: document.getElementById('direction-arrow'),
            directionLabel: document.getElementById('direction-label'),
            directionDescription: document.getElementById('direction-description'),

            // Controls
            retryButton: document.getElementById('retry-button'),
        };
    }

    showLoading() {
        this.elements.netFlowLoading.classList.remove('hidden');
        this.elements.netFlowContent.classList.add('hidden');
        this.elements.netFlowError.classList.add('hidden');
    }

    showContent() {
        this.elements.netFlowLoading.classList.add('hidden');
        this.elements.netFlowContent.classList.remove('hidden');
        this.elements.netFlowError.classList.add('hidden');
    }

    showError(message) {
        this.elements.netFlowLoading.classList.add('hidden');
        this.elements.netFlowContent.classList.add('hidden');
        this.elements.netFlowError.classList.remove('hidden');

        const errorMsg = this.elements.netFlowError.querySelector('.error-message');
        if (errorMsg) {
            errorMsg.textContent = `⚠️ ${message}`;
        }
    }

    updateConnectionStatus(connected, message = '') {
        const statusEl = this.elements.connectionStatus;

        if (connected) {
            statusEl.className = 'status-indicator connected';
            statusEl.querySelector('.status-text').textContent = 'Connected';
        } else {
            statusEl.className = 'status-indicator disconnected';
            statusEl.querySelector('.status-text').textContent = message || 'Disconnected';
        }
    }

    updateLastUpdate(timestamp) {
        if (timestamp) {
            this.elements.lastUpdate.textContent = `Last update: ${getTimestamp()}`;
        } else {
            this.elements.lastUpdate.textContent = 'No data yet';
        }
    }

    updateNetFlowDisplay(data) {
        // Update BTC value with appropriate color
        const btcValue = data.btc;
        const btcFormatted = formatBTC(Math.abs(btcValue));
        const btcSign = btcValue >= 0 ? '+' : '-';

        this.elements.valueBTC.textContent = `${btcSign}${btcFormatted} BTC`;
        this.elements.valueBTC.style.color = this.getDirectionColor(data.direction);

        // Update USD value
        this.elements.valueUSD.textContent = formatUSD(Math.abs(data.usd));
    }

    updateDirectionIndicator(direction) {
        const indicator = this.elements.directionIndicator;
        const arrow = this.elements.directionArrow.querySelector('.arrow-symbol');
        const label = this.elements.directionLabel;
        const description = this.elements.directionDescription;

        // Remove all direction classes
        indicator.classList.remove('accumulation', 'distribution', 'neutral');

        // Add appropriate class and update content
        switch (direction) {
            case 'BUY':
            case 'ACCUMULATION':
                indicator.classList.add('accumulation');
                arrow.textContent = '↑';
                label.textContent = 'ACCUMULATION';
                description.textContent = 'Whales are buying Bitcoin';
                break;

            case 'SELL':
            case 'DISTRIBUTION':
                indicator.classList.add('distribution');
                arrow.textContent = '↓';
                label.textContent = 'DISTRIBUTION';
                description.textContent = 'Whales are selling Bitcoin';
                break;

            case 'NEUTRAL':
            default:
                indicator.classList.add('neutral');
                arrow.textContent = '→';
                label.textContent = 'NEUTRAL';
                description.textContent = 'No significant whale activity';
                break;
        }
    }

    getDirectionColor(direction) {
        switch (direction) {
            case 'BUY':
            case 'ACCUMULATION':
                return 'var(--color-accent-buy)';
            case 'SELL':
            case 'DISTRIBUTION':
                return 'var(--color-accent-sell)';
            case 'NEUTRAL':
            default:
                return 'var(--color-accent-neutral)';
        }
    }
}

// ============================================
// API Client
// ============================================

class WhaleAPIClient {
    constructor(endpoint) {
        this.endpoint = endpoint;
    }

    async fetchLatest() {
        try {
            const response = await fetch(this.endpoint);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            return { success: true, data };

        } catch (error) {
            console.error('API fetch error:', error);
            return { success: false, error: error.message };
        }
    }
}

// ============================================
// Main Dashboard Controller
// ============================================

class WhaleDashboard {
    constructor() {
        this.state = new DashboardState();
        this.ui = new UIController();
        this.api = new WhaleAPIClient(CONFIG.apiEndpoint);

        // WebSocket client (optional - enabled when JWT auth is configured)
        this.wsClient = null;
        this.useWebSocket = CONFIG.enableWebSocket && CONFIG.jwtToken;

        // Transaction feed
        try {
            this.transactionFeed = new TransactionFeed('transaction-feed');
        } catch (error) {
            console.warn('Transaction feed initialization failed:', error);
            this.transactionFeed = null;
        }

        // Transaction modal
        this.transactionModal = new TransactionModal();

        // Audio notifications (T060)
        this.audioNotifier = new WhaleAudioNotifier({ largeTransactionThreshold: 500 });
        this.audioNotifier.init();

        // Historical chart (T063-T067)
        try {
            this.whaleChart = new WhaleChart('whale-chart');
        } catch (error) {
            console.warn('Whale chart initialization failed:', error);
            this.whaleChart = null;
        }

        // Alert system (T079-T085)
        try {
            this.alertSystem = new WhaleAlertSystem();
            console.log('Alert system initialized successfully');
        } catch (error) {
            console.warn('Alert system initialization failed:', error);
            this.alertSystem = null;
        }

        this.setupEventListeners();
        this.initialize();
    }

    setupEventListeners() {
        // Retry button
        this.ui.elements.retryButton.addEventListener('click', () => {
            this.state.reset();
            this.initialize();
        });

        // Handle page visibility changes (pause polling when hidden)
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.stopPolling();
                if (this.transactionFeed) {
                    this.transactionFeed.pause();
                }
            } else {
                this.startPolling();
                if (this.transactionFeed) {
                    this.transactionFeed.resume();
                }
            }
        });

        // Feed control buttons (if they exist)
        const pauseButton = document.getElementById('pause-feed');
        const clearButton = document.getElementById('clear-feed');

        if (pauseButton && this.transactionFeed) {
            pauseButton.addEventListener('click', () => {
                if (this.transactionFeed.isPaused) {
                    this.transactionFeed.resume();
                    pauseButton.querySelector('.control-label').textContent = 'Pause';
                    pauseButton.querySelector('.control-icon').textContent = '⏸';
                    pauseButton.classList.remove('active');
                } else {
                    this.transactionFeed.pause();
                    pauseButton.querySelector('.control-label').textContent = 'Resume';
                    pauseButton.querySelector('.control-icon').textContent = '▶';
                    pauseButton.classList.add('active');
                }
            });
        }

        if (clearButton && this.transactionFeed) {
            clearButton.addEventListener('click', () => {
                this.transactionFeed.clear();
            });
        }

        // High urgency filter toggle (T075)
        const highUrgencyButton = document.getElementById('filter-high-urgency');
        if (highUrgencyButton && this.transactionFeed) {
            let highUrgencyActive = false;

            highUrgencyButton.addEventListener('click', () => {
                highUrgencyActive = !highUrgencyActive;

                if (highUrgencyActive) {
                    // Apply high urgency filter (>= 80)
                    this.transactionFeed.setFilters({
                        minAmount: 0,
                        directions: ['BUY', 'SELL', 'NEUTRAL', 'ACCUMULATION', 'DISTRIBUTION'],
                        minUrgency: 80
                    });
                    highUrgencyButton.classList.add('active');
                } else {
                    // Clear filter
                    this.transactionFeed.clearFilters();
                    highUrgencyButton.classList.remove('active');
                }
            });
        }

        // Filter controls (T057)
        this.setupFilterControls();

        // Audio toggle (T060)
        this.setupAudioToggle();

        // Transaction modal trigger (listen for custom event from feed)
        const feedContainer = document.getElementById('transaction-feed');
        if (feedContainer) {
            feedContainer.addEventListener('transaction-selected', (event) => {
                if (this.transactionModal) {
                    this.transactionModal.show(event.detail);
                }
            });

            // Listen for filter count updates from feed
            feedContainer.addEventListener('filter-count-updated', (event) => {
                const { visible, total } = event.detail;
                const filterCount = document.getElementById('filter-count');
                if (filterCount) {
                    if (visible === total) {
                        filterCount.textContent = '';
                    } else {
                        filterCount.textContent = `Showing ${visible} of ${total}`;
                    }
                }
            });
        }
    }

    setupFilterControls() {
        // Filter panel toggle
        const toggleFiltersBtn = document.getElementById('toggle-filters');
        const filterPanel = document.getElementById('filter-panel');

        if (toggleFiltersBtn && filterPanel) {
            toggleFiltersBtn.addEventListener('click', () => {
                filterPanel.classList.toggle('hidden');

                // Update button state
                if (filterPanel.classList.contains('hidden')) {
                    toggleFiltersBtn.classList.remove('active');
                } else {
                    toggleFiltersBtn.classList.add('active');
                }
            });
        }

        // Urgency slider value display
        const urgencySlider = document.getElementById('filter-urgency');
        const urgencyValue = document.getElementById('filter-urgency-value');

        if (urgencySlider && urgencyValue) {
            urgencySlider.addEventListener('input', (e) => {
                urgencyValue.textContent = e.target.value;
            });
        }

        // Apply filters button
        const applyFiltersBtn = document.getElementById('apply-filters');
        if (applyFiltersBtn && this.transactionFeed) {
            applyFiltersBtn.addEventListener('click', () => {
                const filters = this.getFilterValues();
                this.transactionFeed.setFilters(filters);
            });
        }

        // Reset filters button
        const resetFiltersBtn = document.getElementById('reset-filters');
        if (resetFiltersBtn && this.transactionFeed) {
            resetFiltersBtn.addEventListener('click', () => {
                this.resetFilterValues();
                this.transactionFeed.clearFilters();
            });
        }
    }

    getFilterValues() {
        // Get current filter values from UI
        const minAmount = parseFloat(document.getElementById('filter-min-amount')?.value || '0');
        const minUrgency = parseInt(document.getElementById('filter-urgency')?.value || '0');

        // Get checked directions
        const directions = [];
        if (document.getElementById('filter-buy')?.checked) directions.push('BUY');
        if (document.getElementById('filter-sell')?.checked) directions.push('SELL');
        if (document.getElementById('filter-neutral')?.checked) directions.push('NEUTRAL');

        return {
            minAmount,
            minUrgency,
            directions
        };
    }

    resetFilterValues() {
        // Reset filter UI to defaults
        const minAmountInput = document.getElementById('filter-min-amount');
        const urgencySlider = document.getElementById('filter-urgency');
        const urgencyValue = document.getElementById('filter-urgency-value');
        const buyCheckbox = document.getElementById('filter-buy');
        const sellCheckbox = document.getElementById('filter-sell');
        const neutralCheckbox = document.getElementById('filter-neutral');
        const filterCount = document.getElementById('filter-count');

        if (minAmountInput) minAmountInput.value = '';
        if (urgencySlider) urgencySlider.value = '0';
        if (urgencyValue) urgencyValue.textContent = '0';
        if (buyCheckbox) buyCheckbox.checked = true;
        if (sellCheckbox) sellCheckbox.checked = true;
        if (neutralCheckbox) neutralCheckbox.checked = true;
        if (filterCount) filterCount.textContent = '';
    }

    setupAudioToggle() {
        const audioToggleBtn = document.getElementById('audio-toggle');
        const audioIcon = audioToggleBtn?.querySelector('.audio-icon');

        if (!audioToggleBtn || !audioIcon) return;

        audioToggleBtn.addEventListener('click', () => {
            const enabled = this.audioNotifier.toggle();

            if (enabled) {
                audioToggleBtn.classList.remove('muted');
                audioIcon.textContent = '🔊';
                audioToggleBtn.title = 'Mute sound notifications';
            } else {
                audioToggleBtn.classList.add('muted');
                audioIcon.textContent = '🔇';
                audioToggleBtn.title = 'Enable sound notifications for large transactions';
            }
        });

        // Timeframe selector for historical chart (T067)
        const timeframeSelector = document.getElementById('timeframe-selector');
        if (timeframeSelector && this.whaleChart) {
            timeframeSelector.addEventListener('change', (e) => {
                const timeframe = e.target.value;
                console.log(`Loading chart for timeframe: ${timeframe}`);
                this.whaleChart.loadChart(timeframe);
            });
        }

        // Alert configuration panel (T084)
        this.setupAlertConfigPanel();
    }

    setupAlertConfigPanel() {
        if (!this.alertSystem) {
            console.warn('Alert system not available, skipping config panel setup');
            return;
        }

        // Get DOM elements
        const alertSettingsBtn = document.getElementById('alert-settings-toggle');
        const alertOverlay = document.getElementById('alert-config-overlay');
        const alertCloseBtn = document.getElementById('alert-config-close');
        const alertCancelBtn = document.getElementById('alert-cancel-settings');
        const alertSaveBtn = document.getElementById('alert-save-settings');

        const soundEnabledCheckbox = document.getElementById('alert-sound-enabled');
        const soundVolumeSlider = document.getElementById('alert-sound-volume');
        const volumeValue = document.getElementById('alert-volume-value');

        const browserEnabledCheckbox = document.getElementById('alert-browser-enabled');
        const requestPermissionBtn = document.getElementById('alert-request-permission');
        const permissionStatus = document.getElementById('alert-permission-status');

        const thresholdCritical = document.getElementById('alert-threshold-critical');
        const thresholdHigh = document.getElementById('alert-threshold-high');
        const thresholdMedium = document.getElementById('alert-threshold-medium');

        const testCriticalBtn = document.getElementById('alert-test-critical');
        const testHighBtn = document.getElementById('alert-test-high');
        const testMediumBtn = document.getElementById('alert-test-medium');

        const alertHistoryList = document.getElementById('alert-history-list');
        const alertHistoryClear = document.getElementById('alert-history-clear');

        if (!alertSettingsBtn || !alertOverlay) {
            console.warn('Alert config panel elements not found');
            return;
        }

        // Open panel
        const openPanel = () => {
            alertOverlay.classList.remove('hidden');
            loadCurrentSettings();
        };

        // Close panel
        const closePanel = () => {
            alertOverlay.classList.add('hidden');
        };

        // Load current settings from alert system
        const loadCurrentSettings = () => {
            const prefs = this.alertSystem.getPreferences();

            if (soundEnabledCheckbox) soundEnabledCheckbox.checked = prefs.soundEnabled;
            if (soundVolumeSlider) soundVolumeSlider.value = prefs.soundVolume * 100;
            if (volumeValue) volumeValue.textContent = Math.round(prefs.soundVolume * 100) + '%';

            if (browserEnabledCheckbox) browserEnabledCheckbox.checked = prefs.browserEnabled;
            updatePermissionStatus();

            if (thresholdCritical) thresholdCritical.value = prefs.thresholds.critical;
            if (thresholdHigh) thresholdHigh.value = prefs.thresholds.high;
            if (thresholdMedium) thresholdMedium.value = prefs.thresholds.medium;

            // Update alert history
            updateAlertHistory();
        };

        // Update alert history display (T087)
        const updateAlertHistory = () => {
            if (!alertHistoryList) return;

            const history = this.alertSystem.getAlertHistory();

            if (history.length === 0) {
                alertHistoryList.innerHTML = '<div class="alert-history-empty">No alerts yet</div>';
                return;
            }

            // Build HTML for history items
            const historyHTML = history.map(alert => {
                const time = formatAlertTime(alert.timestamp);
                return `
                    <div class="alert-history-item">
                        <div class="alert-history-item-header">
                            <span class="alert-history-severity ${alert.severity}">
                                ${alert.severity.toUpperCase()}
                            </span>
                            <span class="alert-history-time">${time}</span>
                        </div>
                        <div class="alert-history-message">${alert.message}</div>
                        <div class="alert-history-details">
                            <span>Fee: ${alert.transaction.fee_rate.toFixed(1)} sat/vB</span>
                            <span>Urgency: ${alert.transaction.urgency_score}/100</span>
                        </div>
                    </div>
                `;
            }).join('');

            alertHistoryList.innerHTML = historyHTML;
        };

        // Format alert timestamp
        const formatAlertTime = (timestamp) => {
            const date = new Date(timestamp);
            const now = new Date();
            const diff = now - date;

            // Less than 1 minute
            if (diff < 60000) {
                return 'Just now';
            }

            // Less than 1 hour
            if (diff < 3600000) {
                const minutes = Math.floor(diff / 60000);
                return `${minutes}m ago`;
            }

            // Less than 24 hours
            if (diff < 86400000) {
                const hours = Math.floor(diff / 3600000);
                return `${hours}h ago`;
            }

            // Format as date
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
        };

        // Update permission status display
        const updatePermissionStatus = () => {
            if (!permissionStatus) return;

            const permission = this.alertSystem.notificationPermission;
            if (permission === 'granted') {
                permissionStatus.textContent = '✅ Granted';
                permissionStatus.style.color = 'var(--color-accent-buy)';
            } else if (permission === 'denied') {
                permissionStatus.textContent = '❌ Denied';
                permissionStatus.style.color = 'var(--color-accent-sell)';
            } else {
                permissionStatus.textContent = '⚠️ Not granted';
                permissionStatus.style.color = 'var(--color-text-muted)';
            }
        };

        // Save settings
        const saveSettings = () => {
            const newPrefs = {
                soundEnabled: soundEnabledCheckbox?.checked ?? true,
                soundVolume: soundVolumeSlider ? parseFloat(soundVolumeSlider.value) / 100 : 0.5,
                browserEnabled: browserEnabledCheckbox?.checked ?? true,
                thresholds: {
                    critical: thresholdCritical ? parseFloat(thresholdCritical.value) : 500,
                    high: thresholdHigh ? parseFloat(thresholdHigh.value) : 200,
                    medium: thresholdMedium ? parseFloat(thresholdMedium.value) : 100
                }
            };

            this.alertSystem.updatePreferences(newPrefs);
            closePanel();

            console.log('Alert settings saved:', newPrefs);
        };

        // Event listeners
        alertSettingsBtn.addEventListener('click', openPanel);
        if (alertCloseBtn) alertCloseBtn.addEventListener('click', closePanel);
        if (alertCancelBtn) alertCancelBtn.addEventListener('click', closePanel);
        if (alertSaveBtn) alertSaveBtn.addEventListener('click', saveSettings);

        // Close on overlay click (but not panel click)
        alertOverlay.addEventListener('click', (e) => {
            if (e.target === alertOverlay) {
                closePanel();
            }
        });

        // Volume slider update
        if (soundVolumeSlider && volumeValue) {
            soundVolumeSlider.addEventListener('input', (e) => {
                volumeValue.textContent = Math.round(e.target.value) + '%';
            });
        }

        // Request browser permission
        if (requestPermissionBtn) {
            requestPermissionBtn.addEventListener('click', async () => {
                const granted = await this.alertSystem.requestNotificationPermission();
                updatePermissionStatus();

                if (granted) {
                    console.log('Browser notification permission granted');
                } else {
                    console.warn('Browser notification permission denied');
                }
            });
        }

        // Test alert buttons
        if (testCriticalBtn) {
            testCriticalBtn.addEventListener('click', () => {
                this.alertSystem.testAlert('critical');
            });
        }

        if (testHighBtn) {
            testHighBtn.addEventListener('click', () => {
                this.alertSystem.testAlert('high');
            });
        }

        if (testMediumBtn) {
            testMediumBtn.addEventListener('click', () => {
                this.alertSystem.testAlert('medium');
            });
        }

        // Clear alert history (T087)
        if (alertHistoryClear) {
            alertHistoryClear.addEventListener('click', () => {
                this.alertSystem.clearHistory();
                updateAlertHistory();
                console.log('Alert history cleared');
            });
        }

        // Listen for whale-alert events to update history automatically
        window.addEventListener('whale-alert', () => {
            // If panel is open, update history in real-time
            if (!alertOverlay.classList.contains('hidden')) {
                updateAlertHistory();
            }
        });

        console.log('Alert configuration panel setup complete');
    }

    async initialize() {
        console.log('Initializing Whale Detection Dashboard...');

        this.ui.showLoading();
        this.ui.updateConnectionStatus(false, 'Connecting...');

        // Initialize WebSocket if enabled
        if (this.useWebSocket) {
            this.initializeWebSocket();
        } else {
            console.log('WebSocket disabled - using HTTP polling');
        }

        // Initial data fetch (HTTP fallback)
        const result = await this.api.fetchLatest();

        if (result.success) {
            this.handleDataUpdate(result.data);
            if (!this.useWebSocket) {
                this.startPolling();
            }
        } else {
            this.handleError(result.error);
        }

        // Initialize historical chart (T065)
        if (this.whaleChart) {
            try {
                await this.whaleChart.init('24h'); // Default 24h timeframe
                console.log('Historical chart loaded successfully');
            } catch (error) {
                console.error('Failed to initialize historical chart:', error);
            }
        }
    }

    // ========================================
    // WebSocket Management
    // ========================================

    initializeWebSocket() {
        if (!CONFIG.jwtToken) {
            console.warn('No JWT token available for WebSocket');
            return;
        }

        console.log('Initializing WebSocket client...');
        this.wsClient = new WhaleWebSocketClient(CONFIG.jwtToken);

        // Connection events
        this.wsClient.on(EventType.CONNECTED, () => {
            console.log('WebSocket connected successfully');
            this.state.connected = true;
            this.ui.updateConnectionStatus(true);

            // Stop HTTP polling when WebSocket connects
            this.stopPolling();
        });

        this.wsClient.on(EventType.DISCONNECTED, (data) => {
            console.log('WebSocket disconnected:', data.reason);
            this.state.connected = false;
            this.ui.updateConnectionStatus(false, 'WebSocket disconnected');

            // Fallback to HTTP polling
            this.startPolling();
        });

        this.wsClient.on(EventType.ERROR, (data) => {
            console.error('WebSocket error:', data.message);
        });

        this.wsClient.on(EventType.TOKEN_EXPIRED, () => {
            console.warn('JWT token expired - need to refresh');
            this.ui.updateConnectionStatus(false, 'Token expired');
            // TODO: Implement token refresh logic
        });

        // Data events
        this.wsClient.on(EventType.TRANSACTION, (tx) => {
            console.log('New transaction received:', tx);
            if (this.transactionFeed) {
                this.transactionFeed.addTransaction(tx);
            }
            // Audio notification for large transactions (T060)
            if (this.audioNotifier) {
                this.audioNotifier.notifyTransaction(tx);
            }
            // Alert system processing (T079-T083)
            if (this.alertSystem) {
                this.alertSystem.processTransaction(tx);
            }
        });

        this.wsClient.on(EventType.NETFLOW, (netflowData) => {
            console.log('Net flow update received:', netflowData);
            this.handleNetFlowUpdate(netflowData);
        });

        this.wsClient.on(EventType.ALERT, (alert) => {
            console.log('Alert received:', alert);
            // TODO: Handle alerts (Phase 9)
        });

        this.wsClient.on(EventType.RATE_LIMITED, (data) => {
            console.warn('Rate limited:', data);
        });

        this.wsClient.on(EventType.SUBSCRIPTION_ACK, (data) => {
            console.log('Subscription acknowledged:', data.channels);
        });

        // Connect
        this.wsClient.connect();
    }

    handleNetFlowUpdate(netflowData) {
        // Update state with net flow data
        const data = {
            whale_net_flow: netflowData.net_flow_btc,
            whale_direction: netflowData.direction,
            btc_price: netflowData.net_flow_usd / netflowData.net_flow_btc
        };

        this.state.updateNetFlow(data);
        this.state.connected = true;
        this.state.loading = false;

        this.ui.updateLastUpdate(this.state.lastUpdate);
        this.ui.updateNetFlowDisplay(this.state.netFlowData);
        this.ui.updateDirectionIndicator(this.state.netFlowData.direction);
        this.ui.showContent();
    }

    handleDataUpdate(data) {
        this.state.updateNetFlow(data);
        this.state.connected = true;
        this.state.loading = false;

        this.ui.updateConnectionStatus(true);
        this.ui.updateLastUpdate(this.state.lastUpdate);
        this.ui.updateNetFlowDisplay(this.state.netFlowData);
        this.ui.updateDirectionIndicator(this.state.netFlowData.direction);
        this.ui.showContent();

        console.log('Data updated:', {
            netFlow: this.state.netFlowData.btc,
            direction: this.state.netFlowData.direction,
            timestamp: this.state.lastUpdate.toISOString()
        });
    }

    handleError(errorMessage) {
        this.state.markError(errorMessage);
        this.state.connected = false;

        this.ui.updateConnectionStatus(false, 'Connection failed');
        this.ui.showError(errorMessage || 'Unable to connect to API');

        console.error('Dashboard error:', errorMessage);

        // Retry logic
        if (this.state.retryCount < CONFIG.maxRetries) {
            console.log(`Retrying in ${CONFIG.retryDelay / 1000}s... (attempt ${this.state.retryCount}/${CONFIG.maxRetries})`);
            setTimeout(() => this.initialize(), CONFIG.retryDelay);
        }
    }

    startPolling() {
        if (this.state.pollTimer) {
            clearInterval(this.state.pollTimer);
        }

        console.log(`Starting polling (interval: ${CONFIG.pollInterval / 1000}s)`);

        this.state.pollTimer = setInterval(async () => {
            const result = await this.api.fetchLatest();

            if (result.success) {
                this.handleDataUpdate(result.data);
            } else {
                console.warn('Poll failed:', result.error);
                // Don't show error UI for intermittent failures, just log
                // Only show error if multiple consecutive failures occur
            }
        }, CONFIG.pollInterval);
    }

    stopPolling() {
        if (this.state.pollTimer) {
            console.log('Stopping polling');
            clearInterval(this.state.pollTimer);
            this.state.pollTimer = null;
        }
    }
}

// ============================================
// Initialize Dashboard
// ============================================

// Wait for DOM to be ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDashboard);
} else {
    initDashboard();
}

function initDashboard() {
    console.log('DOM ready, starting dashboard...');

    // Create global dashboard instance
    window.whaleDashboard = new WhaleDashboard();

    // Handle cleanup on page unload
    window.addEventListener('beforeunload', () => {
        if (window.whaleDashboard) {
            window.whaleDashboard.stopPolling();
        }
    });
}

// Export for testing
export { WhaleDashboard, formatNumber, formatBTC, formatUSD };
