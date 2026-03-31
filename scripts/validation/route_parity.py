from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

PRICES_HISTORICAL_ROUTE_ID = "prices-historical"
DEFAULT_PRICES_HISTORICAL_TOLERANCES_PCT = {
    "utxoracle_price": 0.1,
    "mempool_price": 0.1,
    "diff_percent": 0.1,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _normalize_date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        if "T" in value:
            return value.split("T", 1)[0]
        if len(value) >= 10:
            return value[:10]
    raise ValueError(f"Cannot normalize date key from value: {value!r}")


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _normalize_payload(payload: Any, *, timestamp_field: str) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        normalized: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise TypeError("Parity payload lists must contain JSON objects")
            normalized.append(item)
        return normalized
    raise TypeError("Parity payload must be a JSON object or array of objects")


def _get_nested_value(payload: dict[str, Any], field_path: str) -> Any:
    current: Any = payload
    for part in field_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _relative_diff_percent(left: float, right: float) -> float:
    diff = abs(left - right)
    base = max(abs(left), abs(right), 1e-12)
    return (diff / base) * 100.0


def _align_series(
    questdb_payload: Any,
    baseline_payload: Any,
    *,
    timestamp_field: str,
) -> tuple[list[tuple[str, dict[str, Any], dict[str, Any]]], list[str]]:
    questdb_items = _normalize_payload(questdb_payload, timestamp_field=timestamp_field)
    baseline_items = _normalize_payload(baseline_payload, timestamp_field=timestamp_field)

    questdb_index = {
        str(item.get(timestamp_field, f"item_{index}")): item
        for index, item in enumerate(questdb_items)
    }
    baseline_index = {
        str(item.get(timestamp_field, f"item_{index}")): item
        for index, item in enumerate(baseline_items)
    }

    shared_keys = sorted(set(questdb_index) & set(baseline_index))
    missing_keys = sorted((set(questdb_index) ^ set(baseline_index)))
    aligned = [(key, questdb_index[key], baseline_index[key]) for key in shared_keys]
    return aligned, missing_keys


def normalize_prices_historical_payload(payload: Any) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    for item in _normalize_payload(payload, timestamp_field="timestamp"):
        timestamp = _first_present(item, "date", "timestamp")
        if timestamp is None:
            raise ValueError("prices-historical payload requires a timestamp or date field")
        normalized_items.append(
            {
                "date": _normalize_date_key(timestamp),
                "utxoracle_price": _coerce_float(_first_present(item, "utxoracle_price")),
                "mempool_price": _coerce_float(
                    _first_present(item, "mempool_price", "exchange_price", "mempool_exchange_price")
                ),
                "confidence": _coerce_float(_first_present(item, "confidence", "utxoracle_confidence")),
                "diff_amount": _coerce_float(
                    _first_present(item, "diff_amount", "price_difference")
                ),
                "diff_percent": _coerce_float(
                    _first_present(item, "diff_percent", "avg_pct_diff")
                ),
                "tx_count": item.get("tx_count"),
                "is_valid": item.get("is_valid"),
            }
        )
    return normalized_items


def load_prices_historical_baseline_from_duckdb(
    path: str | Path,
    *,
    days: int,
    as_of: date | str | None = None,
) -> list[dict[str, Any]]:
    import duckdb

    if days <= 0:
        raise ValueError("days must be > 0")

    conn = duckdb.connect(str(path), read_only=True)
    try:
        anchor_date = as_of
        if isinstance(anchor_date, str):
            anchor_date = date.fromisoformat(anchor_date)
        if anchor_date is None:
            result = conn.execute("SELECT max(date) FROM price_analysis").fetchone()
            anchor_date = result[0] if result else None
        if anchor_date is None:
            return []

        start_date = anchor_date - timedelta(days=days - 1)
        rows = conn.execute(
            """
            SELECT
                date,
                exchange_price,
                utxoracle_price,
                price_difference,
                avg_pct_diff,
                confidence,
                tx_count,
                is_valid
            FROM price_analysis
            WHERE date >= ? AND date <= ?
            ORDER BY date ASC
            """,
            [start_date, anchor_date],
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "date": _normalize_date_key(row[0]),
            "mempool_price": _coerce_float(row[1]),
            "utxoracle_price": _coerce_float(row[2]),
            "diff_amount": _coerce_float(row[3]),
            "diff_percent": _coerce_float(row[4]),
            "confidence": _coerce_float(row[5]),
            "tx_count": row[6],
            "is_valid": row[7],
        }
        for row in rows
    ]


