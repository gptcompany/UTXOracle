from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
    parser.add_argument("--route-id", required=True, help="Stable route family id")
    parser.add_argument("--questdb", required=True, help="Path to QuestDB JSON payload")
    parser.add_argument("--baseline", help="Path to baseline JSON payload")
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        help="Field tolerance in the form field=tolerance_pct. May be repeated.",
    )
    parser.add_argument("--dataset-id", help="Optional dataset identifier")
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

    if args.divergence_log:
        append_dual_read_event(args.divergence_log, report)

    return 0 if report["status"] in {"pass", "skipped"} else 1


if __name__ == "__main__":
    sys.exit(main())
