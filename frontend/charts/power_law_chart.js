/**
 * Bitcoin Price Power Law Chart (spec-034)
 *
 * Interactive log-log chart showing:
 * - Historical BTC prices (scatter)
 * - Power law regression line (fair value)
 * - +/- 1 sigma bands (support/resistance)
 * - Current zone indication
 */

const PowerLawChart = {
  // Chart configuration
  config: {
    containerId: "power-law-chart",
    apiBase: "/api/v1/models/power-law",
    refreshInterval: 60000, // 1 minute
    defaultDays: 365,
  },

  // Color scheme
  colors: {
    price: "#2196F3", // Blue for actual prices
    fairValue: "#4CAF50", // Green for fair value line
    upperBand: "rgba(255, 152, 0, 0.3)", // Orange for upper band
    lowerBand: "rgba(76, 175, 80, 0.3)", // Green for lower band
    undervalued: "#4CAF50",
    fair: "#FF9800",
    overvalued: "#F44336",
    gridColor: "#333333",
    textColor: "#E0E0E0",
  },

  // Store model data
  model: null,
  history: [],

  /**
   * Initialize the chart
   */
  async init(containerId = null) {
    if (containerId) {
      this.config.containerId = containerId;
    }

    await this.fetchData();
    this.render();
  },

  /**
   * Fetch data from API
   */
  async fetchData(days = null) {
    const daysParam = days || this.config.defaultDays;

    try {
      const response = await fetch(
        `${this.config.apiBase}/history?days=${daysParam}`
      );
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      const data = await response.json();

      this.model = data.model;
      this.history = data.history;

      return data;
    } catch (error) {
      console.error("Failed to fetch power law data:", error);
      throw error;
    }
  },

  /**
   * Render the chart
   */
  render() {
    if (!this.history || this.history.length === 0) {
      console.warn("No data to render");
      return;
    }

    // Prepare data arrays
    const dates = this.history.map((p) => p.date);
    const prices = this.history.map((p) => p.price);
    const fairValues = this.history.map((p) => p.fair_value);

    // Calculate bands using model std_error
    const stdError = this.model.std_error;
    const lowerBands = fairValues.map((fv) => fv / Math.pow(10, stdError));
    const upperBands = fairValues.map((fv) => fv * Math.pow(10, stdError));

    // Zone colors for each point
    const zoneColors = this.history.map((p) => this.colors[p.zone]);

    // Create traces
    const traces = [
      // Upper band fill (to max)
      {
        x: dates,
        y: upperBands,
        fill: "none",
        mode: "lines",
        line: { color: "rgba(255, 152, 0, 0.5)", width: 1 },
        name: "+1σ (Resistance)",
        hoverinfo: "skip",
      },
      // Fair value line
      {
        x: dates,
        y: fairValues,
        mode: "lines",
        line: { color: this.colors.fairValue, width: 2 },
        name: "Fair Value",
        hovertemplate: "<b>Fair Value</b><br>%{x}<br>$%{y:,.0f}<extra></extra>",
      },
      // Lower band
      {
        x: dates,
        y: lowerBands,
        fill: "tonexty",
        mode: "lines",
        line: { color: "rgba(76, 175, 80, 0.5)", width: 1 },
        fillcolor: "rgba(100, 100, 100, 0.2)",
        name: "-1σ (Support)",
        hoverinfo: "skip",
      },
      // Actual prices (scatter)
      {
        x: dates,
        y: prices,
        mode: "markers",
        marker: {
          color: zoneColors,
          size: 4,
          opacity: 0.8,
        },
        name: "BTC Price",
        hovertemplate:
          "<b>BTC Price</b><br>%{x}<br>$%{y:,.0f}<br>Zone: %{text}<extra></extra>",
        text: this.history.map((p) => p.zone),
      },
    ];

    // Layout configuration
    const layout = {
      title: {
        text: "Bitcoin Price Power Law Model",
        font: { color: this.colors.textColor, size: 20 },
      },
      xaxis: {
        title: "Date",
        type: "date",
        gridcolor: this.colors.gridColor,
        tickfont: { color: this.colors.textColor },
        titlefont: { color: this.colors.textColor },
      },
      yaxis: {
        title: "Price (USD)",
        type: "log",
        gridcolor: this.colors.gridColor,
        tickfont: { color: this.colors.textColor },
        titlefont: { color: this.colors.textColor },
        tickformat: "$,.0f",
      },
      paper_bgcolor: "#1a1a1a",
      plot_bgcolor: "#1a1a1a",
      legend: {
        x: 0.02,
        y: 0.98,
        bgcolor: "rgba(0,0,0,0.5)",
        font: { color: this.colors.textColor },
      },
      hovermode: "closest",
      margin: { t: 60, r: 40, b: 60, l: 80 },
    };

    // Plotly config
    const plotConfig = {
      responsive: true,
      displayModeBar: true,
      modeBarButtonsToRemove: ["lasso2d", "select2d"],
    };

    Plotly.newPlot(this.config.containerId, traces, layout, plotConfig);
  },

  /**
   * Update chart with new data
   */
  async update(days = null) {
    await this.fetchData(days);
    this.render();
  },

  /**
   * Get current model info
   */
  getModelInfo() {
    if (!this.model) return null;

    return {
      alpha: this.model.alpha.toFixed(2),
      beta: this.model.beta.toFixed(2),
      rSquared: (this.model.r_squared * 100).toFixed(1) + "%",
      stdError: this.model.std_error.toFixed(3),
      fittedOn: this.model.fitted_on,
      sampleSize: this.model.sample_size.toLocaleString(),
    };
  },

  /**
   * Get zone legend HTML
   */
  getZoneLegendHTML() {
    return `
      <div class="zone-legend">
        <div class="zone-item">
          <span class="zone-color" style="background: ${this.colors.undervalued}"></span>
          <span>Undervalued (&lt;-20%)</span>
        </div>
        <div class="zone-item">
          <span class="zone-color" style="background: ${this.colors.fair}"></span>
          <span>Fair Value (-20% to +50%)</span>
        </div>
        <div class="zone-item">
          <span class="zone-color" style="background: ${this.colors.overvalued}"></span>
          <span>Overvalued (&gt;+50%)</span>
        </div>
      </div>
    `;
  },
};

// Export for module usage
if (typeof module !== "undefined" && module.exports) {
  module.exports = PowerLawChart;
}
