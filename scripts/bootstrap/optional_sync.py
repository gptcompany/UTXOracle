"""The optional QuestDB sync step of the clustering bootstraps.

Deliberately light: nothing from `api.*` (or DuckDB) is imported at module level, because
`api.config` raises ValueError when JWT_SECRET is missing. The heavy import of the sync
module happens inside `run_optional_sync`, in a `try` that holds nothing else, so a
bootstrap that has just finished hours of clustering cannot die at its optional last step.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

EXIT_CLEANUP_FAILED = 5
EXIT_CLUSTERS_LOST = 6


def run_optional_sync(duckdb_path: str, batch_size: int = 100000) -> int:
    """Run the sync and return the exit code the bootstrap must end with after its own
    summary: 5 or 6 when the sync classified a problem to act on, else 0 (a plain failure,
    or a sync that cannot even be loaded, is a warning: DuckDB stays the source of truth)."""
    print("\n" + "=" * 70)
    print("SYNCING CLUSTERS TO QUESTDB SERVING PLANE")
    print("=" * 70)
    try:
        from scripts.bootstrap.sync_clusters_to_questdb import run_sync
    except Exception as exc:
        logger.warning("QuestDB sync unavailable, skipped: %s", exc)
        code = 1
    else:
        code = asyncio.run(run_sync(duckdb_path, batch_size))
    if code == 0:
        print("  ✅ QuestDB sync completed successfully.")
    elif code in (EXIT_CLEANUP_FAILED, EXIT_CLUSTERS_LOST):
        print(
            f"  ❌ QuestDB sync ended with exit code {code}: see the ERROR log above for the recovery command."
        )
        return code
    else:
        print("  ❌ QuestDB sync failed (see the log above).")
        print("  ⚠️  DuckDB analytical plane remains the source of truth.")
    return 0
