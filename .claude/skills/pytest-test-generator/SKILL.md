---
name: pytest-test-generator
description: Generate pytest test templates for UTXOracle modules following TDD patterns. Automatically creates RED phase tests with async fixtures, coverage markers, and integration test stubs.
---

# Pytest Test Generator

Generate standardized pytest tests for UTXOracle Live modules following strict TDD discipline.

## Quick Start

**User says**: "Generate tests for zmq_listener"

**Skill generates**:
```python
# tests/test_zmq_listener.py
import pytest
from live.backend.zmq_listener import ZMQListener

@pytest.fixture
async def zmq_listener():
    """Fixture for ZMQ listener"""
    listener = ZMQListener()
    yield listener
    await listener.close()

async def test_zmq_connection(zmq_listener):
    """Test ZMQ connects to Bitcoin Core"""
    assert await zmq_listener.connect() == True

async def test_transaction_stream(zmq_listener):
    """Test receiving raw tx bytes"""
    async for tx_bytes in zmq_listener.stream():
        assert isinstance(tx_bytes, bytes)
        assert len(tx_bytes) > 0
        break  # Test at least one transaction
```

## Templates

### 1. Async Module Test Template
```python
import pytest
from live.backend.{module} import {ClassName}

@pytest.fixture
async def {module_instance}():
    """{Description}"""
    instance = {ClassName}()
    yield instance
    await instance.cleanup()

async def test_{function_name}({module_instance}):
    """Test {description}"""
    result = await {module_instance}.{method}()
    assert result is not None
```

### 2. Sync Module Test Template
```python
import pytest
from live.backend.{module} import {ClassName}

@pytest.fixture
def {module_instance}():
    """{Description}"""
    return {ClassName}()

def test_{function_name}({module_instance}):
    """Test {description}"""
    result = {module_instance}.{method}()
    assert result is not None
```

### 3. Integration Test Template
```python
import pytest
from live.backend.{module1} import {Class1}
from live.backend.{module2} import {Class2}

async def test_{module1}_to_{module2}_integration():
    """Test Task XX → Task YY integration"""
    upstream = {Class1}()
    downstream = {Class2}()

    # Generate test data
    input_data = await upstream.generate()

    # Process through pipeline
    output_data = downstream.process(input_data)

    # Validate integration
    assert output_data is not None
```

### 4. Coverage Marker Template
```python
@pytest.mark.cov
@pytest.mark.asyncio
async def test_{function_name}():
    """Test with coverage tracking"""
    pass
```

## Usage Patterns

### Pattern 1: New Module
```
User: "Create tests for live/backend/tx_processor.py"

Skill:
1. Detect module type (sync/async)
2. Generate fixture
3. Create 3-5 core tests (RED phase)
4. Add integration test stub
5. Write to tests/test_tx_processor.py
```

### Pattern 2: Add Test to Existing File
```
User: "Add test for filter_round_amounts function"

Skill:
1. Read existing tests/test_tx_processor.py
2. Generate new test function
3. Append to file
```

### Pattern 3: Integration Test
```
User: "Create integration test for Task 01 → Task 02"

Skill:
1. Generate integration test in tests/integration/
2. Include both modules
3. Create end-to-end flow test
```

## Test Naming Conventions

| Pattern | Example | Use Case |
|---------|---------|----------|
| `test_{module}_*` | `test_zmq_connection` | Unit test |
| `test_{action}_*` | `test_parse_segwit_tx` | Action-based test |
| `test_{module1}_to_{module2}` | `test_zmq_to_processor` | Integration |
| `test_{edge_case}` | `test_empty_mempool` | Edge case |

## Fixtures Library

### Bitcoin Test Fixtures
```python
@pytest.fixture
def sample_tx_bytes():
    """Load sample Bitcoin transaction"""
    return load_fixture("fixtures/sample_tx.bin")

@pytest.fixture
def mempool_snapshot():
    """Load historical mempool data"""
    return load_fixture("fixtures/mempool_2024-10-15.json")
```

### Async Fixtures
```python
@pytest.fixture
async def running_zmq_listener():
    """ZMQ listener already connected"""
    listener = ZMQListener()
    await listener.connect()
    yield listener
    await listener.disconnect()
```

## Coverage Configuration

Auto-generate `pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    asyncio: async test
    integration: integration test
    slow: slow test (deselect with -m 'not slow')
addopts =
    --cov=live/backend
    --cov-report=term-missing
    --cov-report=html
    --cov-fail-under=80
```

## Output Format

**Generated test file**:
```python
"""
Tests for {module_name}
Task: {task_number}
Coverage target: >80%
"""
import pytest
from live.backend.{module} import {ClassName}

# Fixtures
@pytest.fixture
def {fixture_name}():
    """...\"\"\"
    pass

# Unit Tests (RED phase - should fail initially)
def test_{feature_1}():
    """Test {description}"""
    assert False  # RED: Not implemented yet

def test_{feature_2}():
    """Test {description}"""
    assert False  # RED: Not implemented yet

# Integration Tests
async def test_integration():
    """Test module integration"""
    pass
```

## Automatic Invocation

**Triggers**:
- "generate tests for [module]"
- "create test file for [file]"
- "add test for [function]"
- "write integration test for [module1] and [module2]"

**Does NOT trigger**:
- Complex test logic design (use subagent)
- Full TDD enforcement (use tdd-guard subagent)
- Test debugging (use general debugging)
