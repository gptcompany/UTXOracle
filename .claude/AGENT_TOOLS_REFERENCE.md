# 🛠️ Agent Tools Reference

**Created**: 2025-10-20
**Purpose**: Quick reference for MCP tool wildcards and agent tool assignments

---

## 📋 MCP Wildcard Syntax

### **Wildcard Pattern**:
```yaml
tools: mcp__<server-name>__*
```

**Example**:
```yaml
# Load ALL Serena tools (10+ tools)
tools: Read, Write, Edit, mcp__serena__*, TodoWrite

# Load ALL Playwright tools (26 tools)
tools: mcp__playwright__*, mcp__chrome-devtools__*
```

**Benefits**:
- ✅ Futureproof (new tools automatically available)
- ✅ Less maintenance (no need to list individual tools)
- ✅ Cleaner agent definitions

---

## 🎯 Agent Tool Matrix

| Agent | Code Work | Serena | context7 | gemini | Browser Tools |
|-------|-----------|--------|----------|--------|---------------|
| **bitcoin-onchain-expert** | Python (ZMQ) | ✅ `*` | ✅ | - | - |
| **data-streamer** | Python (FastAPI) | ✅ `*` | ✅ | - | - |
| **mempool-analyzer** | Python (algorithms) | ✅ `*` | ✅ | - | - |
| **transaction-processor** | Python (binary) | ✅ `*` | ✅ | - | - |
| **visualization-renderer** | JavaScript (Canvas) | - | ✅ | ✅ | ✅ All 3 |
| **tdd-guard** | Test enforcement | - | - | - | - |

---

## 🔍 Available MCP Servers & Tools

### **Serena** (Code Navigation)

**Wildcard**: `mcp__serena__*`

**Tools** (~10):
- `list_dir` - List files in directory
- `find_file` - Find files by pattern
- `get_symbols_overview` - File structure overview
- `find_symbol` - Find class/function by name
- `find_referencing_symbols` - Find usages
- `search_for_pattern` - Grep-like search
- `replace_symbol_body` - Replace function/class
- `insert_after_symbol` - Insert code after symbol
- `insert_before_symbol` - Insert code before symbol
- `read_memory` - Read project memory
- `write_memory` - Save project knowledge

**Use case**: Code navigation, refactoring, symbol search

---

### **Context7** (Library Docs)

**Wildcard**: `mcp__context7__*`

**Tools** (~2):
- `get-library-docs` - Fetch library documentation
- `resolve-library-id` - Resolve library names

**Use case**: Looking up API docs for libraries

---

### **Gemini CLI** (AI Assistant)

**Wildcard**: `mcp__gemini-cli__*`

**Tools** (~1):
- `ask-gemini` - Query Gemini AI for help

**Use case**: Frontend/JS help, alternative AI perspective

---

### **Playwright** (Browser Automation)

**Wildcard**: `mcp__playwright__*`

**Tools** (26):
- Navigation: `browser_navigate`, `browser_navigate_back`, `browser_navigate_forward`
- Interaction: `browser_click`, `browser_type`, `browser_hover`, `browser_drag`
- Content: `browser_take_screenshot`, `browser_snapshot`, `browser_pdf_save`
- Debug: `browser_console_messages`, `browser_network_requests`
- Tabs: `browser_tab_list`, `browser_tab_new`, `browser_tab_select`, `browser_tab_close`
- Advanced: `browser_file_upload`, `browser_handle_dialog`, `browser_generate_playwright_test`

**Use case**: Local browser testing, E2E automation

---

### **Chrome DevTools** (Performance Analysis)

**Wildcard**: `mcp__chrome-devtools__*`

**Tools** (26):
- Navigation: `navigate_page`, `new_page`, `select_page`
- Performance: `performance_start_trace`, `performance_stop_trace`, `performance_analyze_insight`
- Content: `take_screenshot`, `take_snapshot`, `evaluate_script`
- Debug: `list_console_messages`, `list_network_requests`
- Emulation: `emulate_cpu`, `emulate_network`, `resize_page`
- Interaction: `click`, `fill`, `fill_form`, `hover`, `drag`, `upload_file`

**Use case**: Performance profiling, advanced debugging

---

### **Browserbase** (Cloud Browser)

**Wildcard**: `mcp__browserbase__*`

**Tools** (19):
- Core: `navigate`, `act`, `extract`, `observe`, `screenshot`
- Session: `session_create`, `session_close`
- Multi-session: `multi_browserbase_stagehand_session_create`, `multi_browserbase_stagehand_session_list`
- Cookies: `browserbase_cookies_add`

**Use case**: Cloud browser automation with AI-powered element detection

---

## 📝 Agent-Specific Tool Usage

### **Python Development Agents**

All Python agents should have **Serena wildcard**:

```yaml
tools: Read, Write, Edit, Bash, Glob, Grep, mcp__serena__*, mcp__context7__*, TodoWrite
```

**Why**: Code navigation essential for Python work

---

### **visualization-renderer** (Frontend)

```yaml
tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch, 
  mcp__context7__*, 
  mcp__gemini-cli__*, 
  mcp__playwright__*, 
  mcp__chrome-devtools__*, 
  mcp__browserbase__*, 
  TodoWrite
```

**Why**: Needs all 3 browser MCP servers for testing Canvas/Three.js renders

---

### **tdd-guard**

```yaml
# No MCP tools needed (uses Bash for test execution)
```

---

## 🎨 Best Practices

### **When to Use Wildcards**

✅ **DO use wildcard** when:
- Agent works extensively with that domain (Python → Serena)
- Want all current + future tools (futureproof)
- Server has <30 tools (reasonable overhead)

❌ **DON'T use wildcard** when:
- Only need 1-2 specific tools
- Server has 100+ tools (huge overhead)
- Want tight security control

### **Wildcard Examples**

```yaml
# ✅ Good: Python agent needs all Serena tools
tools: mcp__serena__*, mcp__context7__*

# ✅ Good: Browser testing needs all playwright
tools: mcp__playwright__*, mcp__chrome-devtools__*

# ❌ Overkill: Only need 1 tool
tools: mcp__context7__*  # Just use get-library-docs

# ✅ Better: Specific tool
tools: mcp__context7__get-library-docs
```

---

## 🔄 Migration Guide

### **From Specific Tools → Wildcard**

**Before**:
```yaml
tools: mcp__serena__find_symbol, mcp__serena__get_symbols_overview, mcp__serena__find_referencing_symbols
```

**After**:
```yaml
tools: mcp__serena__*
```

**Benefits**:
- 70% shorter tool definition
- Auto-includes new Serena tools
- Easier to maintain

---

## 📊 Token Cost Analysis

| Pattern | Tool Count | Estimated Token Cost | When to Use |
|---------|------------|---------------------|-------------|
| Specific (3 tools) | 3 | ~300 tokens | Only need 1-3 tools |
| Wildcard (all tools) | 10-26 | ~500-1,000 tokens | Need most tools |
| Multiple wildcards | 50+ | ~2,000+ tokens | visualization-renderer |

**Recommendation**: Use wildcard if you need >3 tools from same server.

---

**Updated**: 2025-10-20
**Status**: ✅ All Python agents standardized with `mcp__serena__*`
