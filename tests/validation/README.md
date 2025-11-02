# Validation Tests

This directory contains critical validation tests that verify the UTXOracle_library.py implementation matches the reference UTXOracle.py exactly.

## Test Files

### test_library_direct_comparison.py
**Purpose**: Direct comparison between library and current UTXOracle.py reference

**Usage**:
```bash
python3 tests/validation/test_library_direct_comparison.py --date 2025-10-15
python3 tests/validation/test_library_direct_comparison.py --samples 5  # Random dates
```

**What it does**:
1. Parses HTML files to extract block ranges
2. Fetches same blocks from Bitcoin Core RPC
3. Runs both UTXOracle.py and library on identical data
4. Compares results

**Expected**: <0.01% difference (effectively identical)

---

### test_library_vs_duckdb.py
**Purpose**: Comprehensive validation against historical data stored in DuckDB

**Usage**:
```bash
python3 tests/validation/test_library_vs_duckdb.py --daily --samples 10
python3 tests/validation/test_library_vs_duckdb.py --daily --samples 50  # Full validation
```

**What it does**:
1. Fetches random dates from DuckDB price_analysis table
2. Extracts block ranges from corresponding HTML files
3. Fetches transactions from Bitcoin Core
4. Compares library results vs DuckDB stored prices

**Note**: DuckDB prices may come from older algorithm versions, so small differences are expected

---

### test_october_validation.py
**Purpose**: Validate library matches reference across multiple October 2025 dates

**Usage**:
```bash
python3 tests/validation/test_october_validation.py
```

**What it does**:
1. Tests 5 random October dates
2. For each date:
   - Runs current UTXOracle.py
   - Fetches same blocks
   - Runs library
   - Compares results
3. Reports perfect matches (<$1 difference)

**Expected**: 5/5 perfect matches

---

## Critical Discovery (Nov 2, 2025)

All validation tests confirm a critical finding: The reference implementation (UTXOracle.py) has a logic bug where the convergence loop **never executes**:

```python
# UTXOracle.py lines 1328-1330
avs = set()
avs.add(central_price)           # Adds to set
while central_price not in avs:  # ← FALSE immediately!
    # Loop body NEVER runs
```

The library correctly implements what the reference ACTUALLY does (single call to find_central_output), not what it appears it should do (iterative convergence).

### Validation Results

**Oct 15, 2025**:
- Reference: $111,652
- Library:   $111,652
- Difference: **0.00%**

**5 Random October Dates** (Oct 24, 23, 01, 25, 09):
- **5/5 Perfect matches** (<$1 difference)
- Average difference: $0.67 (0.0006%)
- Total transactions tested: 2,343,533

## Running All Validation Tests

```bash
# Quick validation (1 date)
python3 tests/validation/test_library_direct_comparison.py --date 2025-10-15

# Medium validation (5 October dates)
python3 tests/validation/test_october_validation.py

# Comprehensive validation (10 random dates)
python3 tests/validation/test_library_vs_duckdb.py --daily --samples 10
```

## Success Criteria

- **Direct comparison**: <0.01% average difference
- **October validation**: 5/5 perfect matches
- **DuckDB validation**: ~0.02% average difference (due to historical version differences)

## Important Notes

1. **DO NOT** attempt to "fix" the convergence bug in the library - this would break compatibility
2. If you want to improve the algorithm, create a new version (v2) instead
3. Always validate against current UTXOracle.py, not stale HTML files
4. Historical HTML files may show different prices if generated with older algorithm versions

## See Also

- `UTXOracle_library.py` - `_iterate_convergence()` method has detailed documentation
- Commit `6d19f7b` - Initial implementation with bug discovery
- Commit `dc9880f` - Phase 8 completion documentation
