"""
Frontend Integration Tests

Tests for Canvas rendering and browser-side visualization.

Note: Some tests require a browser environment (Playwright/Selenium) and are marked
with @pytest.mark.browser. These can be run separately using:
    pytest tests/integration/test_frontend.py -m browser

For full frontend validation, use browser MCP tools (ccbrowser, ccfullbrowser).
"""

from pathlib import Path


# =============================================================================
# T085: Stats Panel Rendering Test (User Story 4)
# =============================================================================


def test_stats_panel_rendering():
    """
    Test that HTML contains stats panel and JavaScript updates it.

    Requirements (User Story 4):
    - HTML contains stats display area
    - JavaScript receives stats from WebSocket message
    - Stats displayed: "Received: X | Filtered: Y | Active: Z | Uptime: Xh Ym"
    - Uptime formatted as hours/minutes (not raw seconds)
    - Connection status indicator present

    This is a STRUCTURAL test (checks files and elements exist).
    Visual rendering requires browser environment - see manual testing notes.

    Task: T085 [US4]
    """
    # Assert: HTML file exists
    html_path = Path("live/frontend/index.html")
    assert html_path.exists(), f"Frontend HTML not found: {html_path}"

    # Assert: JavaScript module exists
    js_path = Path("live/frontend/mempool-viz.js")
    assert js_path.exists(), f"Visualization JS not found: {js_path}"

    # Assert: HTML contains stats display area
    html_content = html_path.read_text()

    # Check for stats panel in HTML (any of these patterns)
    has_stats_section = any(
        [
            'id="stats"' in html_content,
            "id='stats'" in html_content,
            'class="stats"' in html_content,
            "class='stats'" in html_content,
            '<div class="stats-panel">' in html_content,
            '<section class="stats">' in html_content,
        ]
    )
    assert has_stats_section, (
        "HTML should contain stats display area (id='stats' or class='stats')"
    )

    # Assert: JavaScript handles stats updates
    js_content = js_path.read_text()

    # Check for stats-related code (any of these patterns)
    has_stats_handling = any(
        [
            "total_received" in js_content,
            "totalReceived" in js_content,
            "active_tx_count" in js_content,
            "activeTxCount" in js_content,
            "uptime" in js_content.lower(),
        ]
    )
    assert has_stats_handling, "JavaScript should handle stats from WebSocket message"

    # Assert: Uptime formatting exists (hours/minutes, not raw seconds)
    has_uptime_format = any(
        [
            "hours" in js_content.lower() or "minutes" in js_content.lower(),
            "formatUptime" in js_content,
            "format_uptime" in js_content,
            "/ 3600" in js_content,  # seconds to hours conversion
            "/ 60" in js_content,  # seconds/minutes to minutes conversion
        ]
    )
    assert has_uptime_format, "JavaScript should format uptime as hours/minutes"

    # Assert: Connection status indicator exists (from US1, should still be present)
    has_connection_status = any(
        [
            "connection" in js_content.lower() and "status" in js_content.lower(),
            "connected" in js_content.lower(),
            "disconnected" in js_content.lower(),
        ]
    )
    assert has_connection_status, "JavaScript should have connection status handling"


# =============================================================================
# T066: Canvas Rendering Test (User Story 2)
# =============================================================================


def test_scatter_plot_renders_transactions():
    """
    Test that Canvas scatter plot can render transaction history.

    Requirements (User Story 2):
    - HTML contains canvas element with correct ID
    - JavaScript module exists with scatter plot renderer
    - Canvas has correct dimensions (1000x660px per spec)
    - Renderer can process WebSocket message format
    - Points are rendered as orange circles
    - X-axis: time (horizontal), Y-axis: price (vertical)

    This is a STRUCTURAL test (checks files and structure exist).
    Visual rendering requires browser environment - see manual testing notes.

    Task: T066 [US2]
    """
    # Assert: HTML file exists
    html_path = Path("live/frontend/index.html")
    assert html_path.exists(), f"Frontend HTML not found: {html_path}"

    # Assert: JavaScript visualization module exists
    js_path = Path("live/frontend/mempool-viz.js")
    assert js_path.exists(), f"Visualization JS not found: {js_path}"

    # Assert: HTML contains canvas element
    html_content = html_path.read_text()
    assert "<canvas" in html_content, "HTML should contain canvas element"
    assert (
        'id="mempool-canvas"' in html_content or "id='mempool-canvas'" in html_content
    ), "Canvas should have id='mempool-canvas'"

    # Assert: Canvas dimensions specified (1000x660px per spec)
    assert "1000" in html_content and "660" in html_content, (
        "Canvas should have dimensions 1000x660px (per spec.md Visual Reference)"
    )

    # Assert: JavaScript file loaded in HTML
    assert "mempool-viz.js" in html_content, "HTML should load mempool-viz.js script"

    # Assert: JavaScript module structure (basic validation)
    js_content = js_path.read_text()

    # Assert: WebSocket connection code present in JS (not HTML)
    assert "WebSocket" in js_content or "new WebSocket" in js_content, (
        "JavaScript should contain WebSocket connection code"
    )

    # Check for required Canvas rendering functions/classes
    required_elements = [
        (
            "class MempoolVisualizer" in js_content
            or "function MempoolVisualizer" in js_content,
            "MempoolVisualizer class/function not found (required for Canvas scatter plot)",
        ),
        (
            "render" in js_content.lower() or "draw" in js_content.lower(),
            "No render/draw method found (required for Canvas scatter plot)",
        ),
        (
            "canvas" in js_content.lower() and "ctx" in js_content.lower(),
            "No Canvas context reference found (required for 2D rendering)",
        ),
    ]

    for condition, error_msg in required_elements:
        assert condition, error_msg


