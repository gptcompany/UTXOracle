/**
 * UTXOracle Whale Alert System
 * Multi-channel notification system for critical whale movements
 *
 * Tasks Implemented:
 * - T079: Alert system architecture
 * - T080: Toast notifications (always enabled)
 * - T081: Browser notification permission request
 * - T082: Browser notifications when permitted
 * - T083: Alert sound for critical alerts (>500 BTC)
 * - T084: Alert configuration panel
 * - T085: localStorage preferences persistence
 *
 * Alert Channels:
 * 1. Toast notifications - Always visible, non-intrusive
 * 2. Browser notifications - Requires permission, even when tab inactive
 * 3. Sound alerts - Optional, for critical transactions
 */

// ============================================
// Configuration
// ============================================

const ALERT_CONFIG = {
    // Alert thresholds
    thresholds: {
        critical: 500,      // BTC - Critical alert (sound + all notifications)
        high: 200,          // BTC - High priority alert
        medium: 100         // BTC - Medium priority alert
    },

    // Toast notification settings
    toast: {
        duration: 5000,         // 5 seconds
        maxToasts: 3,           // Max simultaneous toasts
        position: 'top-right'   // top-left, top-right, bottom-left, bottom-right
    },

    // Sound settings
    sound: {
        enabled: true,          // Can be toggled by user
        volume: 0.5             // 0.0 to 1.0
    },

    // Browser notification settings
    browser: {
        enabled: true,          // Request permission on first use
        requireInteraction: false  // Auto-close after duration
    }
};

// ============================================
// Alert System Class
// ============================================

class WhaleAlertSystem {
    constructor(config = ALERT_CONFIG) {
        this.config = config;

        // Load preferences from localStorage
        this.loadPreferences();

        // Toast container
        this.toastContainer = null;

        // Alert history (last 10 alerts)
        this.alertHistory = [];
        this.maxHistory = 10;

        // Browser notification permission state
        this.notificationPermission = 'default';

        // Sound element
        this.soundElement = null;

        // Initialize
        this.init();
    }

    // ========================================
    // Initialization
    // ========================================

    init() {
        // Create toast container
        this.createToastContainer();

        // Check browser notification permission
        this.checkNotificationPermission();

        // Create sound element
        this.createSoundElement();

        console.log('Whale Alert System initialized');
    }

    createToastContainer() {
        this.toastContainer = document.createElement('div');
        this.toastContainer.id = 'whale-toast-container';
        this.toastContainer.className = `toast-container toast-${this.config.toast.position}`;
        document.body.appendChild(this.toastContainer);
    }

    createSoundElement() {
        // Create audio element for alert sound
        this.soundElement = document.createElement('audio');
        this.soundElement.id = 'whale-alert-sound';
        this.soundElement.volume = this.config.sound.volume;

        // Use data URL for simple beep sound (440Hz sine wave)
        // In production, replace with actual audio file
        this.soundElement.src = this.generateBeepSound();

        document.body.appendChild(this.soundElement);
    }

    generateBeepSound() {
        // Generate simple beep using data URL
        // In production, use: '/static/sounds/alert.mp3'
        return 'data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBiuBz/DUgzUGIGm676FVFAo+j7/v';
    }

    // ========================================
    // Alert Processing (T079-T083)
    // ========================================

