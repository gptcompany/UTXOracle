# Task 02: Transaction Processor Module

**Assigned Agent**: `general-purpose`

**Duration**: 2-3 weeks

**Dependencies**: Task 01 (Bitcoin Interface)

---

## Objective

Parse raw mempool transactions, apply UTXOracle filters, extract output amounts, and handle mempool-specific events (RBF, drops).

---

## Requirements

### Functional
1. Deserialize raw Bitcoin transaction bytes (legacy + SegWit)
2. Apply UTXOracle filters (≤5 inputs, 2 outputs, no coinbase, etc.)
3. Extract BTC amounts from valid outputs
4. Compute txid (for tracking)
5. Handle RBF (Replace-By-Fee) transactions
6. Detect transaction drops on new blocks

### Non-Functional
1. **Throughput**: Process 1000 tx/sec sustained
2. **Accuracy**: 100% match with UTXOracle.py filter logic
3. **Memory**: <100MB for 50k active mempool tx
4. **Dependencies**: Pure Python (reuse UTXOracle.py parsing functions)

---

## Implementation Details

### File Structure
```
live/backend/
├── tx_processor.py      # Main implementation
├── bitcoin_parser.py    # Binary parsing utilities (from UTXOracle.py)
└── mempool_state.py     # Mempool state tracker
```

### Core Interface

```python
# live/backend/tx_processor.py

from typing import Optional, List
from dataclasses import dataclass
from .models import RawTransaction
from .bitcoin_parser import compute_txid, parse_transaction

@dataclass
class ProcessedTransaction:
    """
    Filtered transaction ready for analysis.

    Black Box Contract:
    - Only transactions passing UTXOracle filters
    - Contains BTC amounts in range [1e-5, 1e5]
    """
    txid: str                    # Hex transaction ID
    amounts: List[float]         # BTC amounts (filtered outputs)
    timestamp: float             # When received from ZMQ
    fee_rate: Optional[float]    # Sat/vB (if inputs resolved)
    input_count: int
    output_count: int

class TransactionProcessor:
    """
    Applies UTXOracle filters to raw mempool transactions.

    Filter Rules (from UTXOracle.py Step 6):
    - ≤5 inputs
    - Exactly 2 outputs
    - Not coinbase
    - No OP_RETURN
    - No witness >500 bytes
    - Amounts in range [1e-5, 1e5] BTC
    """

    def __init__(self):
        self.processed_count = 0
        self.filtered_count = 0

    def process(self, raw_tx: RawTransaction) -> Optional[ProcessedTransaction]:
        """
        Parse and filter transaction.

        Args:
            raw_tx: Raw transaction from ZMQ listener

        Returns:
            ProcessedTransaction if passes filters, None otherwise
        """
        pass

    def apply_filters(self, tx) -> bool:
        """
        Apply UTXOracle filters.

        Returns True if transaction should be kept.
        """
        pass

# Public API
def process_mempool_transaction(raw_tx: RawTransaction) -> Optional[ProcessedTransaction]:
    """
    Main entry point for transaction processing.

    Example:
        tx = process_mempool_transaction(raw_tx)
        if tx:
            print(f"Valid tx: {tx.txid}, amounts: {tx.amounts}")
    """
    processor = TransactionProcessor()
    return processor.process(raw_tx)
```

### Bitcoin Binary Parser

