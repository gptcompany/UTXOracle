# 🌐 Browser MCP Quick Reference

**Created**: 2025-10-20
**Purpose**: Guide to browser MCP profiles for visualization testing

---

## 📋 Available Browser Profiles

| Profile | MCP Servers | Tools Count | Use Case |
|---------|-------------|-------------|----------|
| **ccbrowser** | Browserbase | 19 | Cloud browser automation + AI actions |
| **ccbrowser2** (ccviz) | Playwright + Chrome DevTools + chrome-mcp-server | 26 + 26 + local | Local testing + debugging |
| **ccfullbrowser** ✨ | ALL 4 servers | 71+ | Maximum browser capabilities |

---

## 🎯 When to Use Each Profile

### **ccbrowser** - Cloud Browser (Browserbase)
```bash
ccbrowser
```

**Best for**:
- ✅ Cloud deployment testing
- ✅ AI-powered interactions (`act`, `observe`)
- ✅ Session persistence (cookies, auth)
- ✅ Multi-session management

**Key Tools**:
- `browserbase_navigate` - Navigate to URL
- `browserbase_screenshot` - Screenshot (Base64)
- `browserbase_act` - AI action ("click login")
- `browserbase_observe` - Find elements with AI
- `browserbase_extract` - Extract page text
- `browserbase_session_create` - Cloud session

**Requirements**: 
- `.env` with `BROWSERBASE_API_KEY` and `BROWSERBASE_PROJECT_ID`

---

### **ccbrowser2** (alias: ccviz) - Local Testing
```bash
ccbrowser2  # or ccviz
```

**Best for**:
- ✅ Local HTML file testing (file://)
- ✅ Development iteration (fast reload)
- ✅ Console debugging
- ✅ Performance analysis
- ✅ Screenshot comparison

**Key Tools - Playwright**:
- `browser_navigate` - Navigate local/remote
- `browser_take_screenshot` - Screenshot
- `browser_console_messages` - Console logs
- `browser_click` - Interact with page
- `browser_type` - Fill forms
- `browser_evaluate_script` - Execute JS

**Key Tools - Chrome DevTools**:
- `navigate_page` - Navigate + wait
- `take_screenshot` - Screenshot + perf
- `list_console_messages` - Console debug
- `evaluate_script` - Execute JS in browser
- `performance_start_trace` - Record trace
- `performance_analyze_insight` - Perf insights
- `list_network_requests` - Network monitor

**Requirements**: None (works offline)

---

### **ccfullbrowser** ✨ - Maximum Power
```bash
ccfullbrowser
```

**Best for**:
- ✅ Advanced testing scenarios
- ✅ Cloud + local hybrid testing
- ✅ Maximum tool availability
- ✅ Complex automation workflows

**All Tools**: 71+ (combination of all 4 MCP servers)

**Note**: Slower startup (loads all servers), higher token usage

---

## 🔧 MCP Server Details

### **1. Browserbase** (@browserbasehq/mcp-server-browserbase)

**Config**: `.mcp.browser.json`
**Type**: Cloud browser automation
**Tools**: 19

```json
{
  "mcpServers": {
    "browserbase": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@browserbasehq/mcp-server-browserbase"],
      "env": {
        "BROWSERBASE_API_KEY": "${BROWSERBASE_API_KEY}",
        "BROWSERBASE_PROJECT_ID": "${BROWSERBASE_PROJECT_ID}"
      }
    }
  }
}
```

**Key Features**:
- AI-powered element detection
- Cloud session persistence
- Multi-browser support
- Cookie/auth management

---

### **2. Playwright MCP** (@playwright/mcp)

**Config**: `.mcp.browser2.json`
**Type**: Browser automation framework
**Tools**: 26

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"],
      "env": {}
    }
  }
}
```

**Key Features**:
- Cross-browser support (Chrome, Firefox, Safari)
- Fast local automation
- Accessibility tree snapshots
- File upload, drag-drop

---

### **3. Chrome DevTools MCP** (chrome-devtools-mcp)

**Config**: `.mcp.browser2.json`
**Type**: Chrome debugging protocol
**Tools**: 26

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["chrome-devtools-mcp@latest"],
      "env": {}
    }
  }
}
```

