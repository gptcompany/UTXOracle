/**
 * Shared Utilities for Metrics Dashboard
 * Common fetch, transform, and render functions
 */

const MetricsCommon = {
  // API base URL
  baseUrl: '/api/metrics',

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
          <p>Error: ${message}</p>
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
          <p>${message}</p>
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
  }
};

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = MetricsCommon;
}
