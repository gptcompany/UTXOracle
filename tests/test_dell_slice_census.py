"""Census gate (#1498): every service of the Dell composes joins a versioned role slice (gbg-agents dell-*.slice)."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SLICES = {"dell-trading-critical.slice", "dell-services.slice", "dell-batch.slice"}


@pytest.mark.parametrize("name", ["docker-compose.live.yml", "docker-compose.brk.yml"])
def test_every_service_has_a_role_slice(name: str) -> None:
    services = yaml.safe_load((ROOT / name).read_text())["services"]
    missing = {
        svc: cfg.get("cgroup_parent")
        for svc, cfg in services.items()
        if cfg.get("cgroup_parent") not in SLICES
    }
    assert not missing, missing


def test_batch_services_are_in_the_batch_slice() -> None:
    live = yaml.safe_load((ROOT / "docker-compose.live.yml").read_text())["services"]
    assert live["utxoracle-data-updater"]["cgroup_parent"] == "dell-batch.slice"
