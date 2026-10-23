"""
Collection rules for tests/validation.

Three modules here are operator scripts that happen to be named test_*.py: they take
CLI arguments, call bitcoin-cli against a synced node, read the production DuckDB
cache and load SOPS secrets from a sibling checkout. Under pytest their test_*
functions have required positional parameters (``date_str``, ``html_path``) that no
fixture provides, or they open files that exist only on the operator host, so
collection reports errors or failures that are not about the code under test.

They stay runnable by hand (see README.md, e.g. ``python tests/validation/<file> --all``)
and are excluded from collection. Compensating test in CI: tests/test_utxoracle_library.py
and tests/test_backward_compatibility.py exercise the library on fixtures.
TODO: move the three scripts to scripts/validation/ and rename them off test_*.py.
"""

collect_ignore = [
    "test_library_vs_duckdb.py",
    "test_library_direct_comparison.py",
    "test_october_validation.py",
]
