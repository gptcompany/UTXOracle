#!/usr/bin/env python3
"""
Backup all UTXOracle database files before migration.

Creates timestamped copies of all .duckdb and .db files.
"""

import shutil
import json
from datetime import datetime
from pathlib import Path


# Database files to backup
DATABASE_FILES = {
    "utxo_lifecycle.duckdb": Path("data/utxo_lifecycle.duckdb"),
    "utxoracle.duckdb": Path("data/utxoracle.duckdb"),
    "utxoracle_cache.db": Path("data/utxoracle_cache.db"),
    "mempool_predictions.db": Path("data/mempool_predictions.db"),
    "nvme_utxoracle_cache.db": Path(
        "/media/sam/2TB-NVMe/prod/apps/utxoracle/data/utxoracle_cache.db"
    ),
}


def get_backup_dir() -> Path:
    """Create timestamped backup directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(f"data/backups/pre_migration_{timestamp}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def get_file_info(path: Path) -> dict:
    """Get file size and basic info."""
    if not path.exists():
        return {"exists": False, "size_bytes": 0, "size_human": "N/A"}

    size = path.stat().st_size
    if size > 1_000_000_000:
        size_human = f"{size / 1_000_000_000:.2f} GB"
    elif size > 1_000_000:
        size_human = f"{size / 1_000_000:.2f} MB"
    elif size > 1_000:
        size_human = f"{size / 1_000:.2f} KB"
    else:
        size_human = f"{size} B"

    return {
        "exists": True,
        "size_bytes": size,
        "size_human": size_human,
        "path": str(path.resolve()),
    }


def backup_databases(dry_run: bool = False) -> dict:
    """
    Backup all database files.

    Args:
        dry_run: If True, only report what would be done without copying

    Returns:
        dict with backup results
    """
    backup_dir = get_backup_dir()
    results = {
        "timestamp": datetime.now().isoformat(),
        "backup_dir": str(backup_dir),
        "dry_run": dry_run,
        "files": {},
    }

    print(f"Backup directory: {backup_dir}")
    print("-" * 60)

    for name, path in DATABASE_FILES.items():
        info = get_file_info(path)
        results["files"][name] = info

        if not info["exists"]:
            print(f"SKIP: {name} - File not found at {path}")
            continue

        target = backup_dir / name

        if dry_run:
            print(f"WOULD COPY: {name} ({info['size_human']}) -> {target}")
        else:
            print(f"COPYING: {name} ({info['size_human']})...", end=" ", flush=True)
            shutil.copy2(path, target)
            print("OK")
            results["files"][name]["backed_up_to"] = str(target)

    # Save manifest
    manifest_path = backup_dir / "manifest.json"
    if not dry_run:
        with open(manifest_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nManifest saved: {manifest_path}")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Backup UTXOracle databases")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("UTXOracle Database Backup")
    print("=" * 60)

    results = backup_databases(dry_run=args.dry_run)

    print("\n" + "=" * 60)
    total_size = sum(
        f.get("size_bytes", 0) for f in results["files"].values() if f.get("exists")
    )
    print(f"Total backup size: {total_size / 1_000_000_000:.2f} GB")

    if args.dry_run:
        print("\nDry run complete. Use without --dry-run to perform backup.")
    else:
        print(f"\nBackup complete: {results['backup_dir']}")


if __name__ == "__main__":
    main()
