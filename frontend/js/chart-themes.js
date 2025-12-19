/**
 * Chart Theme Configuration for Metrics Dashboard
 * Matches CheckOnChain visual style for validation purposes
 */

const ChartThemes = {
  // Dark theme matching CheckOnChain
  dark: {
    layout: {
      paper_bgcolor: '#1a1a2e',
      plot_bgcolor: '#1a1a2e',
      font: { color: '#e0e0e0', family: 'Inter, sans-serif' },
      xaxis: {
        gridcolor: '#2d2d44',
        linecolor: '#2d2d44',
        tickcolor: '#e0e0e0',
        zerolinecolor: '#3d3d5c'
      },
      yaxis: {
        gridcolor: '#2d2d44',
        linecolor: '#2d2d44',
        tickcolor: '#e0e0e0',
        zerolinecolor: '#3d3d5c'
      },
      legend: {
        bgcolor: 'rgba(26, 26, 46, 0.8)',
        bordercolor: '#2d2d44',
        font: { color: '#e0e0e0' }
      }
    }
  },

  // Zone colors for different metrics
  zones: {
    mvrv: {
      extreme_low: { color: '#00ff88', label: 'Extreme Low (<0)' },
      neutral: { color: '#888888', label: 'Neutral (0-3)' },
      elevated: { color: '#ffcc00', label: 'Elevated (3-7)' },
      extreme_high: { color: '#ff4444', label: 'Extreme High (>7)' }
    },
    nupl: {
      capitulation: { color: '#ff4444', label: 'Capitulation (<0)' },
      hope: { color: '#ff8844', label: 'Hope (0-0.25)' },
      optimism: { color: '#ffcc00', label: 'Optimism (0.25-0.5)' },
      belief: { color: '#88cc00', label: 'Belief (0.5-0.75)' },
      euphoria: { color: '#00ff88', label: 'Euphoria (>0.75)' }
    },
    sopr: {
      loss: { color: '#ff4444', label: 'Loss (<1)' },
      profit: { color: '#00ff88', label: 'Profit (>1)' }
    }
  },

  // Standard line colors
  lines: {
    primary: '#00d4ff',
    secondary: '#ff6b6b',
    tertiary: '#ffd93d',
    btcPrice: '#f7931a',
    realizedPrice: '#00ff88',
    sthCost: '#ff8844',
    lthCost: '#8844ff',
    ma30: '#00d4ff',
    ma60: '#ff6b6b'
  },

  // Standard Plotly config
  config: {
    responsive: true,
    displayModeBar: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'],
    displaylogo: false
  },

  // Get base layout with dark theme
  getLayout(title, yAxisTitle, options = {}) {
    return {
      title: {
        text: title,
        font: { size: 18, color: '#e0e0e0' },
        x: 0.5
      },
      ...this.dark.layout,
      xaxis: {
        ...this.dark.layout.xaxis,
        title: 'Date',
        type: 'date',
        rangeslider: { visible: false },
        ...options.xaxis
      },
      yaxis: {
        ...this.dark.layout.yaxis,
        title: yAxisTitle,
        ...options.yaxis
      },
      margin: { l: 60, r: 60, t: 60, b: 50 },
      showlegend: options.showlegend !== false,
      legend: {
        ...this.dark.layout.legend,
        x: 0,
        y: 1.1,
        orientation: 'h'
      },
      ...options
    };
  },

  // Create zone shapes for horizontal bands
  createZoneShapes(metric, yMin, yMax) {
    const zones = this.zones[metric];
    if (!zones) return [];

    const shapes = [];
    const boundaries = {
      mvrv: [
        { y0: yMin, y1: 0, zone: 'extreme_low' },
        { y0: 0, y1: 3, zone: 'neutral' },
        { y0: 3, y1: 7, zone: 'elevated' },
        { y0: 7, y1: yMax, zone: 'extreme_high' }
      ],
      nupl: [
        { y0: yMin, y1: 0, zone: 'capitulation' },
        { y0: 0, y1: 0.25, zone: 'hope' },
        { y0: 0.25, y1: 0.5, zone: 'optimism' },
        { y0: 0.5, y1: 0.75, zone: 'belief' },
        { y0: 0.75, y1: yMax, zone: 'euphoria' }
      ],
      sopr: [
        { y0: yMin, y1: 1, zone: 'loss' },
        { y0: 1, y1: yMax, zone: 'profit' }
      ]
    };

    const metricBoundaries = boundaries[metric] || [];
    for (const b of metricBoundaries) {
      shapes.push({
        type: 'rect',
        xref: 'paper',
        yref: 'y',
        x0: 0,
        x1: 1,
        y0: Math.max(b.y0, yMin),
        y1: Math.min(b.y1, yMax),
        fillcolor: zones[b.zone].color,
        opacity: 0.15,
        line: { width: 0 }
      });
    }

    return shapes;
  },

  // Create a reference line (e.g., SOPR = 1)
  createReferenceLine(y, color = '#ffffff', label = '') {
    return {
      type: 'line',
      xref: 'paper',
      yref: 'y',
      x0: 0,
      x1: 1,
      y0: y,
      y1: y,
      line: {
        color: color,
        width: 1,
        dash: 'dash'
      }
    };
  }
};

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ChartThemes;
}
