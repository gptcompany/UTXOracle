/**
 * UTXOracle Transaction Details Modal
 * Displays full transaction information in overlay modal
 *
 * Task: T056 - Transaction details modal
 *
 * Features:
 * - Modal overlay with transaction details
 * - Full transaction ID, amounts, direction, urgency
 * - Block height, confirmation status
 * - Close via button, ESC key, or click outside
 * - Responsive design
 */

// ============================================
// Transaction Details Modal
// ============================================

class TransactionModal {
    constructor() {
        this.modal = null;
        this.isOpen = false;
        this.currentTransaction = null;

        this.init();
    }

    // ========================================
    // Initialization
    // ========================================

    init() {
        this.createModal();
        this.setupEventListeners();
    }

    createModal() {
        // Create modal HTML structure
        const modalHTML = `
            <div class="modal-overlay hidden" id="transaction-modal">
                <div class="modal-container">
                    <div class="modal-header">
                        <h2 class="modal-title">Transaction Details</h2>
                        <button class="modal-close" id="modal-close" aria-label="Close modal">
                            ×
                        </button>
                    </div>

                    <div class="modal-body" id="modal-body">
                        <!-- Content will be dynamically inserted -->
                    </div>

                    <div class="modal-footer">
                        <button class="modal-button modal-button-secondary" id="modal-copy">
                            Copy TX ID
                        </button>
                        <button class="modal-button modal-button-primary" id="modal-explorer">
                            View in Explorer →
                        </button>
                    </div>
                </div>
            </div>
        `;

        // Append to body
        document.body.insertAdjacentHTML('beforeend', modalHTML);

        // Store reference
        this.modal = document.getElementById('transaction-modal');
        this.modalBody = document.getElementById('modal-body');
    }