```python
# live/backend/bitcoin_parser.py

"""
Binary parsing utilities extracted from UTXOracle.py Step 6.

These functions are IDENTICAL to UTXOracle.py to ensure
consensus-compatible price calculation.
"""

import struct
import hashlib
from io import BytesIO

def read_varint(stream: BytesIO) -> int:
    """
    Read variable-length integer.

    Copied from UTXOracle.py lines 693-706
    """
    i = stream.read(1)
    if not i:
        return 0
    i = i[0]
    if i < 0xfd:
        return i
    elif i == 0xfd:
        return struct.unpack("<H", stream.read(2))[0]
    elif i == 0xfe:
        return struct.unpack("<I", stream.read(4))[0]
    else:
        return struct.unpack("<Q", stream.read(8))[0]

def encode_varint(i: int) -> bytes:
    """
    Encode integer to variable-length bytes.

    Copied from UTXOracle.py lines 710-719
    """
    assert i >= 0
    if i < 0xfd:
        return i.to_bytes(1, 'little')
    elif i <= 0xffff:
        return b'\xfd' + i.to_bytes(2, 'little')
    elif i <= 0xffffffff:
        return b'\xfe' + i.to_bytes(4, 'little')
    else:
        return b'\xff' + i.to_bytes(8, 'little')

def compute_txid(raw_tx_bytes: bytes) -> bytes:
    """
    Calculate transaction ID.

    Copied from UTXOracle.py lines 722-773

    Handles both legacy and SegWit transactions by stripping
    witness data before hashing.
    """
    # [Full implementation from UTXOracle.py]
    pass

def parse_transaction(raw_tx_bytes: bytes) -> dict:
    """
    Parse raw transaction into structured format.

    Returns:
        {
            'version': int,
            'inputs': List[dict],
            'outputs': List[dict],
            'locktime': int,
            'is_segwit': bool
        }
    """
    pass
```

### Mempool State Tracker

```python
# live/backend/mempool_state.py

from typing import Dict, Set
from .tx_processor import ProcessedTransaction

class MempoolState:
    """
    Tracks active mempool transactions and handles RBF/drops.

    Black Box Contract:
    - Input: ProcessedTransaction events, block events
    - Output: Current set of active mempool tx
    - Side Effects: Maintains in-memory state
    """

    def __init__(self):
        self.active_txs: Dict[str, ProcessedTransaction] = {}
        self.todays_txids: Set[str] = set()  # For same-day filter

    def add_transaction(self, tx: ProcessedTransaction) -> bool:
        """
        Add transaction to mempool state.

        Returns:
            True if new tx, False if RBF replacement
        """
        is_new = tx.txid not in self.active_txs
        self.active_txs[tx.txid] = tx
        self.todays_txids.add(tx.txid)
        return is_new

    def remove_transactions(self, txids: List[str]) -> int:
        """
        Remove confirmed transactions (on new block).

        Returns:
            Number of transactions removed
        """
        count = 0
        for txid in txids:
            if txid in self.active_txs:
                del self.active_txs[txid]
                count += 1
        return count

    def get_active_transactions(self) -> List[ProcessedTransaction]:
        """Return all active mempool transactions"""
        return list(self.active_txs.values())

    def size(self) -> int:
        """Return number of active transactions"""
        return len(self.active_txs)
```

---

## Filter Logic (from UTXOracle.py)

### UTXOracle.py Reference (Lines 862-873)

```python
# From UTXOracle.py Step 6
if (input_count <= 5 and output_count == 2 and not is_coinbase and
    not has_op_return and not witness_exceeds and not is_same_day_tx):
    for amount in output_values:
        # Add to histogram
```

### Mempool Modifications

**Remove**: `is_same_day_tx` filter (not applicable to pending tx)

**Keep**:
- `input_count <= 5`
- `output_count == 2`
- `not is_coinbase`
- `not has_op_return`
- `not witness_exceeds` (>500 bytes)
- Amount range `1e-5 < value_btc < 1e5`

---

## RBF Handling

### Replace-By-Fee Detection

