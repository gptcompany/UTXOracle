import csv
import asyncio
from api.questdb_repository import QuestDBRepository

async def ingest():
    repo = QuestDBRepository()
    await repo.initialize()
    
    rows = []
    with open("data/exchange_addresses.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({"address": row["address"], "cluster_id": row["exchange_name"], "label": row["type"]})
            
    if await repo.save_address_clusters_bulk(rows):
        print("✅ Ingested to DB")
    else:
        print("❌ Ingestion failed")

if __name__ == "__main__":
    asyncio.run(ingest())
