#!/bin/bash
# Weekly exchange address scraper
# Run with: nohup ./run_weekly_scrape.sh &

cd /media/sam/1TB/UTXOracle
mkdir -p logs

echo "$(date): Starting exchange address scrape" >> logs/scrape_exchange.log
uv run python -m scripts.bootstrap.scrape_exchange_addresses --max-pages 50 >> logs/scrape_exchange.log 2>&1
echo "$(date): Scrape completed" >> logs/scrape_exchange.log
