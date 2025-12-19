# Quickstart: Metrics Dashboard Pages

## Prerequisites

1. **FastAPI Backend Running**
   ```bash
   cd /media/sam/1TB/UTXOracle
   uv run uvicorn api.main:app --reload --port 8000
   ```

2. **Browser** (Chrome, Firefox, or Safari)

## Development Setup

### 1. Directory Structure

Create the metrics directory:
```bash
mkdir -p frontend/metrics
```

### 2. Serve Frontend

Option A: Use Python's built-in server:
```bash
cd frontend
python -m http.server 8080
```

Option B: Use FastAPI static files (already configured in api/main.py)

### 3. Access Pages

- MVRV: http://localhost:8080/metrics/mvrv.html
- NUPL: http://localhost:8080/metrics/nupl.html
- etc.

## Development Workflow

### 1. Create New Metric Page

Copy template from mvrv.html and modify:
```bash
cp frontend/metrics/mvrv.html frontend/metrics/new_metric.html
```

Edit:
- Page title
- API endpoint
- Trace configuration
- Zone boundaries

### 2. Test Locally

1. Start backend: `uv run uvicorn api.main:app --reload`
2. Open page in browser
3. Check console for errors (F12)
4. Verify data loads correctly

### 3. Visual Validation

Compare with CheckOnChain:
1. Open your page: http://localhost:8080/metrics/mvrv.html
2. Open reference: https://charts.checkonchain.com/btconchain/unrealised/mvrv_all/mvrv_all_light.html
3. Compare trend shape and zones

## Common Issues

### CORS Errors

If fetch fails with CORS, ensure FastAPI has CORS middleware:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
```

### API Returns Empty Data

Check if database has historical data:
```bash
curl http://localhost:8000/api/metrics/nupl
```

### Chart Not Rendering

1. Check browser console for JavaScript errors
2. Verify Plotly CDN loaded
3. Check container element exists

## File Templates

### Basic HTML Page

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>METRIC_NAME - UTXOracle</title>
  <link rel="stylesheet" href="../css/metrics.css">
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
</head>
<body>
  <div id="chart"></div>
  <script src="../js/metrics-common.js"></script>
  <script src="../js/chart-themes.js"></script>
  <script>
    // Page-specific chart code
  </script>
</body>
</html>
```

## Next Steps

1. Create shared utilities (`metrics-common.js`, `chart-themes.js`)
2. Build MVRV page as template
3. Replicate for other metrics
4. Run visual validation with alpha-visual
