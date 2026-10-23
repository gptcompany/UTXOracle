"""Predicates on secret values, importable without loading the API configuration."""

from typing import Optional

# SOPS dotenv values and dotenvx values that were never decrypted.
ENCRYPTED_PREFIXES = ("ENC[", "encrypted:")


def is_encrypted(value: Optional[str]) -> bool:
    return bool(value) and str(value).startswith(ENCRYPTED_PREFIXES)
