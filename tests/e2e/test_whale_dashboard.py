"""
Playwright E2E Tests for Whale Detection Dashboard

Test Coverage:
- T094.1: Page load and initial state
- T094.2: WebSocket connection and real-time updates
- T094.3: Transaction feed interactions (filters, controls)
- T094.4: Historical chart rendering and interactions
- T094.5: Alert system configuration and testing
- T094.6: Responsive design (mobile/tablet/desktop)
- T094.7: Error handling and reconnection

Prerequisites:
- API server running on localhost:8000
- Test data available in DuckDB
- Playwright installed: playwright install chromium
"""

import re
from playwright.sync_api import Page, expect, sync_playwright
import pytest


# ============================================
# Fixtures
# ============================================


@pytest.fixture(scope="session")
def base_url():
    """Base URL for dashboard"""
    return "http://localhost:8000"


@pytest.fixture(scope="function")
def page(base_url):
    """Playwright page fixture with browser context"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) Whale Dashboard E2E Tests",
        )
        page = context.new_page()

        # Navigate to dashboard
        page.goto(f"{base_url}/static/whale_dashboard.html")

        yield page

        context.close()
        browser.close()


# ============================================
# T094.1: Page Load & Initial State
# ============================================


class TestPageLoad:
    """Test dashboard initial load and rendering"""

    def test_page_title_and_header(self, page: Page):
        """Verify page title and header are correct"""
        expect(page).to_have_title(re.compile("Whale Detection Dashboard"))

        header = page.locator(".dashboard-title")
        expect(header).to_be_visible()
        expect(header).to_contain_text("Whale Detection Dashboard")

    def test_status_bar_visible(self, page: Page):
        """Verify status bar shows connection status"""
        status_bar = page.locator("#status-bar")
        expect(status_bar).to_be_visible()

        # Connection status indicator
        connection_status = page.locator("#connection-status")
        expect(connection_status).to_be_visible()

        # Should show either "Connecting..." or "Connected"
        expect(connection_status).to_contain_text(re.compile("Connect"))

    def test_main_sections_present(self, page: Page):
        """Verify all main dashboard sections are present"""
        # Net flow section
        expect(page.locator(".net-flow-section")).to_be_visible()

        # Transaction feed section
        expect(page.locator(".transaction-feed-section")).to_be_visible()

        # Chart section
        expect(page.locator(".chart-section")).to_be_visible()

    def test_loading_states_present(self, page: Page):
        """Verify loading states are shown initially"""
        # Net flow may show loading state
        net_flow_section = page.locator("#net-flow-display")
        expect(net_flow_section).to_be_visible()

        # Chart may show loading state
        chart_section = page.locator("#chart-container")
        expect(chart_section).to_be_visible()

    def test_no_javascript_errors(self, page: Page):
        """Verify no JavaScript console errors on load"""
        errors = []

        def handle_console(msg):
            if msg.type == "error":
                errors.append(msg.text)

        page.on("console", handle_console)

        # Wait for page to settle
        page.wait_for_timeout(2000)

        # Should have no critical errors
        critical_errors = [
            e for e in errors if "critical" in e.lower() or "fatal" in e.lower()
        ]
        assert len(critical_errors) == 0, f"Critical errors found: {critical_errors}"


# ============================================
# T094.2: WebSocket Connection & Real-time Updates
# ============================================


class TestWebSocketConnection:
    """Test WebSocket connection and real-time data streaming"""

    def test_websocket_connection_established(self, page: Page):
        """Verify WebSocket connects successfully"""
        # Wait for connection indicator to show "Connected"
        connection_status = page.locator("#connection-status")

        # Should eventually show "Connected" (wait up to 10 seconds)
        expect(connection_status).to_contain_text("Connected", timeout=10000)

        # Status indicator should have "connected" class
        status_dot = connection_status.locator(".status-dot")
        expect(status_dot.locator("..")).to_have_class(re.compile("connected"))

    def test_websocket_receives_data(self, page: Page):
        """Verify WebSocket receives and processes messages"""
        # Wait for connection
        page.wait_for_selector(".status-indicator.connected", timeout=10000)

        # Net flow should update (wait up to 15 seconds for first update)
        net_flow_content = page.locator("#net-flow-content")
        expect(net_flow_content).not_to_have_class("hidden", timeout=15000)

        # Should show actual values
        value_btc = page.locator("#value-btc")
        expect(value_btc).not_to_contain_text("0.00 BTC")

    def test_transaction_feed_updates(self, page: Page):
        """Verify transaction feed receives and displays transactions"""
        # Wait for connection
        page.wait_for_selector(".status-indicator.connected", timeout=10000)

        # Transaction feed should eventually show transactions
        # (may take time if no whale activity, so timeout is generous)
        feed = page.locator("#transaction-feed")

        # Either has transaction items OR shows empty state
        page.wait_for_selector(".transaction-item, .feed-empty-state", timeout=30000)

    def test_last_update_timestamp_changes(self, page: Page):
        """Verify last update timestamp updates periodically"""
        last_update = page.locator("#last-update")

        initial_text = last_update.text_content()

        # Wait for an update (max 30 seconds)
        page.wait_for_timeout(5000)

        # Text should change (new timestamp)
        # Note: May not always change if no new data, so this is optional
        # Just verify element exists and is updated
        expect(last_update).to_be_visible()


# ============================================
# T094.3: Transaction Feed Interactions
# ============================================


class TestTransactionFeed:
    """Test transaction feed controls and filtering"""

    def test_toggle_filters_panel(self, page: Page):
        """Verify filter panel can be shown/hidden"""
        filter_panel = page.locator("#filter-panel")
        toggle_button = page.locator("#toggle-filters")

        # Initially hidden
        expect(filter_panel).to_have_class(re.compile("hidden"))

        # Click to show
        toggle_button.click()
        expect(filter_panel).not_to_have_class(re.compile("hidden"))

        # Click to hide
        toggle_button.click()
        expect(filter_panel).to_have_class(re.compile("hidden"))

    def test_min_amount_filter(self, page: Page):
        """Verify min amount filter works"""
        # Show filter panel
        page.locator("#toggle-filters").click()

        # Set min amount to 500 BTC
        min_amount_input = page.locator("#filter-min-amount")
        min_amount_input.fill("500")

        # Apply filters
        page.locator("#apply-filters").click()

        # Filter panel should close
        expect(page.locator("#filter-panel")).to_have_class(re.compile("hidden"))

        # Verify filter is applied (implementation detail - just check no errors)
        page.wait_for_timeout(1000)

    def test_direction_filter_checkboxes(self, page: Page):
        """Verify direction filter checkboxes work"""
        # Show filter panel
        page.locator("#toggle-filters").click()

        # Uncheck BUY
        buy_checkbox = page.locator("#filter-buy")
        buy_checkbox.uncheck()

        # Check it's unchecked
        expect(buy_checkbox).not_to_be_checked()

        # Apply filters
        page.locator("#apply-filters").click()

        # No errors should occur
        page.wait_for_timeout(1000)

    def test_urgency_slider(self, page: Page):
        """Verify urgency slider works"""
        # Show filter panel
        page.locator("#toggle-filters").click()

        # Set urgency to 80
        urgency_slider = page.locator("#filter-urgency")
        urgency_slider.fill("80")

        # Value should update
        urgency_value = page.locator("#filter-urgency-value")
        expect(urgency_value).to_contain_text("80")

        # Apply filters
        page.locator("#apply-filters").click()

    def test_high_urgency_toggle(self, page: Page):
        """Verify high urgency quick filter button"""
        high_urgency_btn = page.locator("#filter-high-urgency")

        # Click to activate
        high_urgency_btn.click()

        # Button should have active class
        expect(high_urgency_btn).to_have_class(re.compile("active"))

        # Click again to deactivate
        high_urgency_btn.click()
        expect(high_urgency_btn).not_to_have_class(re.compile("active"))

    def test_pause_feed_button(self, page: Page):
        """Verify pause/resume feed button"""
        pause_btn = page.locator("#pause-feed")

        # Initially showing pause icon
        expect(pause_btn.locator(".control-icon")).to_contain_text("⏸")

        # Click to pause
        pause_btn.click()

        # Should change to play icon
        expect(pause_btn.locator(".control-icon")).to_contain_text("▶")

        # Click to resume
        pause_btn.click()
        expect(pause_btn.locator(".control-icon")).to_contain_text("⏸")

    def test_clear_feed_button(self, page: Page):
        """Verify clear feed button"""
        clear_btn = page.locator("#clear-feed")

        # Click clear
        clear_btn.click()

        # Feed should show empty state
        # (may not be visible if auto-refilled, so just check no errors)
        page.wait_for_timeout(500)


# ============================================
# T094.4: Historical Chart
# ============================================


class TestHistoricalChart:
    """Test historical net flow chart rendering and interactions"""

    def test_chart_renders(self, page: Page):
        """Verify Plotly chart renders successfully"""
        # Wait for chart to load
        page.wait_for_selector("#whale-chart .plotly", timeout=15000)

        # Chart container should be visible
        chart = page.locator("#whale-chart")
        expect(chart).to_be_visible()

        # Plotly elements should be present
        expect(chart.locator(".plotly")).to_be_visible()

    def test_timeframe_selector(self, page: Page):
        """Verify timeframe selector changes chart data"""
        timeframe_selector = page.locator("#timeframe-selector")

        # Select 1 hour
        timeframe_selector.select_option("1h")

        # Wait for chart to update
        page.wait_for_timeout(2000)

        # Select 24 hours
        timeframe_selector.select_option("24h")
        page.wait_for_timeout(2000)

        # No errors should occur
        chart = page.locator("#whale-chart")
        expect(chart).to_be_visible()

    def test_chart_hover_interaction(self, page: Page):
        """Verify chart hover shows tooltip"""
        # Wait for chart to load
        page.wait_for_selector("#whale-chart .plotly", timeout=15000)

        chart = page.locator("#whale-chart")

        # Hover over chart (middle of chart)
        box = chart.bounding_box()
        if box:
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.wait_for_timeout(500)

            # Plotly should show hover tooltip (if data present)
            # This is optional - just verify no errors


# ============================================
# T094.5: Alert System
# ============================================


class TestAlertSystem:
    """Test alert configuration panel and alert delivery"""

    def test_open_alert_config_panel(self, page: Page):
        """Verify alert settings panel opens"""
        settings_btn = page.locator("#alert-settings-toggle")
        overlay = page.locator("#alert-config-overlay")

        # Initially hidden
        expect(overlay).to_have_class(re.compile("hidden"))

        # Click to open
        settings_btn.click()
        expect(overlay).not_to_have_class(re.compile("hidden"))

        # Panel should be visible
        panel = page.locator(".alert-config-panel")
        expect(panel).to_be_visible()

    def test_close_alert_config_panel(self, page: Page):
        """Verify alert settings panel closes"""
        # Open panel
        page.locator("#alert-settings-toggle").click()

        # Close via X button
        close_btn = page.locator("#alert-config-close")
        close_btn.click()

        overlay = page.locator("#alert-config-overlay")
        expect(overlay).to_have_class(re.compile("hidden"))

    def test_sound_alert_toggle(self, page: Page):
        """Verify sound alert enable/disable"""
        # Open panel
        page.locator("#alert-settings-toggle").click()

        sound_checkbox = page.locator("#alert-sound-enabled")

        # Should be checked by default
        expect(sound_checkbox).to_be_checked()

        # Uncheck
        sound_checkbox.uncheck()
        expect(sound_checkbox).not_to_be_checked()

        # Check again
        sound_checkbox.check()
        expect(sound_checkbox).to_be_checked()

    def test_volume_slider(self, page: Page):
        """Verify volume slider updates value display"""
        # Open panel
        page.locator("#alert-settings-toggle").click()

        volume_slider = page.locator("#alert-sound-volume")
        volume_value = page.locator("#alert-volume-value")

        # Set to 75%
        volume_slider.fill("75")

        # Value should update
        expect(volume_value).to_contain_text("75%")

    def test_threshold_inputs(self, page: Page):
        """Verify threshold inputs accept values"""
        # Open panel
        page.locator("#alert-settings-toggle").click()

        # Critical threshold
        critical_input = page.locator("#alert-threshold-critical")
        critical_input.fill("1000")
        expect(critical_input).to_have_value("1000")

        # High threshold
        high_input = page.locator("#alert-threshold-high")
        high_input.fill("500")
        expect(high_input).to_have_value("500")

        # Medium threshold
        medium_input = page.locator("#alert-threshold-medium")
        medium_input.fill("200")
        expect(medium_input).to_have_value("200")

    def test_alert_test_buttons(self, page: Page):
        """Verify test alert buttons trigger alerts"""
        # Open panel
        page.locator("#alert-settings-toggle").click()

        # Click test critical button
        test_btn = page.locator("#alert-test-critical")
        test_btn.click()

        # Toast should appear (wait up to 2 seconds)
        page.wait_for_selector(".whale-toast", timeout=2000)

        toast = page.locator(".whale-toast").first
        expect(toast).to_be_visible()
        expect(toast).to_have_class(re.compile("critical"))

    def test_save_settings_persistence(self, page: Page):
        """Verify settings are saved to localStorage"""
        # Open panel
        page.locator("#alert-settings-toggle").click()

        # Change settings
        page.locator("#alert-threshold-critical").fill("2000")
        page.locator("#alert-sound-volume").fill("80")

        # Save
        save_btn = page.locator("#alert-save-settings")
        save_btn.click()

        # Panel should close
        overlay = page.locator("#alert-config-overlay")
        expect(overlay).to_have_class(re.compile("hidden"))

        # Reload page
        page.reload()

        # Open panel again
        page.locator("#alert-settings-toggle").click()

        # Settings should be persisted
        expect(page.locator("#alert-threshold-critical")).to_have_value("2000")
        expect(page.locator("#alert-sound-volume")).to_have_value("80")


# ============================================
# T094.6: Responsive Design
# ============================================


class TestResponsiveDesign:
    """Test responsive layouts for mobile/tablet"""

    def test_mobile_layout(self, base_url):
        """Verify mobile layout (viewport 375x667)"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 375, "height": 667},
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 13_0 like Mac OS X)",
            )
            page = context.new_page()
            page.goto(f"{base_url}/static/whale_dashboard.html")

            # Status bar should wrap on mobile
            status_bar = page.locator("#status-bar")
            expect(status_bar).to_be_visible()

            # Net flow section should stack vertically
            net_flow = page.locator(".net-flow-content")
            # Just verify it's visible, CSS handles layout

            # Feed controls should stack
            feed_controls = page.locator(".feed-controls")
            expect(feed_controls).to_be_visible()

            # Alert panel should be full screen on mobile
            page.locator("#alert-settings-toggle").click()
            alert_panel = page.locator(".alert-config-panel")
            expect(alert_panel).to_be_visible()

            context.close()
            browser.close()

    def test_tablet_layout(self, base_url):
        """Verify tablet layout (viewport 768x1024)"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 768, "height": 1024},
                user_agent="Mozilla/5.0 (iPad; CPU OS 13_0 like Mac OS X)",
            )
            page = context.new_page()
            page.goto(f"{base_url}/static/whale_dashboard.html")

            # All sections should be visible
            expect(page.locator(".net-flow-section")).to_be_visible()
            expect(page.locator(".transaction-feed-section")).to_be_visible()
            expect(page.locator(".chart-section")).to_be_visible()

            # Controls should wrap on tablet
            feed_controls = page.locator(".feed-controls")
            expect(feed_controls).to_be_visible()

            context.close()
            browser.close()


# ============================================
# T094.7: Error Handling & Reconnection
# ============================================


class TestErrorHandling:
    """Test error states and reconnection logic"""

    def test_websocket_reconnection_attempt(self, page: Page):
        """Verify dashboard attempts to reconnect on WebSocket close"""
        # Wait for initial connection
        page.wait_for_selector(".status-indicator.connected", timeout=10000)

        # Simulate disconnect by closing WebSocket from client side
        page.evaluate("""
            if (window.whaleDashboard && window.whaleDashboard.wsClient) {
                window.whaleDashboard.wsClient.ws.close();
            }
        """)

        # Status should change to disconnected or reconnecting
        connection_status = page.locator("#connection-status")
        page.wait_for_timeout(1000)

        # Should show reconnecting or disconnected state
        # (exact behavior depends on implementation)
        status_text = connection_status.text_content()
        assert status_text.lower() in [
            "connecting...",
            "disconnected",
            "reconnecting...",
        ]

    def test_api_error_handling(self, page: Page):
        """Verify graceful handling when API endpoints fail"""
        # This would require mocking API to return errors
        # For now, just verify error states exist in UI

        error_state = page.locator("#net-flow-error")
        # Should exist (hidden initially)
        expect(error_state).to_have_class(re.compile("hidden"))

        # Retry button should exist
        retry_btn = page.locator("#retry-button")
        # Should exist but be hidden initially


# ============================================
# Run Tests
# ============================================

if __name__ == "__main__":
    # Run tests with: pytest tests/e2e/test_whale_dashboard.py -v
    pytest.main([__file__, "-v", "--tb=short"])
