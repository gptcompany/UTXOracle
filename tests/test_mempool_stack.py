"""Deployment contract for the mempool.space + electrs stack on the Dell; run in CI only.

The electrs healthcheck window is derived from measured boot timings (scripts/mempool-stack/boot-timing.json),
not chosen: the test recomputes it, and first checks the formula against the failure observed on 2026-11-17.
"""

import configparser
import json
import math
import unittest
from datetime import datetime
from pathlib import Path

import jsonschema
import yaml

STACK = Path(__file__).resolve().parents[1] / "scripts" / "mempool-stack"

TIMING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "measured_on",
        "formula",
        "calibration",
        "probe_duration_s",
        "boots",
    ],
    "properties": {
        "schema_version": {"const": 1},
        "measured_on": {"type": "string"},
        "formula": {"type": "string"},
        "calibration": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "what",
                "start_period_s",
                "interval_s",
                "retries",
                "observed_unhealthy_s",
                "source",
            ],
            "properties": {
                "what": {"type": "string"},
                "start_period_s": {"type": "number"},
                "interval_s": {"type": "number", "exclusiveMinimum": 0},
                "retries": {"type": "integer", "minimum": 1},
                "observed_unhealthy_s": {"type": "number"},
                "source": {"type": "string"},
            },
        },
        "probe_duration_s": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "number", "exclusiveMinimum": 0},
        },
        "boots": {
            "type": "array",
            "minItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "electrs_start_utc",
                    "bitcoind_ready_utc",
                    "rest_ready_s",
                    "source",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "electrs_start_utc": {"type": "string"},
                    "bitcoind_ready_utc": {"type": "string"},
                    "rest_ready_s": {"type": ["number", "null"]},
                    "source": {"type": "string"},
                },
            },
        },
    },
}


def unhealthy_after(start_period: float, interval: float, retries: int) -> float:
    """Docker counts failed probes only from the first one at or after start_period; probe k runs at k*interval."""
    return (math.ceil(start_period / interval) + retries - 1) * interval


def seconds(text: str) -> float:
    assert text.endswith("s"), text
    return float(text[:-1])


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def load_timing() -> dict:
    document = json.loads((STACK / "boot-timing.json").read_text())
    jsonschema.validate(document, TIMING_SCHEMA)
    return document


def derive(timing: dict) -> tuple[int, int, float]:
    """(start_period_s, retries, boot window B) from the measured boots."""
    interval = timing["calibration"]["interval_s"]
    warmups, catchups = [], []
    for boot in timing["boots"]:
        warmup = (
            utc(boot["bitcoind_ready_utc"]) - utc(boot["electrs_start_utc"])
        ).total_seconds()
        warmups.append(warmup)
        if boot["rest_ready_s"] is not None:
            catchups.append(boot["rest_ready_s"] - warmup)
    window = max(warmups) + max(catchups)
    start_period = math.ceil(max(warmups))
    retries = math.ceil(window / interval) - math.ceil(start_period / interval) + 1
    return start_period, retries, window


class ElectrsHealthcheckDerivation(unittest.TestCase):
    def test_formula_reproduces_the_observed_failure(self):
        c = load_timing()["calibration"]
        got = unhealthy_after(c["start_period_s"], c["interval_s"], c["retries"])
        self.assertLessEqual(abs(got - c["observed_unhealthy_s"]), 1.0)

    def test_compose_healthcheck_is_the_derived_one(self):
        timing = load_timing()
        start_period, retries, window = derive(timing)
        interval = timing["calibration"]["interval_s"]
        health = load_compose()["services"]["electrs"]["healthcheck"]
        self.assertEqual(seconds(health["start_period"]), start_period)
        self.assertEqual(health["retries"], retries)
        self.assertEqual(seconds(health["interval"]), interval)
        self.assertGreaterEqual(
            unhealthy_after(start_period, interval, retries), window
        )
        # timeout is a limit on a hung probe: below the interval and far above every measured probe.
        self.assertLess(seconds(health["timeout"]), interval)
        self.assertGreater(
            seconds(health["timeout"]), 10 * max(timing["probe_duration_s"])
        )


def load_compose() -> dict:
    return yaml.safe_load((STACK / "docker-compose.yml").read_text())


class ComposeContract(unittest.TestCase):
    def test_services_and_dependency_gates(self):
        services = load_compose()["services"]
        self.assertEqual(set(services), {"electrs", "db", "api", "web"})
        self.assertEqual(
            services["api"]["depends_on"],
            {
                "db": {"condition": "service_healthy"},
                "electrs": {"condition": "service_healthy"},
            },
        )
        self.assertEqual(services["electrs"]["network_mode"], "host")
        self.assertEqual(services["electrs"]["healthcheck"]["test"][0], "CMD-SHELL")

    def test_credentials_are_whole_variable_references(self):
        """No literal secret in the file: every credential value is ${NAME} (the values live in the host .env)."""
        services = load_compose()["services"]
        expected = {
            ("db", "MYSQL_PASSWORD"): "${MYSQL_PASSWORD}",
            ("db", "MYSQL_ROOT_PASSWORD"): "${MYSQL_ROOT_PASSWORD}",
            ("api", "DATABASE_PASSWORD"): "${MYSQL_PASSWORD}",
            ("api", "CORE_RPC_PASSWORD"): "${BTC_RPC_PASSWORD}",
        }
        for (service, key), value in expected.items():
            self.assertEqual(
                services[service]["environment"][key], value, (service, key)
            )
        command = services["electrs"]["command"]
        self.assertEqual(
            command[command.index("--cookie") + 1], "bitcoinrpc:${BTC_RPC_PASSWORD}"
        )
        for name, service in services.items():
            env = service.get("environment") or {}
            if isinstance(env, list):  # electrs: ["KEY=value"] form
                env = dict(entry.split("=", 1) for entry in env)
            for key, value in env.items():
                if "PASSWORD" in key:
                    self.assertEqual(value, expected[(name, key)], (name, key))


class UnitContract(unittest.TestCase):
    def unit(self) -> configparser.ConfigParser:
        unit = configparser.ConfigParser(interpolation=None, strict=False)
        unit.read_string((STACK / "mempool-stack.service").read_text())
        return unit

    def test_oneshot_compose_up_without_wait(self):
        """`up -d` already blocks on the api depends_on (electrs healthy); --wait would add a second, identical
        gate on the same healthcheck, so the unit stays as installed and the window lives in the healthcheck."""
        service = self.unit()["Service"]
        self.assertEqual(service["Type"], "oneshot")
        self.assertEqual(service["ExecStart"], "/usr/bin/docker compose up -d")
        self.assertEqual(service["ExecStop"], "/usr/bin/docker compose down")
        self.assertEqual(service["TimeoutStartSec"], "0")
        self.assertEqual(
            service["WorkingDirectory"], "/data/4TB/prod/apps/mempool-stack"
        )

    def test_unit_orders_after_bitcoind(self):
        unit = self.unit()
        self.assertIn("bitcoind.service", unit["Unit"]["Requires"].split())
        self.assertIn("bitcoind.service", unit["Unit"]["After"].split())


if __name__ == "__main__":
    unittest.main()
