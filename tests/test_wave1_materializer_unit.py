"""The live Wave 1 materializer unit is bounded in memory and never spills to swap (issue #98)."""

from __future__ import annotations

import configparser
from pathlib import Path

from scripts.live import wave1_materializer_runtime as runtime

UNIT = (
    Path(__file__).resolve().parent.parent / "utxoracle-live-wave1-materializer.service"
)


def test_unit_forbids_swap():
    """Unset MemorySwapMax let the unit park 6.5G in swap and starve the host's other services."""
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read(UNIT)
    assert parser["Service"]["MemorySwapMax"] == "0"


def test_rss_mib_reads_the_resident_set_of_this_process():
    assert runtime._rss_mib() > 0
