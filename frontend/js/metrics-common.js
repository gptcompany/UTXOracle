/**
 * Shared Utilities for Metrics Dashboard
 * Common fetch, transform, and render functions
 */

const MetricsCommon = {
  // API base URL
  baseUrl: '/api/metrics',

  // HTML escape helper to prevent XSS
  _escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  },

  // Theme state (with localStorage fallback for privacy modes)
  _theme: (() => {
    try {
      return localStorage.getItem('metricsTheme') || 'dark';
    } catch (e) {
      return 'dark';
    }
  })(),

  // Last refresh timestamp
  _lastRefresh: null,

  // Auto-refresh interval (5 minutes by default)
  _refreshInterval: 5 * 60 * 1000,
  _refreshTimer: null,

  // Fetch data from API endpoint
  async fetchData(endpoint, params = {}) {
    const url = new URL(endpoint, window.location.origin);
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.append(key, value);
      }
    });

    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return await response.json();
    } catch (error) {
      console.error(`Error fetching ${endpoint}:`, error);
      throw error;
    }
  },

  // Fetch historical data with days parameter
  async fetchHistory(endpoint, days = 365) {
    return this.fetchData(endpoint, { days });
  },

  // Transform API response to Plotly trace format
  toTrace(data, config) {
    const validData = Array.isArray(data) ? data : [data];
    const filtered = validData.filter(d =>
      d && d[config.xKey || 'date'] != null && d[config.yKey] != null
    );

    return {
      x: filtered.map(d => d[config.xKey || 'date']),
      y: filtered.map(d => d[config.yKey]),
      type: config.type || 'scatter',
      mode: config.mode || 'lines',
      name: config.name || config.yKey,
      fill: config.fill || 'none',
      fillcolor: config.fillcolor,
      line: {
        color: config.color || ChartThemes.lines.primary,
        width: config.width || 2,
        dash: config.dash
      },
      yaxis: config.yaxis,
      hovertemplate: config.hovertemplate || `%{y:.4f}<extra>${config.name || config.yKey}</extra>`
    };
  },

  // Create BTC price overlay trace (secondary y-axis)
  toPriceTrace(data, config = {}) {
    return this.toTrace(data, {
      yKey: config.yKey || 'market_price',
      name: config.name || 'BTC Price',
      color: ChartThemes.lines.btcPrice,
      yaxis: 'y2',
      hovertemplate: '$%{y:,.0f}<extra>BTC Price</extra>',
      ...config
    });
  },

  // Render chart to container
  render(containerId, traces, layout, config = ChartThemes.config) {
    const container = document.getElementById(containerId);
    if (!container) {
      console.error(`Container #${containerId} not found`);
      return;
    }

    Plotly.newPlot(containerId, traces, layout, config);
  },

  // Show loading state
  showLoading(containerId) {
    const container = document.getElementById(containerId);
    if (container) {
      container.innerHTML = `
        <div class="loading-state">
          <div class="loading-spinner"></div>
          <p>Loading data...</p>
        </div>
      `;
    }
  },

  // Show error state
  showError(containerId, message) {
    const container = document.getElementById(containerId);
    if (container) {
      container.innerHTML = `
        <div class="error-state">
          <p>Error: ${this._escapeHtml(message)}</p>
          <button onclick="location.reload()">Retry</button>
        </div>
      `;
    }
  },

  // Show no data state
  showNoData(containerId, message = 'No data available') {
    const container = document.getElementById(containerId);
    if (container) {
      container.innerHTML = `
        <div class="no-data-state">
          <p>${this._escapeHtml(message)}</p>
        </div>
      `;
    }
  },

  // Format date for display
  formatDate(dateStr) {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  },

  // Format number with suffix (K, M, B)
  formatNumber(num) {
    if (num == null || isNaN(num)) return '0';
    if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(2) + 'K';
    return num.toFixed(2);
  },

  // Get layout with secondary y-axis for price
  getLayoutWithPriceAxis(title, yAxisTitle, options = {}) {
    const layout = ChartThemes.getLayout(title, yAxisTitle, options);
    layout.yaxis2 = {
      ...ChartThemes.dark.layout.yaxis,
      title: 'BTC Price (USD)',
      overlaying: 'y',
      side: 'right',
      type: options.priceLogScale ? 'log' : 'linear',
      showgrid: false
    };
    return layout;
  },

  // Calculate min/max from data array
  getDataRange(data, key) {
    const values = data.map(d => d[key]).filter(v => v != null && !isNaN(v));
    return {
      min: Math.min(...values),
      max: Math.max(...values)
    };
  },

  // Add zone coloring to layout
  addZoneColoring(layout, metric, yMin, yMax) {
    layout.shapes = layout.shapes || [];
    layout.shapes.push(...ChartThemes.createZoneShapes(metric, yMin, yMax));
    return layout;
  },

  // Add reference line to layout
  addReferenceLine(layout, y, color, label) {
    layout.shapes = layout.shapes || [];
    layout.shapes.push(ChartThemes.createReferenceLine(y, color, label));
    return layout;
  },

  // Create metric info box HTML
  createInfoBox(title, value, subtitle = '') {
    return `
      <div class="metric-info-box">
        <div class="metric-title">${title}</div>
        <div class="metric-value">${value}</div>
        ${subtitle ? `<div class="metric-subtitle">${subtitle}</div>` : ''}
      </div>
    `;
  },

  // Update metric info boxes
  updateInfoBoxes(containerId, metrics) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = metrics.map(m =>
      this.createInfoBox(m.title, m.value, m.subtitle)
    ).join('');
  },

  // Initialize page with common setup
  async initPage(options) {
    const { chartId, endpoint, buildChart, days = 365 } = options;

    this.showLoading(chartId);

    try {
      const data = await this.fetchData(endpoint, days ? { days } : {});

      if (!data || (Array.isArray(data) && data.length === 0)) {
        this.showNoData(chartId);
        return null;
      }

      buildChart(data);
      return data;
    } catch (error) {
      this.showError(chartId, error.message);
      return null;
    }
  },

  // ============================================
  // Theme Management (T043)
  // ============================================

  // Initialize theme from storage
  initTheme() {
    if (this._theme === 'light') {
      document.body.classList.add('light-theme');
    }
    // Update Plotly charts if they exist
    this.updateChartTheme();
  },

  // Toggle between dark and light theme
  toggleTheme() {
    this._theme = this._theme === 'dark' ? 'light' : 'dark';
    try {
      localStorage.setItem('metricsTheme', this._theme);
    } catch (e) {
      // localStorage may be unavailable in privacy modes
    }

    if (this._theme === 'light') {
      document.body.classList.add('light-theme');
    } else {
      document.body.classList.remove('light-theme');
    }

    this.updateChartTheme();
    return this._theme;
  },

  // Get current theme
  getTheme() {
    return this._theme;
  },

  // Update Plotly chart colors based on theme
  updateChartTheme() {
    const chartDiv = document.getElementById('chart');
    if (chartDiv && chartDiv.data) {
      const layoutUpdate = this._theme === 'light' ? {
        paper_bgcolor: '#ffffff',
        plot_bgcolor: '#ffffff',
        font: { color: '#1a1a2e' },
        'xaxis.gridcolor': '#e0e0e0',
        'yaxis.gridcolor': '#e0e0e0'
      } : {
        paper_bgcolor: '#1a1a2e',
        plot_bgcolor: '#1a1a2e',
        font: { color: '#e0e0e0' },
        'xaxis.gridcolor': '#2d2d44',
        'yaxis.gridcolor': '#2d2d44'
      };
      Plotly.relayout('chart', layoutUpdate);
    }
  },

  // Create theme toggle button HTML
  createThemeToggle() {
    const icon = this._theme === 'dark' ? '☀️' : '🌙';
    return `<button class="theme-toggle" onclick="MetricsCommon.toggleTheme(); this.textContent = MetricsCommon.getTheme() === 'dark' ? '☀️' : '🌙';" title="Toggle theme">${icon}</button>`;
  },

  // ============================================
  // Date Range Selector (T044)
  // ============================================

  // Create date range selector HTML
  createDateRangeSelector(currentDays = 365) {
    const options = [
      { value: 7, label: '7D' },
      { value: 30, label: '30D' },
      { value: 90, label: '90D' },
      { value: 365, label: '1Y' },
      { value: 730, label: '2Y' },
      { value: 0, label: 'All' }
    ];

    const optionsHtml = options.map(opt =>
      `<option value="${opt.value}" ${opt.value === currentDays ? 'selected' : ''}>${opt.label}</option>`
    ).join('');

    return `
      <div class="control-group">
        <label for="date-range">Range</label>
        <select id="date-range" onchange="MetricsCommon.onDateRangeChange(this.value)">
          ${optionsHtml}
        </select>
      </div>
    `;
  },

  // Date range change handler (to be overridden by pages)
  _dateRangeCallback: null,

  setDateRangeCallback(callback) {
    this._dateRangeCallback = callback;
  },

  onDateRangeChange(days) {
    if (this._dateRangeCallback) {
      this._dateRangeCallback(parseInt(days));
    }
  },

  // ============================================
  // Export Functionality (T045)
  // ============================================

  // Create export buttons HTML
  createExportButtons() {
    return `
      <div class="export-buttons">
        <button onclick="MetricsCommon.exportToPNG()" title="Export chart as PNG">PNG</button>
        <button onclick="MetricsCommon.exportToCSV()" title="Export data as CSV">CSV</button>
      </div>
    `;
  },

  // Export chart to PNG
  exportToPNG() {
    const chartDiv = document.getElementById('chart');
    if (chartDiv && chartDiv.data) {
      Plotly.downloadImage('chart', {
        format: 'png',
        width: 1200,
        height: 800,
        filename: `utxoracle_${document.title.split('|')[0].trim().toLowerCase().replace(/\s+/g, '_')}_${new Date().toISOString().split('T')[0]}`
      });
    }
  },

  // Store current data for CSV export
  _currentData: null,

  setExportData(data) {
    this._currentData = data;
  },

  // Export data to CSV
  exportToCSV() {
    if (!this._currentData) {
      console.warn('No data available for export');
      return;
    }

    const data = Array.isArray(this._currentData) ? this._currentData : [this._currentData];
    if (data.length === 0) return;

    // Ensure first item is an object
    if (typeof data[0] !== 'object' || data[0] === null) {
      console.warn('Export data must be an array of objects');
      return;
    }

    // Get all keys from the first object
    const headers = Object.keys(data[0]);
    const csvRows = [headers.join(',')];

    // Add data rows
    for (const row of data) {
      const values = headers.map(header => {
        const value = row[header];
        // Escape commas, quotes, and newlines per RFC 4180
        if (typeof value === 'string' && (value.includes(',') || value.includes('"') || value.includes('\n') || value.includes('\r'))) {
          return `"${value.replace(/"/g, '""')}"`;
        }
        return value ?? '';
      });
      csvRows.push(values.join(','));
    }

    // Create and download CSV
    const csvContent = csvRows.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `utxoracle_${document.title.split('|')[0].trim().toLowerCase().replace(/\s+/g, '_')}_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);  // Clean up to prevent memory leak
  },

  // ============================================
  // Refresh Indicator (T046)
  // ============================================

  // Create refresh indicator HTML
  createRefreshIndicator() {
    return `
      <div class="refresh-indicator" id="refresh-indicator">
        <div class="refresh-spinner"></div>
        <span class="last-refresh" id="last-refresh-time">--</span>
        <button onclick="MetricsCommon.manualRefresh()" title="Refresh now" style="padding: 4px 8px; font-size: 0.7rem;">↻</button>
      </div>
    `;
  },

  // Update refresh indicator
  updateRefreshIndicator(isLoading = false) {
    const indicator = document.getElementById('refresh-indicator');
    const timeEl = document.getElementById('last-refresh-time');

    if (indicator) {
      if (isLoading) {
        indicator.classList.add('loading');
      } else {
        indicator.classList.remove('loading');
        this._lastRefresh = new Date();
      }
    }

    if (timeEl && this._lastRefresh) {
      timeEl.textContent = this._lastRefresh.toLocaleTimeString();
    }
  },

  // Manual refresh handler (to be overridden)
  _refreshCallback: null,

  setRefreshCallback(callback) {
    this._refreshCallback = callback;
  },

  async manualRefresh() {
    if (this._refreshCallback) {
      this.updateRefreshIndicator(true);
      try {
        await this._refreshCallback();
      } catch (error) {
        console.error('Refresh failed:', error);
      } finally {
        this.updateRefreshIndicator(false);
      }
    } else {
      // Default: reload page
      location.reload();
    }
  },

  // Start auto-refresh timer
  startAutoRefresh(intervalMs = null) {
    if (intervalMs) {
      this._refreshInterval = intervalMs;
    }

    // Clear existing timer
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
    }

    // Start new timer
    this._refreshTimer = setInterval(() => {
      this.manualRefresh();
    }, this._refreshInterval);
  },

  // Stop auto-refresh
  stopAutoRefresh() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = null;
    }
  },

  // ============================================
  // Controls Toolbar (combines all controls)
  // ============================================

  // Create complete controls toolbar HTML
  createControlsToolbar(options = {}) {
    const { showDateRange = true, showExport = true, showTheme = true, showRefresh = true, currentDays = 365 } = options;

    let html = '<div class="controls-toolbar">';

    if (showDateRange) {
      html += this.createDateRangeSelector(currentDays);
    }

    if (showTheme) {
      html += this.createThemeToggle();
    }

    if (showExport) {
      html += this.createExportButtons();
    }

    if (showRefresh) {
      html += this.createRefreshIndicator();
    }

    html += '</div>';
    return html;
  },

  // Insert controls toolbar into page
  insertControlsToolbar(containerId, options = {}) {
    const container = document.getElementById(containerId);
    if (container) {
      container.innerHTML = this.createControlsToolbar(options);
      this.initTheme();
      this.updateRefreshIndicator(false);
    }
  }
};

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = MetricsCommon;
}
