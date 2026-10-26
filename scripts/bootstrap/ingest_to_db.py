import csv
import asyncio
import sys
from api.questdb_repository import (
    ConcurrentRefreshError,
    OldCopyCleanupError,
    QuestDBRepository,
)

# Exit codes: 0 ingested; 1 failed or concurrent refresh; 5 swap ok, cleanup failed.
EXIT_CLEANUP_FAILED = 5


async def ingest() -> int:
    repo = QuestDBRepository()
    await repo.initialize()

    rows = []
    with open("data/exchange_addresses.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    "address": row["address"],
                    "cluster_id": row["exchange_name"],
                    "label": row["type"],
                }
            )

    try:
        ok = await repo.save_address_clusters_bulk(rows)
    except ConcurrentRefreshError:
        print("❌ Another address_clusters refresh is running")
        return 1
    except OldCopyCleanupError as e:
        print(f"⚠️ Ingested to DB, but {e}")
        return EXIT_CLEANUP_FAILED
    if ok:
        print("✅ Ingested to DB")
        return 0
    print("❌ Ingestion failed")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(ingest()))
