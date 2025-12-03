/**
 * UTXOracle Transaction Feed Component
 * Displays real-time whale transactions in a scrollable feed
 *
 * Tasks Implemented:
 * - T052: Transaction feed table component
 * - T053: Display transaction fields (time, amount, direction, urgency, fee rate)
 * - T054: Ring buffer (max 50 transactions)
 * - T055: Auto-scroll with pause on hover
 * - T072: Urgency progress bar display (0-100)
 * - T073: Color-coded urgency (red/yellow/green)
 * - T074: Sortable columns (time, amount, urgency, fee rate)
 * - T076: Urgency calculation breakdown tooltip
 *
 * Features:
 * - Circular buffer (FIFO, max 50 transactions)
 * - Auto-scroll with pause on hover/focus
 * - Color-coded by direction (BUY/SELL/NEUTRAL)
 * - Urgency score progress bar with color coding
 * - Sortable table headers with visual indicators
 * - Responsive table layout
 */

// ============================================
// Configuration
// ============================================

const FEED_CONFIG = {
    maxTransactions: 50,        // Ring buffer size
    autoScrollEnabled: true,    // Auto-scroll to newest
    pauseOnHover: true,         // Pause scroll on hover
    animationDuration: 300,     // Row fade-in animation (ms)
    urgencyThresholds: {
        high: 80,               // High urgency >= 80
        medium: 50,             // Medium urgency >= 50
        low: 0                  // Low urgency < 50
    }
};

// ============================================
// Ring Buffer
// ============================================

class RingBuffer {
    constructor(maxSize) {
        this.maxSize = maxSize;
        this.buffer = [];
    }

    push(item) {
        // Add to end
        this.buffer.push(item);

        // Remove from beginning if over limit
        if (this.buffer.length > this.maxSize) {
            this.buffer.shift();
        }
    }

    getAll() {
        return [...this.buffer];
    }

    clear() {
        this.buffer = [];
    }

    size() {
        return this.buffer.length;
    }

    isEmpty() {
        return this.buffer.length === 0;
    }
}

// ============================================
// Transaction Feed Component
// ============================================

