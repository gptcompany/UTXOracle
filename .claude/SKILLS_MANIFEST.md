# Skills Manifest

| Skill | Description | Token Savings |
|-------|-------------|---------------|
| `pytest-test-generator` | Generate pytest tests for Bitcoin price oracle components (mempool clustering, UTXO tracking, statistical estimation). Creates fixtures for blockchain data, transaction parsing, and histogram analysis with real BRK/Bitcoin Core integration. | 83% |
| `pydantic-model-generator` | Auto-generate Pydantic models for Bitcoin data structures (transactions, UTXOs, price estimates, histogram bins). Includes Bitcoin-specific validators for satoshi amounts, script types (P2PKH/P2WPKH/P2TR), and confidence scores. | 75% |
| `github-workflow` | Standardized PR/issue templates for UTXOracle feature development. Auto-fills spec status (007-020), Bitcoin Core integration details, and statistical validation results with oracle-specific checklists. | 79% |
| `bitcoin-rpc-connector` | Generate Bitcoin Core RPC connection code with cookie authentication, BRK integration, and ZMQ subscription setup. Optimized for UTXOracle's privacy-first architecture (no external price feeds). | ~70% |