# =============================================================================
# T076: Low Confidence Warning Display Test (User Story 3)
# =============================================================================


def test_confidence_warning_display():
    """
    Test that HTML contains confidence warning element.

    Requirements (User Story 3):
    - Warning element exists in HTML
    - Warning text: "⚠ Low confidence - warming up"
    - CSS class for show/hide: confidence-warning

    Task: T076 [US3]
    """
    # Assert: HTML file exists
    html_path = Path("live/frontend/index.html")
    assert html_path.exists(), "Frontend HTML not found"

    html_content = html_path.read_text()

    # Assert: Warning element exists
    assert "confidence-warning" in html_content, "Missing confidence warning element"
    assert "Low confidence" in html_content, "Missing low confidence warning text"
    assert "warming up" in html_content, "Missing warming up text"

    # Assert: CSS file has warning styles
    css_path = Path("live/frontend/styles.css")
    assert css_path.exists(), "CSS file not found"

    css_content = css_path.read_text()

    assert ".confidence-warning" in css_content, (
        "Missing CSS class for confidence warning"
    )
    assert ".confidence-high" in css_content or "confidence-high" in css_content, (
        "Missing high confidence CSS"
    )
    assert ".confidence-medium" in css_content or "confidence-medium" in css_content, (
        "Missing medium confidence CSS"
    )
    assert ".confidence-low" in css_content or "confidence-low" in css_content, (
        "Missing low confidence CSS"
    )


# =============================================================================
# T107-T109: Baseline Visualization Tests (Phase BL-4)
# =============================================================================


def test_baseline_rendering_code_present():
    """
    Test that baseline rendering functionality exists in frontend code.

    Requirements (T107-T109):
    - T107: Render baseline points (cyan) vs mempool (orange)
    - T108: Add baseline price line indicator (horizontal reference)
    - T109: Use baseline price_min/max for Y-axis scaling

    This is a STRUCTURAL test (checks code elements exist).
    Visual rendering requires browser environment - see T110 manual testing.

    Tasks: T107, T108, T109 [Phase BL-4]
    """
    # Assert: JavaScript visualization module exists
    js_path = Path("live/frontend/mempool-viz.js")
    assert js_path.exists(), f"Visualization JS not found: {js_path}"

    js_content = js_path.read_text()

    # T107: Check for baseline data storage
    has_baseline_storage = any(
        [
            "this.baseline" in js_content,
            "baseline =" in js_content,
        ]
    )
    assert has_baseline_storage, (
        "T107: JavaScript should store baseline data (this.baseline or baseline variable)"
    )

    # T107: Check for baseline color (cyan) definition
    has_cyan_color = any(
        [
            "#00FFFF" in js_content,
            "00FFFF" in js_content,
            "cyan" in js_content.lower(),
        ]
    )
    assert has_cyan_color, (
        "T107: JavaScript should define cyan color for baseline (#00FFFF)"
    )

    # T108: Check for baseline line drawing method (must be a function, not just comment)
    has_baseline_line_method = (
        "drawBaselineLine(" in js_content
        or "drawBaselineLine ()" in js_content
        or "function drawBaselineLine" in js_content
    )
    assert has_baseline_line_method, (
        "T108: JavaScript should have drawBaselineLine() method implementation"
    )

    # T108: Check that baseline line is actually called in render()
    # Must be "this.drawBaselineLine()" not just the function definition
    render_calls_baseline = "this.drawBaselineLine()" in js_content
    assert render_calls_baseline, (
        "T108: render() method should call this.drawBaselineLine()"
    )

    # T109: Check for baseline price range usage
    has_price_range = any(
        [
            "price_min" in js_content and "price_max" in js_content,
            "priceMin" in js_content and "priceMax" in js_content,
            "baseline.price_min" in js_content or "baseline.price_max" in js_content,
        ]
    )
    assert has_price_range, (
        "T109: JavaScript should use baseline price_min/price_max for Y-axis scaling"
    )

    # T109: Check for Y-axis scaling logic
    has_scaling = any(
        [
            "scaleY" in js_content,
            "scale_y" in js_content,
            "priceToY" in js_content,
        ]
    )
    assert has_scaling, (
        "T109: JavaScript should have Y-axis scaling method (scaleY or priceToY)"
    )

    # T109: Check that updateData accepts baseline parameter
    has_update_with_baseline = (
        "updateData(transactions, baseline" in js_content
        or "updateData (transactions, baseline" in js_content
    )
    assert has_update_with_baseline, (
        "T109: updateData() should accept baseline parameter (transactions, baseline)"
    )

    # T109: Check that baseline price_min/price_max is used for scaling
    uses_baseline_range = (
        "baseline.price_min" in js_content or "baseline.priceMin" in js_content
    ) and ("baseline.price_max" in js_content or "baseline.priceMax" in js_content)
    assert uses_baseline_range, (
        "T109: Should use baseline.price_min and baseline.price_max for Y-axis scaling"
    )

    # T107-T109: Check that handleMempoolUpdate passes baseline to visualizer
    passes_baseline_to_visualizer = "data.baseline" in js_content and (
        "updateData(" in js_content or "update_data(" in js_content
    )
    assert passes_baseline_to_visualizer, (
        "T107-T109: handleMempoolUpdate should pass data.baseline to visualizer.updateData()"
    )


