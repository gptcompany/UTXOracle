# UTXOracle Scripts

## utxoracle_batch.py

Batch processing wrapper for running UTXOracle on multiple dates in parallel.

### Usage

```bash
python3 utxoracle_batch.py <start_date> <end_date> [data_dir] [max_workers]
```

### Example

```bash
# Process 10 days with 12 parallel workers
python3 utxoracle_batch.py 2025/10/01 2025/10/10 /home/sam/.bitcoin 12
```

### Features

- Parallel processing with configurable workers
- Date range generation
- Progress tracking
- Error handling
- HTML summary report generation

### Output

- Individual HTML files: `UTXOracle_YYYY-MM-DD.html`
- Summary report: `batch_summary.html`

### Dependencies

Calls the main UTXOracle.py script located in repository root.
