import csv
import logging
from pydantic import BaseModel, Field, field_validator
from typing import Dict, List

logger = logging.getLogger(__name__)

class ExchangeAddress(BaseModel):
    address: str = Field(..., min_length=25, max_length=62)
    exchange_name: str

    @field_validator("address")
    @classmethod
    def validate_btc_addr(cls, v: str) -> str:
        # Basic validation (could be expanded)
        if not v.isalnum():
            raise ValueError("Invalid address characters")
        return v

def load_exchange_addresses(path: str) -> Dict[str, str]:
    addresses = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for line_num, row in enumerate(reader, start=2):
                try:
                    ea = ExchangeAddress(address=row["address"], exchange_name=row["exchange_name"])
                    addresses[ea.address] = ea.exchange_name
                except Exception as e:
                    logger.warning(f"Skipping invalid address at line {line_num}: {e}")
        return addresses
    except Exception as e:
        logger.error(f"Critical failure loading exchange addresses: {e}")
        return {}