    setupEventListeners() {
        // Close button
        const closeBtn = document.getElementById('modal-close');
        closeBtn.addEventListener('click', () => this.close());

        // Click outside modal
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) {
                this.close();
            }
        });

        // ESC key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen) {
                this.close();
            }
        });

        // Copy TX ID button
        const copyBtn = document.getElementById('modal-copy');
        copyBtn.addEventListener('click', () => this.copyTransactionId());

        // Explorer button
        const explorerBtn = document.getElementById('modal-explorer');
        explorerBtn.addEventListener('click', () => this.openExplorer());
    }

    // ========================================
    // Public API
    // ========================================

    show(transaction) {
        this.currentTransaction = transaction;
        this.renderTransactionDetails(transaction);
        this.open();
    }

    open() {
        this.modal.classList.remove('hidden');
        this.isOpen = true;

        // Prevent body scroll
        document.body.style.overflow = 'hidden';

        // Focus close button for accessibility
        setTimeout(() => {
            const closeBtn = document.getElementById('modal-close');
            closeBtn.focus();
        }, 100);
    }

    close() {
        this.modal.classList.add('hidden');
        this.isOpen = false;

        // Restore body scroll
        document.body.style.overflow = '';

        // Clear current transaction
        this.currentTransaction = null;
    }

    // ========================================
    // Rendering
    // ========================================

    renderTransactionDetails(tx) {
        const detailsHTML = `
            <div class="detail-section">
                <h3 class="detail-section-title">Transaction ID</h3>
                <div class="detail-value tx-id-display">
                    <code>${tx.transaction_id}</code>
                </div>
            </div>

            <div class="detail-section">
                <h3 class="detail-section-title">Amount</h3>
                <div class="detail-grid">
                    <div class="detail-item">
                        <span class="detail-label">BTC</span>
                        <span class="detail-value">${this.formatBTC(tx.amount_btc)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">USD</span>
                        <span class="detail-value">${this.formatUSD(tx.amount_usd)}</span>
                    </div>
                </div>
            </div>

            <div class="detail-section">
                <h3 class="detail-section-title">Transaction Details</h3>
                <div class="detail-grid">
                    <div class="detail-item">
                        <span class="detail-label">Direction</span>
                        <span class="detail-value">
                            <span class="direction-badge direction-${tx.direction.toLowerCase()}">
                                ${this.getDirectionSymbol(tx.direction)} ${tx.direction}
                            </span>
                        </span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Urgency Score</span>
                        <span class="detail-value">
                            <span class="urgency-badge urgency-${this.getUrgencyClass(tx.urgency_score)}">
                                ${tx.urgency_score}/100
                            </span>
                        </span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Fee Rate</span>
                        <span class="detail-value">${tx.fee_rate.toFixed(1)} sat/vB</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Confidence</span>
                        <span class="detail-value">${(tx.confidence * 100).toFixed(1)}%</span>
                    </div>
                </div>
            </div>

            <div class="detail-section">
                <h3 class="detail-section-title">Blockchain Status</h3>
                <div class="detail-grid">
                    <div class="detail-item">
                        <span class="detail-label">Status</span>
                        <span class="detail-value">
                            ${tx.is_mempool
                                ? '<span class="status-badge status-mempool">📡 Mempool</span>'
                                : '<span class="status-badge status-confirmed">✅ Confirmed</span>'
                            }
                        </span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Block Height</span>
                        <span class="detail-value">${tx.block_height || 'Pending'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Timestamp</span>
                        <span class="detail-value">${this.formatFullTimestamp(tx.timestamp)}</span>
                    </div>
                </div>
            </div>
        `;

        this.modalBody.innerHTML = detailsHTML;
    }

    // ========================================
    // Formatting Utilities
    // ========================================

    formatBTC(btc) {
        return parseFloat(btc).toFixed(8) + ' BTC';
    }

    formatUSD(usd) {
        if (usd >= 1e9) {
            return '$' + (usd / 1e9).toFixed(2) + 'B';
        } else if (usd >= 1e6) {
            return '$' + (usd / 1e6).toFixed(2) + 'M';
        } else if (usd >= 1e3) {
            return '$' + (usd / 1e3).toFixed(2) + 'K';
        } else {
            return '$' + usd.toFixed(2);
        }
    }

    formatFullTimestamp(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    getDirectionSymbol(direction) {
        switch (direction) {
            case 'BUY':
            case 'ACCUMULATION':
                return '↑';
            case 'SELL':
            case 'DISTRIBUTION':
                return '↓';
            default:
                return '→';
        }
    }

    getUrgencyClass(score) {
        if (score >= 80) return 'high';
        if (score >= 50) return 'medium';
        return 'low';
    }

    // ========================================
    // Actions
    // ========================================

    copyTransactionId() {
        if (!this.currentTransaction) return;

        const txId = this.currentTransaction.transaction_id;

        // Modern Clipboard API
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(txId)
                .then(() => {
                    this.showCopySuccess();
                })
                .catch(err => {
                    console.error('Failed to copy:', err);
                    this.fallbackCopy(txId);
                });
        } else {
            this.fallbackCopy(txId);
        }
    }

    fallbackCopy(text) {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.select();

        try {
            document.execCommand('copy');
            this.showCopySuccess();
        } catch (err) {
            console.error('Fallback copy failed:', err);
        }

        document.body.removeChild(textArea);
    }

    showCopySuccess() {
        const copyBtn = document.getElementById('modal-copy');
        const originalText = copyBtn.textContent;

        copyBtn.textContent = '✓ Copied!';
        copyBtn.classList.add('button-success');

        setTimeout(() => {
            copyBtn.textContent = originalText;
            copyBtn.classList.remove('button-success');
        }, 2000);
    }

    openExplorer() {
        if (!this.currentTransaction) return;

        const txId = this.currentTransaction.transaction_id;

        // Default to mempool.space
        const explorerUrl = `https://mempool.space/tx/${txId}`;

        window.open(explorerUrl, '_blank');
    }
}

// ============================================
// Export
// ============================================

export { TransactionModal };
