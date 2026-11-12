"""Deployment contract for the existing Dell brk container; run in CI only."""

import configparser
import unittest
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "brk@sha256:ca2e444a0598a5c0847642add4bd3f111ff3cc805b8d51aba10c0cfc2317c6c3"


class BrkComposeContract(unittest.TestCase):
    def test_pinned_image_memory_and_existing_runtime(self):
        expected = {
            "name": "brk",
            "services": {
                "brk": {
                    "image": IMAGE,
                    "pull_policy": "never",
                    "container_name": "brk",
                    "network_mode": "host",
                    "restart": "unless-stopped",
                    "mem_limit": "15g",
                    "memswap_limit": "15g",
                    "volumes": [
                        "${BITCOIN_DATA_DIR:-/data/cold/12TB/Bitcoin}:/bitcoin:ro",
                        "${BRK_DATA_DIR:-/data/4TB/brk-v0.3.6-data}:/home/brk/.brk",
                    ],
                    "command": [
                        "--bitcoindir",
                        "/bitcoin",
                        "--blocksdir",
                        "/bitcoin/blocks",
                        "--brkdir",
                        "/home/brk/.brk",
                        "--brkport",
                        "7070",
                        "--rpcconnect",
                        "127.0.0.1",
                        "--rpcuser",
                        "${BTC_RPC_USER:?external env required}",
                        "--rpcpassword",
                        "${BTC_RPC_PASSWORD:?external env required}",
                    ],
                }
            },
        }
        with (ROOT / "docker-compose.brk.yml").open() as stream:
            document = yaml.safe_load(stream)
        # A closed constant schema rejects unknown fields and credential literals too.
        jsonschema.validate(document, {"const": expected})


class BrkUnitContract(unittest.TestCase):
    def test_compose_stop_grace_matches_unit_timeout(self):
        unit = configparser.ConfigParser(interpolation=None, strict=False)
        unit.read_string((ROOT / "brk-stack.service").read_text())
        with (ROOT / "docker-compose.brk.yml").open() as stream:
            document = yaml.safe_load(stream)
        self.assertEqual(
            document["services"]["brk"].get("stop_grace_period"),
            f"{unit.getint('Service', 'TimeoutStopSec')}s",
        )

    def test_installed_boot_and_shutdown_guarantees(self):
        # Reuse the stdlib parser used by test_daily_analysis_timer.py.
        # Repeated Environment= is legal; these contract keys occur once.
        unit = configparser.ConfigParser(interpolation=None, strict=False)
        unit.optionxform = str
        unit.read_string((ROOT / "brk-stack.service").read_text())
        expected = {
            "Unit": {
                "Requires": "docker.service bitcoind.service",
                "After": "docker.service network-online.target bitcoind.service",
                "RequiresMountsFor": "/data/sata/1TB /data/cold/12TB /data/4TB",
            },
            "Service": {"TimeoutStartSec": "0", "TimeoutStopSec": "300"},
        }
        for section, directives in expected.items():
            for key, value in directives.items():
                with self.subTest(section=section, directive=key):
                    self.assertEqual(unit.get(section, key, fallback=None), value)


if __name__ == "__main__":
    unittest.main()
