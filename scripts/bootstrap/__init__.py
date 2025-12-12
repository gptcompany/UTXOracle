"""Bootstrap utilities for UTXO lifecycle data.

This module provides fast bootstrap of UTXO lifecycle data using:
- Tier 1: bitcoin-utxo-dump (chainstate) for current UTXOs
- Tier 2: rpc-v3 (incremental) for spent UTXOs

Architecture: See docs/ARCHITECTURE.md section "UTXO Lifecycle Bootstrap Architecture"
"""
