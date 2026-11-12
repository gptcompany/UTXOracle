"""Deployment contract for the existing Dell brk container; run in CI only."""
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
                        "--bitcoindir", "/bitcoin", "--blocksdir", "/bitcoin/blocks",
                        "--brkdir", "/home/brk/.brk", "--brkport", "7070",
                        "--rpcconnect", "127.0.0.1",
                        "--rpcuser", "${BTC_RPC_USER:?external env required}",
                        "--rpcpassword", "${BTC_RPC_PASSWORD:?external env required}",
                    ],
                }
            },
        }
        with (ROOT / "docker-compose.brk.yml").open() as stream:
            document = yaml.safe_load(stream)
        # A closed constant schema rejects unknown fields and credential literals too.
        jsonschema.validate(document, {"const": expected})


if __name__ == "__main__":
    unittest.main()