    processTransaction(tx) {
        // Determine alert severity based on amount
        const severity = this.getAlertSeverity(tx.amount_btc);

        if (!severity) {
            return; // No alert needed
        }

        // Create alert object
        const alert = {
            id: `alert-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
            timestamp: new Date().toISOString(),
            transaction: tx,
            severity: severity,
            message: this.createAlertMessage(tx, severity)
        };

        // Add to history
        this.addToHistory(alert);

        // Send alerts through all enabled channels
        this.sendToast(alert);

        if (this.config.browser.enabled && this.notificationPermission === 'granted') {
            this.sendBrowserNotification(alert);
        }

        if (severity === 'critical' && this.config.sound.enabled) {
            this.playAlertSound();
        }

        // Emit event for dashboard integration
        this.emitAlertEvent(alert);
    }

    getAlertSeverity(amountBTC) {
        if (amountBTC >= this.config.thresholds.critical) {
            return 'critical';
        } else if (amountBTC >= this.config.thresholds.high) {
            return 'high';
        } else if (amountBTC >= this.config.thresholds.medium) {
            return 'medium';
        }
        return null; // No alert
    }

    createAlertMessage(tx, severity) {
        const emoji = {
            critical: '🚨',
            high: '⚠️',
            medium: '📊'
        }[severity];

        const direction = tx.direction === 'BUY' ? '↑' : '↓';

        return `${emoji} ${direction} ${tx.amount_btc.toFixed(2)} BTC (${this.formatUSD(tx.amount_usd)})`;
    }

    formatUSD(usd) {
        if (usd >= 1e9) {
            return '$' + (usd / 1e9).toFixed(2) + 'B';
        } else if (usd >= 1e6) {
            return '$' + (usd / 1e6).toFixed(2) + 'M';
        } else if (usd >= 1e3) {
            return '$' + (usd / 1e3).toFixed(2) + 'K';
        }
        return '$' + usd.toFixed(2);
    }

    // ========================================
    // Toast Notifications (T080)
    // ========================================

    sendToast(alert) {
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `whale-toast whale-toast-${alert.severity}`;
        toast.id = alert.id;

        toast.innerHTML = `
            <div class="toast-header">
                <span class="toast-title">${alert.severity.toUpperCase()} WHALE ALERT</span>
                <button class="toast-close" onclick="this.parentElement.parentElement.remove()">×</button>
            </div>
            <div class="toast-body">
                <div class="toast-message">${alert.message}</div>
                <div class="toast-details">
                    <span>Fee: ${alert.transaction.fee_rate.toFixed(1)} sat/vB</span>
                    <span>Urgency: ${alert.transaction.urgency_score}/100</span>
                </div>
            </div>
        `;

        // Add to container
        this.toastContainer.appendChild(toast);

        // Trigger fade-in animation
        setTimeout(() => {
            toast.classList.add('toast-visible');
        }, 10);

        // Auto-remove after duration
        setTimeout(() => {
            toast.classList.remove('toast-visible');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.remove();
                }
            }, 300);
        }, this.config.toast.duration);

        // Limit number of toasts
        this.limitToasts();
    }

    limitToasts() {
        const toasts = this.toastContainer.querySelectorAll('.whale-toast');
        if (toasts.length > this.config.toast.maxToasts) {
            // Remove oldest toast
            toasts[0].remove();
        }
    }

    // ========================================
    // Browser Notifications (T081-T082)
    // ========================================

    checkNotificationPermission() {
        if ('Notification' in window) {
            this.notificationPermission = Notification.permission;
        }
    }

    async requestNotificationPermission() {
        if (!('Notification' in window)) {
            console.warn('Browser notifications not supported');
            return false;
        }

        if (Notification.permission === 'granted') {
            this.notificationPermission = 'granted';
            return true;
        }

        if (Notification.permission !== 'denied') {
            const permission = await Notification.requestPermission();
            this.notificationPermission = permission;
            this.savePreferences();
            return permission === 'granted';
        }

        return false;
    }

    sendBrowserNotification(alert) {
        if (!('Notification' in window)) {
            return;
        }

        if (Notification.permission !== 'granted') {
            return;
        }

        const options = {
            body: alert.message,
            icon: '/static/favicon.ico', // Replace with actual icon path
            badge: '/static/badge.png',  // Replace with actual badge path
            tag: alert.id,
            requireInteraction: this.config.browser.requireInteraction,
            data: {
                transactionId: alert.transaction.transaction_id,
                amount: alert.transaction.amount_btc
            }
        };

        const notification = new Notification('UTXOracle Whale Alert', options);

        // Handle click event
        notification.onclick = () => {
            window.focus();
            notification.close();

            // Emit event to show transaction details
            this.emitTransactionClickEvent(alert.transaction);
        };
    }

    // ========================================
    // Sound Alerts (T083)
    // ========================================

    playAlertSound() {
        if (!this.config.sound.enabled || !this.soundElement) {
            return;
        }

        try {
            // Reset playback
            this.soundElement.currentTime = 0;
            this.soundElement.play();
        } catch (error) {
            console.error('Failed to play alert sound:', error);
        }
    }

    // ========================================
    // Preferences Management (T085)
    // ========================================

    loadPreferences() {
        try {
            const saved = localStorage.getItem('whale-alert-preferences');
            if (saved) {
                const prefs = JSON.parse(saved);

                // Apply saved preferences
                this.config.sound.enabled = prefs.soundEnabled !== undefined ? prefs.soundEnabled : true;
                this.config.sound.volume = prefs.soundVolume !== undefined ? prefs.soundVolume : 0.5;
                this.config.browser.enabled = prefs.browserEnabled !== undefined ? prefs.browserEnabled : true;

                // Apply thresholds if saved
                if (prefs.thresholds) {
                    Object.assign(this.config.thresholds, prefs.thresholds);
                }
            }
        } catch (error) {
            console.error('Failed to load alert preferences:', error);
        }
    }

    savePreferences() {
        try {
            const prefs = {
                soundEnabled: this.config.sound.enabled,
                soundVolume: this.config.sound.volume,
                browserEnabled: this.config.browser.enabled,
                thresholds: this.config.thresholds
            };

            localStorage.setItem('whale-alert-preferences', JSON.stringify(prefs));
        } catch (error) {
            console.error('Failed to save alert preferences:', error);
        }
    }

    updatePreferences(newPrefs) {
        // Update configuration
        if (newPrefs.soundEnabled !== undefined) {
            this.config.sound.enabled = newPrefs.soundEnabled;
        }

        if (newPrefs.soundVolume !== undefined) {
            this.config.sound.volume = newPrefs.soundVolume;
            if (this.soundElement) {
                this.soundElement.volume = newPrefs.soundVolume;
            }
        }

        if (newPrefs.browserEnabled !== undefined) {
            this.config.browser.enabled = newPrefs.browserEnabled;

            // Request permission if enabling
            if (newPrefs.browserEnabled && this.notificationPermission !== 'granted') {
                this.requestNotificationPermission();
            }
        }

        if (newPrefs.thresholds) {
            Object.assign(this.config.thresholds, newPrefs.thresholds);
        }

        // Save to localStorage
        this.savePreferences();
    }

    // ========================================
    // Alert History
    // ========================================

    addToHistory(alert) {
        this.alertHistory.unshift(alert);

        // Keep only last N alerts
        if (this.alertHistory.length > this.maxHistory) {
            this.alertHistory.pop();
        }
    }

    getAlertHistory() {
        return [...this.alertHistory];
    }

    clearHistory() {
        this.alertHistory = [];
    }

    // ========================================
    // Event Emitters
    // ========================================

    emitAlertEvent(alert) {
        const event = new CustomEvent('whale-alert', {
            detail: alert
        });
        window.dispatchEvent(event);
    }

    emitTransactionClickEvent(transaction) {
        const event = new CustomEvent('whale-alert-transaction-click', {
            detail: transaction
        });
        window.dispatchEvent(event);
    }

    // ========================================
    // Public API
    // ========================================

    getPreferences() {
        return {
            soundEnabled: this.config.sound.enabled,
            soundVolume: this.config.sound.volume,
            browserEnabled: this.config.browser.enabled,
            thresholds: { ...this.config.thresholds }
        };
    }

    testAlert(severity = 'medium') {
        // Create test transaction
        const testTx = {
            transaction_id: 'test-' + Date.now(),
            timestamp: new Date().toISOString(),
            amount_btc: this.config.thresholds[severity] + 10,
            amount_usd: (this.config.thresholds[severity] + 10) * 95000,
            direction: 'SELL',
            urgency_score: 85,
            fee_rate: 50.5,
            is_mempool: true
        };

        this.processTransaction(testTx);
    }
}

// ============================================
// Export
// ============================================

export { WhaleAlertSystem, ALERT_CONFIG };
