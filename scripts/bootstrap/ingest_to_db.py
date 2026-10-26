import csv
import asyncio
import sys
from api.questdb_repository import QuestDBRepository


async def ingest() -> bool:
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

    if await repo.save_address_clusters_bulk(rows):
        print("✅ Ingested to DB")
        return True
    print("❌ Ingestion failed")
    return False


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(ingest()) else 1)
