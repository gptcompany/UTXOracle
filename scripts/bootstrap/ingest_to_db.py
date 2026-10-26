import csv
import asyncio
import sys
from api.questdb_repository import QuestDBRepository, refresh_exit_status

# Exit codes: 0 ingested; 1 failed or concurrent refresh; 5 swap ok, cleanup failed;
# 6 the refresh state is lost or unobservable: no address_clusters and no _old copy after
# a swap, or the tables could not be observed or restored (the ERROR has the command).


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
    except Exception as e:
        # the exit code is decided on the whole exception chain
        status = refresh_exit_status(e)
        if status is None:
            raise
        code, message = status
        print(f"⚠️ Ingested to DB, but {message}" if code == 5 else f"❌ {message}")
        return code
    if ok:
        print("✅ Ingested to DB")
        return 0
    print("❌ Ingestion failed")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(ingest()))