def compare_prices_historical_payloads(
    *,
    questdb_payload: Any,
    duckdb_path: str | Path,
    lookback_days: int,
    dataset_id: str | None = None,
    allow_missing_baseline: bool = False,
    field_tolerances_pct: dict[str, float] | None = None,
    baseline_as_of: date | str | None = None,
) -> dict[str, Any]:
    normalized_payload = normalize_prices_historical_payload(questdb_payload)
    baseline_payload = load_prices_historical_baseline_from_duckdb(
        duckdb_path,
        days=lookback_days,
        as_of=baseline_as_of,
    )
    return compare_payloads(
        route_id=PRICES_HISTORICAL_ROUTE_ID,
        questdb_payload=normalized_payload,
        baseline_payload=baseline_payload,
        field_tolerances_pct=field_tolerances_pct or DEFAULT_PRICES_HISTORICAL_TOLERANCES_PCT,
        dataset_id=dataset_id,
        allow_missing_baseline=allow_missing_baseline,
        timestamp_field="date",
    )


def run_prices_historical_dual_read(
    *,
    questdb_payload: Any,
    duckdb_path: str | Path,
    lookback_days: int,
    dataset_id: str | None = None,
    divergence_log: str | Path | None = None,
    allow_missing_baseline: bool = False,
    field_tolerances_pct: dict[str, float] | None = None,
    baseline_as_of: date | str | None = None,
) -> dict[str, Any]:
    report = compare_prices_historical_payloads(
        questdb_payload=questdb_payload,
        duckdb_path=duckdb_path,
        lookback_days=lookback_days,
        dataset_id=dataset_id,
        allow_missing_baseline=allow_missing_baseline,
        field_tolerances_pct=field_tolerances_pct,
        baseline_as_of=baseline_as_of,
    )
    if divergence_log:
        append_dual_read_event(divergence_log, report)
    return report


def compare_payloads(
    *,
    route_id: str,
    questdb_payload: Any,
    baseline_payload: Any,
    field_tolerances_pct: dict[str, float],
    dataset_id: str | None = None,
    allow_missing_baseline: bool = False,
    timestamp_field: str = "timestamp",
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "route_id": route_id,
        "dataset_id": dataset_id,
        "timestamp_field": timestamp_field,
        "generated_at": _utc_now_iso(),
        "status": "pass",
        "sample_count": 0,
        "notes": [],
        "missing_keys": [],
        "failing_fields": [],
        "field_results": {},
    }

    if baseline_payload is None:
        report["status"] = "skipped" if allow_missing_baseline else "fail"
        report["notes"].append("baseline_missing")
        return report

    aligned, missing_keys = _align_series(
        questdb_payload,
        baseline_payload,
        timestamp_field=timestamp_field,
    )
    report["sample_count"] = len(aligned)
    report["missing_keys"] = missing_keys
    if missing_keys:
        report["notes"].append("key_mismatch")

    if not aligned:
        report["status"] = "skipped" if allow_missing_baseline else "fail"
        report["notes"].append("no_overlapping_samples")
        return report

    for field_path, tolerance_pct in field_tolerances_pct.items():
        diffs: list[float] = []
        missing_samples = 0
        for _, questdb_item, baseline_item in aligned:
            questdb_value = _get_nested_value(questdb_item, field_path)
            baseline_value = _get_nested_value(baseline_item, field_path)
            if questdb_value is None or baseline_value is None:
                missing_samples += 1
                continue
            if not isinstance(questdb_value, (int, float)) or not isinstance(
                baseline_value, (int, float)
            ):
                raise TypeError(f"Field '{field_path}' must resolve to numeric values")
            diffs.append(_relative_diff_percent(float(questdb_value), float(baseline_value)))

        if not diffs:
            result = {
                "status": "missing",
                "tolerance_pct": tolerance_pct,
                "sample_count": 0,
                "missing_samples": missing_samples,
                "max_diff_pct": None,
                "avg_diff_pct": None,
            }
            report["failing_fields"].append(field_path)
            report["status"] = "fail"
        else:
            max_diff_pct = max(diffs)
            avg_diff_pct = sum(diffs) / len(diffs)
            field_status = "pass" if max_diff_pct <= tolerance_pct else "fail"
            result = {
                "status": field_status,
                "tolerance_pct": tolerance_pct,
                "sample_count": len(diffs),
                "missing_samples": missing_samples,
                "max_diff_pct": round(max_diff_pct, 6),
                "avg_diff_pct": round(avg_diff_pct, 6),
            }
            if field_status == "fail":
                report["failing_fields"].append(field_path)
                report["status"] = "fail"

        report["field_results"][field_path] = result

    return report


