/**
 * UTXOracle Whale Charts Component
 * Plotly.js-based interactive historical net flow chart
 *
 * Tasks Implemented:
 * - T063: Line chart implementation with Plotly.js
 * - T065: Fetch and display 24-hour data by default
 * - T066: Enable zoom and pan interactions
 * - T067: Timeframe selector integration
 *
 * Features:
 * - Interactive line chart with zoom/pan (Plotly built-in)
 * - Multiple timeframes (1h, 6h, 24h, 7d)
 * - Loading and error states
 * - Responsive sizing
 * - Dark theme integration
 */

// ============================================
// Configuration
// ============================================

const CHART_CONFIG = {
    defaultTimeframe: '24h',
    updateInterval: 60000, // 60 seconds
    maxDataPoints: 10000,
    colors: {
        line: '#00ff00', // Green (buy/accumulation)
        positive: '#00ff00',
        negative: '#ff0000',
        neutral: '#ffff00',
        background: '#0a0a0a',
        gridline: '#333'
    }
};

// ============================================
// Whale Chart Component
// ============================================

class WhaleChart {
    constructor(containerId, config = CHART_CONFIG) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Chart container not found: ${containerId}`);
        }

        this.config = config;
        this.chartData = null;
        this.currentTimeframe = config.defaultTimeframe;

        // State
        this.isLoaded = false;
        this.updateTimer = null;

        // Initialize UI references
        this.loadingEl = document.getElementById('chart-loading');
        this.errorEl = document.getElementById('chart-error');
        this.retryBtn = document.getElementById('chart-retry');

        // Setup retry handler
        if (this.retryBtn) {
            this.retryBtn.addEventListener('click', () => {
                this.loadChart(this.currentTimeframe);
            });
        }
    }

    // ========================================
    // Public API
    // ========================================

    async init(timeframe = null) {
        const tf = timeframe || this.currentTimeframe;
        await this.loadChart(tf);
    }

    async loadChart(timeframe) {
        this.currentTimeframe = timeframe;

        // Show loading state
        this.showLoading();

        try {
            // Fetch historical data
            const data = await this.fetchHistoricalData(timeframe);

            if (!data || data.length === 0) {
                throw new Error('No data available for selected timeframe');
            }

            // Store data
            this.chartData = data;

            // Render chart
            this.renderChart(data);

            // Hide loading, show chart
            this.hideLoading();
            this.isLoaded = true;

        } catch (error) {
            console.error('Failed to load chart:', error);
            this.showError(error.message);
        }
    }

    async updateChart() {
        if (!this.isLoaded) return;

        try {
            const data = await this.fetchHistoricalData(this.currentTimeframe);
            if (data && data.length > 0) {
                this.chartData = data;
                this.renderChart(data);
            }
        } catch (error) {
            console.error('Failed to update chart:', error);
        }
    }

    startAutoUpdate() {
        if (this.updateTimer) {
            clearInterval(this.updateTimer);
        }

        this.updateTimer = setInterval(() => {
            this.updateChart();
        }, this.config.updateInterval);
    }

    stopAutoUpdate() {
        if (this.updateTimer) {
            clearInterval(this.updateTimer);
            this.updateTimer = null;
        }
    }

    destroy() {
        this.stopAutoUpdate();
        if (typeof Plotly !== 'undefined') {
            Plotly.purge(this.container);
        }
    }

    // ========================================
    // Data Fetching
    // ========================================

    async fetchHistoricalData(timeframe) {
        // Calculate time range based on timeframe
        const endTime = Date.now();
        const startTime = this.getStartTime(timeframe, endTime);

        // Build API URL
        const url = `/api/whale/historical?start=${startTime}&end=${endTime}&timeframe=${timeframe}`;

        const response = await fetch(url);

        if (!response.ok) {
            throw new Error(`API error: ${response.status} ${response.statusText}`);
        }

        const result = await response.json();

        // API returns: { success: true, data: [...], count: N }
        if (!result.success) {
            throw new Error(result.error || 'Failed to fetch data');
        }

        return result.data;
    }

    getStartTime(timeframe, endTime) {
        const durations = {
            '1h': 60 * 60 * 1000,
            '6h': 6 * 60 * 60 * 1000,
            '24h': 24 * 60 * 60 * 1000,
            '7d': 7 * 24 * 60 * 60 * 1000
        };

        const duration = durations[timeframe] || durations['24h'];
        return endTime - duration;
    }

    // ========================================
    // Chart Rendering
    // ========================================

    renderChart(data) {
        // Transform data for Plotly
        const timestamps = data.map(d => d.timestamp);
        const netFlowBTC = data.map(d => parseFloat(d.net_flow_btc));

        // Determine colors based on net flow values
        const lineColors = netFlowBTC.map(val => {
            if (val > 0) return this.config.colors.positive;
            if (val < 0) return this.config.colors.negative;
            return this.config.colors.neutral;
        });

        // Create trace
        const trace = {
            x: timestamps,
            y: netFlowBTC,
            type: 'scatter',
            mode: 'lines+markers',
            name: 'Net Flow (BTC)',
            line: {
                color: this.config.colors.line,
                width: 2,
                shape: 'spline' // Smooth line
            },
            marker: {
                size: 4,
                color: lineColors,
                line: {
                    color: '#fff',
                    width: 0.5
                }
            },
            hovertemplate: '<b>%{x}</b><br>' +
                          'Net Flow: %{y:.2f} BTC<br>' +
                          '<extra></extra>'
        };

        // Layout configuration (dark theme)
        const layout = {
            title: {
                text: `Whale Net Flow - ${this.currentTimeframe.toUpperCase()}`,
                font: {
                    family: 'Monaco, monospace',
                    size: 16,
                    color: this.config.colors.line
                }
            },
            xaxis: {
                title: 'Time',
                titlefont: { color: this.config.colors.line },
                tickfont: { color: this.config.colors.line },
                gridcolor: this.config.colors.gridline,
                showgrid: true,
                zeroline: false
            },
            yaxis: {
                title: 'Net Flow (BTC)',
                titlefont: { color: this.config.colors.line },
                tickfont: { color: this.config.colors.line },
                gridcolor: this.config.colors.gridline,
                showgrid: true,
                zeroline: true,
                zerolinecolor: this.config.colors.neutral,
                zerolinewidth: 1
            },
            plot_bgcolor: this.config.colors.background,
            paper_bgcolor: this.config.colors.background,
            hovermode: 'closest',
            margin: {
                l: 60,
                r: 30,
                t: 50,
                b: 50
            },
            autosize: true,
            responsive: true
        };

        // Plotly config (enables zoom, pan, etc.)
        const config = {
            responsive: true,
            displayModeBar: true,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            displaylogo: false,
            toImageButtonOptions: {
                format: 'png',
                filename: `whale_netflow_${this.currentTimeframe}`,
                height: 600,
                width: 1200,
                scale: 2
            }
        };

        // Render chart with Plotly
        Plotly.newPlot(this.container, [trace], layout, config);
    }

    // ========================================
    // UI State Management
    // ========================================

    showLoading() {
        if (this.loadingEl) {
            this.loadingEl.classList.remove('hidden');
        }
        if (this.errorEl) {
            this.errorEl.classList.add('hidden');
        }
        this.container.classList.add('hidden');
    }

    hideLoading() {
        if (this.loadingEl) {
            this.loadingEl.classList.add('hidden');
        }
        this.container.classList.remove('hidden');
    }

    showError(message) {
        if (this.loadingEl) {
            this.loadingEl.classList.add('hidden');
        }
        if (this.errorEl) {
            this.errorEl.classList.remove('hidden');
            const msgEl = this.errorEl.querySelector('.error-message');
            if (msgEl) {
                msgEl.textContent = `⚠️ ${message}`;
            }
        }
        this.container.classList.add('hidden');
    }

    // ========================================
    // Data Export (T059 extension)
    // ========================================

    exportToCSV() {
        if (!this.chartData || this.chartData.length === 0) {
            console.warn('No chart data to export');
            return null;
        }

        // CSV header
        const headers = ['Timestamp', 'Net Flow BTC', 'Timeframe'];

        // CSV rows
        const rows = this.chartData.map(d => [
            d.timestamp,
            d.net_flow_btc,
            this.currentTimeframe
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
        link.setAttribute('download', `whale_netflow_${this.currentTimeframe}_${Date.now()}.csv`);
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

export { WhaleChart, CHART_CONFIG };