class TransactionFeed {
    constructor(containerId, config = FEED_CONFIG) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Transaction feed container not found: ${containerId}`);
        }

        this.config = config;
        this.transactions = new RingBuffer(config.maxTransactions);

        // State
        this.isPaused = false;
        this.autoScrollEnabled = config.autoScrollEnabled;
        this.emptyState = null;

        // Sort state (T074)
        this.sortColumn = null;         // Column to sort by (time, amount, urgency, fee)
        this.sortDirection = 'desc';    // 'asc' or 'desc'

        // Initialize UI
        this.init();
    }

    // ========================================
    // Initialization
    // ========================================

    init() {
        // Save reference to empty state
        this.emptyState = this.container.querySelector('.feed-empty-state');

        // Create table structure
        this.createTable();

        // Setup hover/focus pause behavior
        if (this.config.pauseOnHover) {
            this.setupPauseBehavior();
        }
    }

    createTable() {
        const table = document.createElement('table');
        table.className = 'transaction-table';
        table.innerHTML = `
            <thead>
                <tr>
                    <th class="col-time sortable" data-sort="time">
                        Time <span class="sort-indicator"></span>
                    </th>
                    <th class="col-amount sortable" data-sort="amount">
                        Amount (BTC) <span class="sort-indicator"></span>
                    </th>
                    <th class="col-usd">USD Value</th>
                    <th class="col-direction">Direction</th>
                    <th class="col-urgency sortable" data-sort="urgency">
                        Urgency <span class="sort-indicator"></span>
                    </th>
                    <th class="col-fee sortable" data-sort="fee">
                        Fee Rate <span class="sort-indicator"></span>
                    </th>
                </tr>
            </thead>
            <tbody id="transaction-tbody">
                <!-- Rows will be added here -->
            </tbody>
        `;

        this.table = table;
        this.tbody = table.querySelector('#transaction-tbody');

        // Hide table initially (show empty state)
        table.classList.add('hidden');

        // Setup sort behavior (T074)
        this.setupSortBehavior();
    }

    setupPauseBehavior() {
        this.container.addEventListener('mouseenter', () => {
            this.pause();
        });

        this.container.addEventListener('mouseleave', () => {
            this.resume();
        });

        // Also pause when user is selecting text
        this.container.addEventListener('selectstart', () => {
            this.pause();
        });
    }

    setupSortBehavior() {
        // Add click handlers to sortable headers (T074)
        const sortableHeaders = this.table.querySelectorAll('th.sortable');

        sortableHeaders.forEach(header => {
            header.addEventListener('click', () => {
                const column = header.dataset.sort;
                this.handleSort(column);
            });

            // Visual feedback on hover
            header.style.cursor = 'pointer';
        });
    }

    // ========================================
    // Public API
    // ========================================

    addTransaction(tx) {
        // Add to ring buffer
        this.transactions.push(tx);

        // Show table if first transaction
        if (this.transactions.size() === 1) {
            this.showTable();
        }

        // Render new row
        this.renderTransaction(tx);

        // Auto-scroll to bottom if enabled and not paused
        if (this.autoScrollEnabled && !this.isPaused) {
            this.scrollToBottom();
        }
    }

    clear() {
        this.transactions.clear();
        this.tbody.innerHTML = '';
        this.hideTable();
    }

    pause() {
        this.isPaused = true;
        this.container.classList.add('paused');
    }

    resume() {
        this.isPaused = false;
        this.container.classList.remove('paused');

        // Scroll to bottom when resuming
        if (this.autoScrollEnabled) {
            this.scrollToBottom();
        }
    }

    toggleAutoScroll() {
        this.autoScrollEnabled = !this.autoScrollEnabled;
    }

    getTransactions() {
        return this.transactions.getAll();
    }

    // ========================================
    // Filtering (T057)
    // ========================================

    setFilters(filters) {
        this.filters = {
            minAmount: filters.minAmount || 0,
            directions: filters.directions || ['BUY', 'SELL', 'NEUTRAL'],
            minUrgency: filters.minUrgency || 0
        };
        this.applyFilters();
    }

    applyFilters() {
        const rows = this.tbody.querySelectorAll('.tx-row');
        let visibleCount = 0;
        let totalCount = rows.length;

        rows.forEach(row => {
            const tx = this.getTransactionFromRow(row);
            if (!tx) {
                row.style.display = 'none';
                return;
            }

            const matches = this.filterTransaction(tx);
            row.style.display = matches ? '' : 'none';
            if (matches) visibleCount++;
        });

        this.updateFilterCount(visibleCount, totalCount);
    }

    filterTransaction(tx) {
        // No filters set = show all
        if (!this.filters) {
            return true;
        }

        // Check min amount
        if (tx.amount_btc < this.filters.minAmount) {
            return false;
        }

        // Check direction
        if (!this.filters.directions.includes(tx.direction)) {
            return false;
        }

        // Check min urgency
        if (tx.urgency_score < this.filters.minUrgency) {
            return false;
        }

        return true;
    }

    getTransactionFromRow(row) {
        // Extract transaction data from row
        // Look up in transactions buffer by TX ID
        const txId = row.dataset.txId;
        if (!txId) return null;

        const transactions = this.transactions.getAll();
        return transactions.find(tx => tx.transaction_id === txId);
    }

    updateFilterCount(visibleCount, totalCount) {
        // Emit event for dashboard to update filter count badge
        const event = new CustomEvent('filter-count-updated', {
            detail: { visible: visibleCount, total: totalCount }
        });
        this.container.dispatchEvent(event);
    }

    clearFilters() {
        this.filters = null;
        this.applyFilters();
    }

    // ========================================
    // Sorting (T074)
    // ========================================

    handleSort(column) {
        // Toggle direction if clicking same column, otherwise default to descending
        if (this.sortColumn === column) {
            this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortColumn = column;
            this.sortDirection = 'desc'; // Default to descending (high to low)
        }

        // Update sort indicators in headers
        this.updateSortIndicators();

        // Re-render all rows in sorted order
        this.rerenderSorted();
    }

    updateSortIndicators() {
        // Remove all sort indicators
        const headers = this.table.querySelectorAll('th.sortable');
        headers.forEach(header => {
            header.classList.remove('sort-asc', 'sort-desc');
            const indicator = header.querySelector('.sort-indicator');
            if (indicator) {
                indicator.textContent = '';
            }
        });

        // Add indicator to active sort column
        if (this.sortColumn) {
            const activeHeader = this.table.querySelector(`th[data-sort="${this.sortColumn}"]`);
            if (activeHeader) {
                activeHeader.classList.add(`sort-${this.sortDirection}`);
                const indicator = activeHeader.querySelector('.sort-indicator');
                if (indicator) {
                    indicator.textContent = this.sortDirection === 'asc' ? '↑' : '↓';
                }
            }
        }
    }

    rerenderSorted() {
        // Get all transactions from buffer
        const transactions = this.transactions.getAll();

        if (transactions.length === 0) {
            return;
        }

        // Sort transactions
        const sorted = this.sortTransactions(transactions);

        // Clear tbody
        this.tbody.innerHTML = '';

        // Re-render all rows in sorted order
        sorted.forEach((tx, index) => {
            const row = this.createTransactionRow(tx);
            this.tbody.appendChild(row);

            // Trigger fade-in animation
            setTimeout(() => {
                row.classList.add('visible');
            }, 10 + (index * 20)); // Stagger animations
        });

        // Apply filters if active
        if (this.filters) {
            this.applyFilters();
        }
    }

    sortTransactions(transactions) {
        if (!this.sortColumn) {
            return transactions; // No sorting
        }

        const sorted = [...transactions].sort((a, b) => {
            let aVal, bVal;

            // Extract values based on sort column
            switch (this.sortColumn) {
                case 'time':
                    aVal = new Date(a.timestamp).getTime();
                    bVal = new Date(b.timestamp).getTime();
                    break;
                case 'amount':
                    aVal = parseFloat(a.amount_btc);
                    bVal = parseFloat(b.amount_btc);
                    break;
                case 'urgency':
                    aVal = a.urgency_score;
                    bVal = b.urgency_score;
                    break;
                case 'fee':
                    aVal = parseFloat(a.fee_rate);
                    bVal = parseFloat(b.fee_rate);
                    break;
                default:
                    return 0;
            }

            // Compare
            if (this.sortDirection === 'asc') {
                return aVal - bVal;
            } else {
                return bVal - aVal;
            }
        });

        return sorted;
    }

    // ========================================
    // Rendering
    // ========================================

    renderTransaction(tx) {
        const row = this.createTransactionRow(tx);

        // Add row to table
        this.tbody.appendChild(row);

        // Trigger fade-in animation
        setTimeout(() => {
            row.classList.add('visible');
        }, 10);

        // Remove oldest row if over limit
        if (this.tbody.children.length > this.config.maxTransactions) {
            const firstRow = this.tbody.firstChild;
            firstRow.classList.add('fade-out');

            setTimeout(() => {
                if (firstRow.parentNode) {
                    firstRow.remove();
                }
            }, this.config.animationDuration);
        }
    }

    createTransactionRow(tx) {
        const row = document.createElement('tr');
        row.className = `tx-row tx-${tx.direction.toLowerCase()}`;
        row.dataset.txId = tx.transaction_id;

        // Format time
        const time = this.formatTime(tx.timestamp);

        // Format amounts
        const btcAmount = this.formatBTC(tx.amount_btc);
        const usdAmount = this.formatUSD(tx.amount_usd);

        // Urgency class
        const urgencyClass = this.getUrgencyClass(tx.urgency_score);

        // Fee rate
        const feeRate = this.formatFeeRate(tx.fee_rate);

        row.innerHTML = `
            <td class="col-time">${time}</td>
            <td class="col-amount">${btcAmount}</td>
            <td class="col-usd">${usdAmount}</td>
            <td class="col-direction">
                <span class="direction-badge direction-${tx.direction.toLowerCase()}">
                    ${this.getDirectionSymbol(tx.direction)} ${tx.direction}
                </span>
            </td>
            <td class="col-urgency">
                <div class="urgency-container" title="${this.getUrgencyBreakdown(tx)}">
                    <div class="urgency-progress-bar urgency-${urgencyClass}">
                        <div class="urgency-progress-fill" style="width: ${tx.urgency_score}%"></div>
                    </div>
                    <span class="urgency-value">${tx.urgency_score}</span>
                </div>
            </td>
            <td class="col-fee">${feeRate}</td>
        `;

        // Add click handler for details modal (future: T056)
        row.addEventListener('click', () => {
            this.onRowClick(tx);
        });

        return row;
    }

    // ========================================
    // Formatting Utilities
    // ========================================

    formatTime(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    formatBTC(btc) {
        return parseFloat(btc).toFixed(2);
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

    formatFeeRate(feeRate) {
        return parseFloat(feeRate).toFixed(1) + ' sat/vB';
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
        const { high, medium } = this.config.urgencyThresholds;

        if (score >= high) return 'high';
        if (score >= medium) return 'medium';
        return 'low';
    }

    getUrgencyBreakdown(tx) {
        // T076: Generate urgency calculation breakdown tooltip
        const score = tx.urgency_score;
        const breakdown = [];

        // Title
        breakdown.push(`URGENCY SCORE: ${score}/100`);
        breakdown.push('');

        // Estimate breakdown components based on score
        // (In production, this would come from backend)
        const amountWeight = Math.min(40, (tx.amount_btc / 500) * 40); // Up to 40 points
        const feeWeight = Math.min(30, (tx.fee_rate / 100) * 30);       // Up to 30 points
        const directionWeight = tx.direction === 'SELL' ? 15 : 10;       // Sells more urgent
        const timeWeight = score - amountWeight - feeWeight - directionWeight; // Remaining

        breakdown.push('Breakdown:');
        breakdown.push(`• Amount Size: ${Math.round(amountWeight)}/40`);
        breakdown.push(`• Fee Rate: ${Math.round(feeWeight)}/30`);
        breakdown.push(`• Direction: ${Math.round(directionWeight)}/15`);
        breakdown.push(`• Time Factor: ${Math.round(timeWeight)}/15`);
        breakdown.push('');

        // Classification
        if (score >= this.config.urgencyThresholds.high) {
            breakdown.push('⚠️ HIGH URGENCY - Immediate attention');
        } else if (score >= this.config.urgencyThresholds.medium) {
            breakdown.push('⚡ MEDIUM URGENCY - Monitor closely');
        } else {
            breakdown.push('✓ LOW URGENCY - Normal activity');
        }

        return breakdown.join('\n');
    }

    // ========================================
    // UI State Management
    // ========================================

    showTable() {
        if (this.emptyState) {
            this.emptyState.classList.add('hidden');
        }

        if (!this.table.parentNode) {
            this.container.appendChild(this.table);
        }

        this.table.classList.remove('hidden');
    }

    hideTable() {
        this.table.classList.add('hidden');

        if (this.emptyState) {
            this.emptyState.classList.remove('hidden');
        }
    }

    scrollToBottom() {
        // Smooth scroll to bottom
        this.container.scrollTo({
            top: this.container.scrollHeight,
            behavior: 'smooth'
        });
    }

    // ========================================
    // Event Handlers
    // ========================================

    onRowClick(tx) {
        // Emit event for modal display (T056)
        const event = new CustomEvent('transaction-selected', {
            detail: tx
        });
        this.container.dispatchEvent(event);
    }

    // ========================================
    // Export Functionality (T059)
    // ========================================

    exportToCSV() {
        const transactions = this.transactions.getAll();

        if (transactions.length === 0) {
            console.warn('No transactions to export');
            return null;
        }

        // CSV header
        const headers = [
            'Timestamp',
            'Transaction ID',
            'Amount BTC',
            'Amount USD',
            'Direction',
            'Urgency Score',
            'Fee Rate (sat/vB)',
            'Block Height',
            'Is Mempool'
        ];

        // CSV rows
        const rows = transactions.map(tx => [
            tx.timestamp,
            tx.transaction_id,
            tx.amount_btc,
            tx.amount_usd,
            tx.direction,
            tx.urgency_score,
            tx.fee_rate,
            tx.block_height || 'N/A',
            tx.is_mempool ? 'Yes' : 'No'
        ]);

        // Combine headers and rows
        const csvContent = [
            headers.join(','),
            ...rows.map(row => row.join(','))
        ].join('\n');

        return csvContent;
    }

    downloadCSV() {
        const csv = this.exportToCSV();

        if (!csv) {
            return;
        }

        // Create blob
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });

        // Create download link
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);

        link.setAttribute('href', url);
        link.setAttribute('download', `whale_transactions_${Date.now()}.csv`);
        link.style.visibility = 'hidden';

        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        URL.revokeObjectURL(url);
    }
}

// ============================================
// Export
// ============================================

export { TransactionFeed, RingBuffer, FEED_CONFIG };