def append_dual_read_event(path: str | Path, report: dict[str, Any]) -> None:
    status = str(report.get("status", "fail"))
    severity = {"pass": "info", "skipped": "warning"}.get(status, "error")
    event = {
        "timestamp": _utc_now_iso(),
        "route_id": report.get("route_id"),
        "dataset_id": report.get("dataset_id"),
        "status": status,
        "severity": severity,
        "sample_count": report.get("sample_count", 0),
        "failing_fields": report.get("failing_fields", []),
        "notes": report.get("notes", []),
    }
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _parse_field_tolerances(items: list[str]) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --field value '{item}'. Expected field=tolerance_pct")
        field, value = item.split("=", 1)
        parsed[field.strip()] = float(value)
    if not parsed:
        raise ValueError("At least one --field field=tolerance_pct pair is required")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare QuestDB-backed route payloads against research baselines",
    )
    parser.add_argument(
        "--route-family",
        choices=[PRICES_HISTORICAL_ROUTE_ID],
        help="Use a retained route family with built-in dataset loaders and default tolerances",
    )
    parser.add_argument("--route-id", help="Stable route family id")
    parser.add_argument("--questdb", required=True, help="Path to QuestDB JSON payload")
    parser.add_argument("--baseline", help="Path to baseline JSON payload")
    parser.add_argument(
        "--baseline-duckdb",
        help="Path to DuckDB baseline database for route-family helpers",
    )
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        help="Field tolerance in the form field=tolerance_pct. May be repeated.",
    )
    parser.add_argument("--dataset-id", help="Optional dataset identifier")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Bounded lookback window for route-family helpers",
    )
    parser.add_argument(
        "--baseline-as-of",
        help="Optional baseline anchor date (YYYY-MM-DD). Defaults to the latest available day",
    )
    parser.add_argument("--output", help="Optional path to write the full report JSON")
    parser.add_argument(
        "--divergence-log",
        help="Optional JSONL path where a dual-read divergence summary event is appended",
    )
    parser.add_argument(
        "--allow-missing-baseline",
        action="store_true",
        help="Mark the result as skipped instead of failed when the baseline is missing",
    )
    parser.add_argument(
        "--timestamp-field",
        default="timestamp",
        help="Field used to align time-series samples",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.route_family == PRICES_HISTORICAL_ROUTE_ID:
        if not args.baseline_duckdb:
            raise ValueError("--baseline-duckdb is required for --route-family prices-historical")
        field_tolerances_pct = (
            _parse_field_tolerances(args.field)
            if args.field
            else DEFAULT_PRICES_HISTORICAL_TOLERANCES_PCT
        )
        report = run_prices_historical_dual_read(
            questdb_payload=_load_json(args.questdb),
            duckdb_path=args.baseline_duckdb,
            lookback_days=args.lookback_days,
            dataset_id=args.dataset_id,
            divergence_log=args.divergence_log,
            allow_missing_baseline=args.allow_missing_baseline,
            field_tolerances_pct=field_tolerances_pct,
            baseline_as_of=args.baseline_as_of,
        )
    else:
        if not args.route_id:
            raise ValueError("--route-id is required when --route-family is not provided")
        field_tolerances_pct = _parse_field_tolerances(args.field)
        questdb_payload = _load_json(args.questdb)
        baseline_payload = _load_json(args.baseline) if args.baseline else None

        report = compare_payloads(
            route_id=args.route_id,
            questdb_payload=questdb_payload,
            baseline_payload=baseline_payload,
            field_tolerances_pct=field_tolerances_pct,
            dataset_id=args.dataset_id,
            allow_missing_baseline=args.allow_missing_baseline,
            timestamp_field=args.timestamp_field,
        )

    serialized = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)

    if args.divergence_log and args.route_family != PRICES_HISTORICAL_ROUTE_ID:
        append_dual_read_event(args.divergence_log, report)

    return 0 if report["status"] in {"pass", "skipped"} else 1


if __name__ == "__main__":
    sys.exit(main())