**Key Features**:
- Performance tracing
- Network monitoring
- Console debugging
- CPU/network emulation

---

### **4. Chrome MCP Server** (chrome-mcp-server)

**Config**: `.mcp.browser2.json`
**Type**: Local HTTP server
**Tools**: Custom (localhost:12306)

```json
{
  "mcpServers": {
    "chrome-mcp-server": {
      "type": "http",
      "url": "http://127.0.0.1:12306/mcp"
    }
  }
}
```

**Requirements**: Server must be running on port 12306

---

## 🎨 visualization-renderer Agent Tools

**Agent**: visualization-renderer
**File**: `.claude/agents/visualization-renderer.md`

**Browser Tools (13)**:
```yaml
# Playwright
- mcp__playwright__browser_navigate
- mcp__playwright__browser_take_screenshot
- mcp__playwright__browser_console_messages

# Chrome DevTools
- mcp__chrome-devtools__navigate_page
- mcp__chrome-devtools__take_screenshot
- mcp__chrome-devtools__list_console_messages
- mcp__chrome-devtools__evaluate_script

# Browserbase
- mcp__browserbase__navigate
- mcp__browserbase__screenshot
- mcp__browserbase__extract
- mcp__browserbase__act
- mcp__browserbase__observe
- mcp__browserbase__session_create
```

---

## 📊 Comparison Matrix

| Feature | ccbrowser | ccbrowser2 | ccfullbrowser |
|---------|-----------|------------|---------------|
| **Startup Speed** | Fast | Medium | Slow |
| **Token Usage** | Low | Medium | High |
| **Cloud Testing** | ✅ Yes | ❌ No | ✅ Yes |
| **Local Testing** | ❌ No | ✅ Yes | ✅ Yes |
| **AI Actions** | ✅ Yes | ❌ No | ✅ Yes |
| **Performance Analysis** | ❌ No | ✅ Yes | ✅ Yes |
| **Offline Work** | ❌ No | ✅ Yes | ✅ Yes |
| **Requires .env** | ✅ Yes | ❌ No | ✅ Yes |

---

## 💡 Recommended Workflows

### **Workflow 1: Canvas Development**
```bash
# 1. Start with local testing (fast iteration)
ccviz

# Prompt:
"Use visualization-renderer to implement Canvas 2D scatter plot"

# Agent will:
# - Write live/frontend/mempool-viz.js
# - Open in browser (playwright navigate)
# - Screenshot render
# - Debug console errors
```

### **Workflow 2: Three.js WebGL**
```bash
# 1. Local dev
ccviz

# 2. Cloud testing (deployment verification)
ccbrowser

# 3. Performance analysis
ccbrowser2  # Use performance_start_trace
```

### **Workflow 3: Full Integration Testing**
```bash
ccfullbrowser

# All tools available:
# - Browserbase AI actions
# - Playwright automation
# - Chrome DevTools profiling
# - Local HTTP server
```

---

## 🐛 Troubleshooting

### Browser tools not working
```bash
# Verify MCP config syntax
jq . .mcp.fullbrowser.json

# Test profile loads
ccfullbrowser --version
```

### .env not loaded
```bash
# Check .env exists
ls -la /media/sam/1TB/UTXOracle/.env

# Manually load
source ~/.bashrc
ccbrowser  # Should show "✅ Loaded environment"
```

### Port 12306 not responding
```bash
# Start chrome-mcp-server manually
# (server startup command depends on your setup)
```

### Playwright installation
```bash
# Install browsers
npx playwright install
```

---

## 🔐 Security

**IMPORTANT**: `.env` contains API keys!

```bash
# Verify .env permissions (should be 600)
ls -la .env
# -rw------- (only owner can read/write)

# Fix if needed
chmod 600 .env

# Never commit .env
git status .env  # Should show in .gitignore
```

---

## 📝 Quick Commands

```bash
# Reload aliases
source ~/.bashrc

# Test browser profiles
ccbrowser --help
ccbrowser2 --help
ccfullbrowser --help

# Check loaded MCP servers
# (after starting Claude with profile)
# Type: /mcp list

# Analyze pattern usage
python3 .claude/scripts/analyze_patterns.py
```

---

**Created**: 2025-10-20
**Last Updated**: 2025-10-20
**Status**: ✅ All 3 profiles configured and tested
