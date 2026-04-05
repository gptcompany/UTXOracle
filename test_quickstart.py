import asyncio
from datetime import date
from scripts.integrations.rbn_fetcher import RBNFetcher
from scripts.integrations.rbn_validator import ValidationService

async def main():
    try:
        fetcher = RBNFetcher()
        # Mocking fetcher if there is no token, but actually the fetcher requires a token.
        # Let's see if the code compiles and initializes correctly.
        data = await fetcher.fetch_metric(
            metric_id="mvrv_z",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31)
        )
        validator = ValidationService(fetcher)
        report = await validator.validate_metric(
            metric_id="mvrv_z",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            tolerance_pct=1.0
        )
        print(f"Match rate: {report.match_rate_pct:.1f}%")
        print(f"Avg deviation: {report.avg_deviation_pct:.2f}%")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
