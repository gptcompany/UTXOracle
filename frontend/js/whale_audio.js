/**
 * UTXOracle Audio Notification System
 * Simple sound alerts for large whale transactions
 *
 * Task: T060 - Sound notifications
 *
 * Features:
 * - Browser AudioContext (no external files)
 * - Simple beep for large transactions (>500 BTC)
 * - Mute/unmute toggle
 * - Respects user interaction requirement for audio
 *
 * KISS: Native Web Audio API, no dependencies, no complexity
 */

// ============================================
// Audio Notification Manager
// ============================================

class WhaleAudioNotifier {
    constructor(config = {}) {
        this.config = {
            largeTransactionThreshold: config.largeTransactionThreshold || 500, // BTC
            enabled: false, // Start muted (requires user interaction)
            frequency: 800, // Hz
            duration: 0.15, // seconds
            volume: 0.3 // 0-1
        };

        this.audioContext = null;
        this.initialized = false;
    }

    // ========================================
    // Initialization
    // ========================================

    init() {
        // AudioContext requires user interaction
        // We'll initialize on first unmute
        this.initialized = true;
    }

    createAudioContext() {
        if (!this.audioContext) {
            try {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            } catch (error) {
                console.error('Failed to create AudioContext:', error);
                return false;
            }
        }
        return true;
    }

    // ========================================
    // Public API
    // ========================================

    enable() {
        // Create AudioContext on first enable (user interaction)
        if (!this.createAudioContext()) {
            return false;
        }

        this.config.enabled = true;
        console.log('Audio notifications enabled');
        return true;
    }

    disable() {
        this.config.enabled = false;
        console.log('Audio notifications disabled');
    }

    toggle() {
        if (this.config.enabled) {
            this.disable();
            return false;
        } else {
            return this.enable();
        }
    }

    isEnabled() {
        return this.config.enabled;
    }

    // ========================================
    // Notification Logic
    // ========================================

    notifyTransaction(transaction) {
        // Check if notifications enabled
        if (!this.config.enabled || !this.audioContext) {
            return;
        }

        // Check if transaction is large enough
        const amountBTC = parseFloat(transaction.amount_btc);
        if (amountBTC < this.config.largeTransactionThreshold) {
            return;
        }

        // Play notification sound
        this.playBeep();
        console.log(`🔊 Audio alert: Large transaction ${amountBTC.toFixed(2)} BTC`);
    }

    // ========================================
    // Sound Generation
    // ========================================

    playBeep() {
        if (!this.audioContext) {
            return;
        }

        const now = this.audioContext.currentTime;

        // Create oscillator (tone generator)
        const oscillator = this.audioContext.createOscillator();
        const gainNode = this.audioContext.createGain();

        // Connect: oscillator -> gain -> output
        oscillator.connect(gainNode);
        gainNode.connect(this.audioContext.destination);

        // Configure sound
        oscillator.frequency.value = this.config.frequency;
        oscillator.type = 'sine'; // Smooth tone

        // Configure volume with envelope (fade in/out)
        gainNode.gain.setValueAtTime(0, now);
        gainNode.gain.linearRampToValueAtTime(this.config.volume, now + 0.01); // Fade in
        gainNode.gain.exponentialRampToValueAtTime(0.01, now + this.config.duration); // Fade out

        // Play
        oscillator.start(now);
        oscillator.stop(now + this.config.duration);

        // Cleanup
        oscillator.onended = () => {
            oscillator.disconnect();
            gainNode.disconnect();
        };
    }

    // ========================================
    // Configuration
    // ========================================

    setThreshold(btcAmount) {
        this.config.largeTransactionThreshold = btcAmount;
    }

    setVolume(volume) {
        this.config.volume = Math.max(0, Math.min(1, volume)); // Clamp 0-1
    }
}

// ============================================
// Export
// ============================================

export { WhaleAudioNotifier };
