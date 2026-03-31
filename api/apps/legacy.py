"""Explicit legacy application entrypoint.

The legacy surface still reuses the historical mixed app until spec-041 finishes
the full router split. Production services must not use this module.
"""

from api.main import app