```python
def is_rbf(tx: dict) -> bool:
    """
    Check if transaction signals RBF (BIP 125).

    A transaction signals RBF if any input has sequence < 0xfffffffe
    """
    for inp in tx['inputs']:
        if inp['sequence'] < 0xfffffffe:
            return True
    return False

# When processing RBF:
if is_rbf(tx):
    # Replace old tx with new one
    mempool_state.add_transaction(processed_tx)  # Overwrites old
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_tx_processor.py

import pytest
from live.backend.tx_processor import TransactionProcessor, process_mempool_transaction
from live.backend.models import RawTransaction

def test_filter_valid_transaction():
    """Test that valid tx passes filters"""
    # Sample valid tx (2 inputs, 2 outputs, no OP_RETURN)
    raw_bytes = bytes.fromhex("0100000002...")  # Valid tx hex
    raw_tx = RawTransaction(raw_bytes, 1234567890.0, 'rawtx')

    result = process_mempool_transaction(raw_tx)

    assert result is not None
    assert len(result.amounts) > 0
    assert result.input_count <= 5
    assert result.output_count == 2

def test_filter_coinbase():
    """Test that coinbase tx is filtered out"""
    # Coinbase tx (input prevout = 0x00...00)
    raw_bytes = bytes.fromhex("01000000010000...")
    raw_tx = RawTransaction(raw_bytes, 1234567890.0, 'rawtx')

    result = process_mempool_transaction(raw_tx)

    assert result is None  # Filtered out

def test_filter_too_many_inputs():
    """Test that tx with >5 inputs is filtered"""
    # Construct tx with 6 inputs
    raw_bytes = construct_tx(inputs=6, outputs=2)
    raw_tx = RawTransaction(raw_bytes, 1234567890.0, 'rawtx')

    result = process_mempool_transaction(raw_tx)

    assert result is None

def test_rbf_replacement():
    """Test that RBF transaction replaces old one"""
    state = MempoolState()

    # Original tx
    tx1 = ProcessedTransaction("abc123", [0.01], 1000.0, 10.0, 2, 2)
    state.add_transaction(tx1)

    # RBF replacement (same txid, higher fee)
    tx2 = ProcessedTransaction("abc123", [0.01], 1001.0, 20.0, 2, 2)
    is_new = state.add_transaction(tx2)

    assert is_new == False  # Replacement, not new
    assert state.size() == 1
    assert state.active_txs["abc123"].fee_rate == 20.0  # Updated
```

### Integration Tests

```python
# tests/integration/test_tx_processing_pipeline.py

@pytest.mark.asyncio
async def test_full_pipeline():
    """Test ZMQ → Parser → Filter pipeline"""
    async for raw_tx in stream_mempool_transactions():
        processed = process_mempool_transaction(raw_tx)

        if processed:
            assert processed.txid is not None
            assert len(processed.amounts) > 0

        # Test 100 transactions
        count += 1
        if count >= 100:
            break
```

---

## Performance Benchmarks

```python
# tests/benchmark_tx_processor.py

import time
from live.backend.tx_processor import process_mempool_transaction

def benchmark_throughput():
    """Measure tx/sec processing rate"""
    # Load 10k sample transactions
    txs = load_sample_transactions(10000)

    start = time.time()
    for raw_tx in txs:
        process_mempool_transaction(raw_tx)
    elapsed = time.time() - start

    throughput = len(txs) / elapsed
    print(f"Throughput: {throughput:.0f} tx/sec")

    assert throughput > 1000  # Must exceed 1k tx/sec
```

**Target**: >1000 tx/sec on modern CPU

---

## Edge Cases

1. **Malformed transactions**: Skip with warning log
2. **Empty mempool**: Return None, no errors
3. **Duplicate txid**: RBF replacement (update existing)
4. **SegWit v2+ (Taproot)**: Parse correctly (test with sample)
5. **Zero-fee transactions**: Accept (fee_rate = None)

---

## Deliverables

- [ ] `live/backend/tx_processor.py` - Main processor
- [ ] `live/backend/bitcoin_parser.py` - Parsing utilities
- [ ] `live/backend/mempool_state.py` - State tracker
- [ ] `tests/test_tx_processor.py` - Unit tests (>90% coverage)
- [ ] `tests/benchmark_tx_processor.py` - Performance tests
- [ ] Sample transactions for testing (`tests/fixtures/sample_txs.json`)

---

## Acceptance Criteria

✅ **Must Have**:
1. Parses legacy + SegWit transactions correctly
2. Applies all UTXOracle filters accurately
3. Handles RBF replacements
4. Processes >1000 tx/sec
5. Unit tests >90% coverage

✅ **Should Have**:
1. Graceful handling of malformed tx
2. Logging for filtered transactions (debug level)
3. Metrics (processed count, filtered count)

---

## Completion Checklist

- [ ] Code written and tested
- [ ] Benchmarks pass (>1k tx/sec)
- [ ] Integration test with Task 01
- [ ] Code review
- [ ] Merge to feature branch

---

**Status**: NOT STARTED
**Dependencies**: Task 01 complete
**Target Completion**: __________ (3 weeks from Task 01 completion)