def test_dual_panel_layout_code_present():
    """
    Test that dual-panel layout code exists for T109.

    Requirements (T109 - Dual Timeline Split):
    - LEFT panel (40%): Baseline/confirmed transactions (cyan points)
    - RIGHT panel (60%): Mempool transactions (orange points)
    - Panel split ratio defined (e.g., PANEL_SPLIT = 0.4)
    - drawBaselinePoints() method exists to render cyan points
    - Labels: "Confirmed On-Chain (3hr)" (cyan) and "Mempool" (orange)

    This is a STRUCTURAL test (checks code elements exist).
    Visual rendering verification requires browser environment - see manual testing.

    Task: T109 [Phase BL-4]
    """
    # Assert: JavaScript visualization module exists
    js_path = Path("live/frontend/mempool-viz.js")
    assert js_path.exists(), f"Visualization JS not found: {js_path}"

    js_content = js_path.read_text()

    # T109: Check for panel split configuration
    has_panel_split = any(
        [
            "panelSplit" in js_content,
            "panel_split" in js_content,
            "PANEL_SPLIT" in js_content,
            "baselineWidth" in js_content and "mempoolWidth" in js_content,
        ]
    )
    assert has_panel_split, (
        "T109: JavaScript should have panel split configuration "
        "(panelSplit ratio or baselineWidth/mempoolWidth)"
    )

    # T109: Check for drawBaselinePoints() method
    has_baseline_points_method = (
        "drawBaselinePoints(" in js_content
        or "drawBaselinePoints ()" in js_content
        or "function drawBaselinePoints" in js_content
    )
    assert has_baseline_points_method, (
        "T109: JavaScript should have drawBaselinePoints() method "
        "to render baseline transaction points"
    )

    # T109: Check for dual timeline labels
    has_confirmed_label = (
        "Confirmed On-Chain" in js_content or "confirmed" in js_content.lower()
    )
    has_mempool_label = "Mempool" in js_content or "mempool" in js_content.lower()
    assert has_confirmed_label, (
        "T109: Should have 'Confirmed On-Chain' label for baseline panel"
    )
    assert has_mempool_label, "T109: Should have 'Mempool' label for real-time panel"


def test_render_calls_dual_panel_methods():
    """
    Test that render() method calls the dual-panel rendering methods.

    Requirements (T109):
    - render() should call this.drawPanelLabels()
    - render() should call this.drawBaselinePoints()
    - render() should use scaleXMempool() for tooltip positioning

    Task: T109 [Phase BL-4]
    """
    js_path = Path("live/frontend/mempool-viz.js")
    assert js_path.exists(), f"Visualization JS not found: {js_path}"

    js_content = js_path.read_text()

    # Find render() method
    assert "render()" in js_content, "render() method not found"

    # Check for method calls with 'this.' prefix (ensures it's called, not just defined)
    render_calls_panel_labels = "this.drawPanelLabels()" in js_content
    assert render_calls_panel_labels, (
        "T109: render() should call this.drawPanelLabels() to show dual panel labels"
    )

    render_calls_baseline_points = "this.drawBaselinePoints()" in js_content
    assert render_calls_baseline_points, (
        "T109: render() should call this.drawBaselinePoints() to render baseline transactions"
    )

    # Check that tooltip uses scaleXMempool (not old scaleX)
    # Should be 'this.scaleXMempool(' in tooltip/render context
    tooltip_uses_mempool_scale = "this.scaleXMempool(" in js_content
    assert tooltip_uses_mempool_scale, (
        "T109: Tooltip should use this.scaleXMempool() for correct positioning in right panel"
    )
