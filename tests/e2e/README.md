# Whale Detection Dashboard - E2E Tests

Playwright-based end-to-end tests for the Whale Detection Dashboard.

## Setup

### 1. Install Playwright

```bash
# Install Python package
uv pip install playwright pytest-playwright

# Install Chromium browser
playwright install chromium
```

### 2. Start Test Environment

Before running tests, ensure the following services are running:

```bash
# Start API server
cd /media/sam/1TB/UTXOracle
.venv/bin/uvicorn api.main:app --reload
```

The tests expect the API to be available at `http://localhost:8000`.

## Running Tests

### Run All Tests

```bash
# From project root
pytest tests/e2e/test_whale_dashboard.py -v
```

### Run Specific Test Classes

```bash
# Page load tests only
pytest tests/e2e/test_whale_dashboard.py::TestPageLoad -v

# WebSocket tests only
pytest tests/e2e/test_whale_dashboard.py::TestWebSocketConnection -v

# Transaction feed tests
pytest tests/e2e/test_whale_dashboard.py::TestTransactionFeed -v

# Chart tests
pytest tests/e2e/test_whale_dashboard.py::TestHistoricalChart -v

# Alert system tests
pytest tests/e2e/test_whale_dashboard.py::TestAlertSystem -v

# Responsive design tests
pytest tests/e2e/test_whale_dashboard.py::TestResponsiveDesign -v

# Error handling tests
pytest tests/e2e/test_whale_dashboard.py::TestErrorHandling -v
```

### Run Specific Test

```bash
pytest tests/e2e/test_whale_dashboard.py::TestPageLoad::test_page_title_and_header -v
```

### Run in Headed Mode (see browser)

```bash
# Set headless=False in test file, or use --headed flag:
pytest tests/e2e/test_whale_dashboard.py --headed -v
```

### Run with Screenshots on Failure

```bash
pytest tests/e2e/test_whale_dashboard.py --screenshot=only-on-failure -v
```

## Test Coverage

| Test Class | Tests | Coverage |
|------------|-------|----------|
| **TestPageLoad** | 5 | Initial page render, sections visible, loading states, no JS errors |
| **TestWebSocketConnection** | 4 | Connection established, data received, feed updates, timestamp changes |
| **TestTransactionFeed** | 8 | Filter panel toggle, filters (amount, direction, urgency), pause/clear |
| **TestHistoricalChart** | 3 | Chart renders, timeframe selector, hover interactions |
| **TestAlertSystem** | 8 | Config panel, sound/volume controls, thresholds, test buttons, persistence |
| **TestResponsiveDesign** | 2 | Mobile (375px) and tablet (768px) layouts |
| **TestErrorHandling** | 2 | WebSocket reconnection, API error handling |

**Total**: 32 tests

## Test Structure

```
tests/e2e/
├── README.md                    # This file
├── test_whale_dashboard.py      # Main test suite
└── conftest.py                  # Shared fixtures (optional)
```

## Writing New Tests

### Test Template

```python
class TestNewFeature:
    """Test description"""

    def test_feature_behavior(self, page: Page):
        """Test specific behavior"""
        # Arrange
        element = page.locator("#element-id")

        # Act
        element.click()

        # Assert
        expect(element).to_have_class("active")
```

### Common Patterns

**Wait for element**:
```python
page.wait_for_selector(".my-element", timeout=5000)
```

**Check visibility**:
```python
expect(page.locator("#element")).to_be_visible()
```

**Check text content**:
```python
expect(page.locator(".title")).to_contain_text("Expected")
```

**Check CSS class**:
```python
expect(page.locator(".btn")).to_have_class(re.compile("active"))
```

**Simulate user input**:
```python
page.locator("#input").fill("value")
page.locator("#button").click()
```

**Check localStorage**:
```python
value = page.evaluate("localStorage.getItem('key')")
assert value == "expected"
```

## Debugging

### View browser while testing

```python
# In test file, change:
browser = p.chromium.launch(headless=False, slow_mo=500)
```

### Pause execution

```python
page.pause()  # Opens Playwright Inspector
```

### Print element properties

```python
element = page.locator("#my-element")
print(element.text_content())
print(element.get_attribute("class"))
print(element.bounding_box())
```

### Check console logs

```python
def test_example(page: Page):
    messages = []
    page.on("console", lambda msg: messages.append(msg.text))

    # ... test actions ...

    print("Console messages:", messages)
```

## CI/CD Integration

### GitHub Actions

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install uv
          uv pip install -r requirements.txt
          playwright install --with-deps chromium

      - name: Start API server
        run: |
          .venv/bin/uvicorn api.main:app &
          sleep 5

      - name: Run E2E tests
        run: pytest tests/e2e/ -v --screenshot=only-on-failure

      - name: Upload screenshots
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: test-screenshots
          path: test-results/
```

## Best Practices

1. **Use meaningful test names**: `test_user_can_filter_by_direction` not `test_1`
2. **Wait for elements**: Always use `wait_for_selector()` or `expect()` with timeout
3. **Clean up**: Tests should not depend on each other's state
4. **Test user behavior**: Click buttons, fill forms (not just check DOM)
5. **Use data-testid**: Add `data-testid` attributes for stable selectors
6. **Handle timing**: Use `expect()` which auto-waits instead of manual `wait_for_timeout()`
7. **Test accessibility**: Use semantic selectors (`role=button`) when possible

## Troubleshooting

### Tests hang or timeout

- Increase timeout: `page.wait_for_selector(".element", timeout=30000)`
- Check if API server is running
- Check WebSocket connection in browser DevTools

### Element not found

- Verify selector is correct: `page.locator("#my-id").count()`
- Check if element is in iframe: `page.frame_locator("iframe").locator(".element")`
- Wait for page to load: `page.wait_for_load_state("networkidle")`

### Test passes locally but fails in CI

- Different viewport sizes - specify in test
- Race conditions - add explicit waits
- Missing data - ensure test data is seeded

## Resources

- [Playwright Python Docs](https://playwright.dev/python/docs/intro)
- [Playwright Selectors](https://playwright.dev/python/docs/selectors)
- [Playwright Assertions](https://playwright.dev/python/docs/test-assertions)
- [Best Practices](https://playwright.dev/python/docs/best-practices)
