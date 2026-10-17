"""Static gate: BRK files deployed from this repo must use the cookie, not argv credentials.

Scope, declared on purpose. The gate covers only the files listed in the versioned
manifest ``docs/contracts/brk_deployed_files.json`` (schema next to it, validated
with jsonschema, the engine of ``check-jsonschema``). It enforces:

1. Completeness: every repo file that launches BRK (a systemd unit, or a YAML with a
   top-level ``services`` mapping, referencing the ``brk`` / ``bitcoinresearchkit``
   word) must be in the manifest, whatever its name.
2. On each listed file, textual invariants only: no ``rpcpassword`` / ``rpcuser``
   (case-insensitive, comments included) and ``--rpccookiefile`` present.

It does NOT interpret systemd or Compose syntax: C escapes, drop-ins and resets,
``docker compose -f`` chains and override merging are out of scope, as are launcher
files with other extensions. Those need the effective configuration and belong to
the post-deploy runtime check (docker compose config, systemctl show, docker inspect).

Diagnostics carry file names, line numbers and flag names, never a configuration
value or a parser message (parsers quote their input).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import jsonschema
import yaml

MANIFEST_REL = Path("docs/contracts/brk_deployed_files.json")
SCHEMA_REL = Path("docs/contracts/brk_deployed_files.schema.json")
FORBIDDEN_FLAGS = ("rpcpassword", "rpcuser")
COOKIE_FLAG = b"--rpccookiefile"
# Whole-word match: BRK_BASE_URL (a client setting, not a launcher) does not count.
BRK_WORD = re.compile(r"(?<!\w)(brk|bitcoinresearchkit)(?!\w)", re.IGNORECASE)
UNIT_SUFFIXES = {
    ".service", ".socket", ".timer", ".path", ".mount", ".automount",
    ".swap", ".target", ".slice", ".scope",
}  # fmt: skip
YAML_SUFFIXES = {".yml", ".yaml"}
EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".tox"}


def _candidate_files(root: Path) -> set[Path]:
    """Unit and YAML files on disk plus the git-tracked ones (an excluded dir cannot hide one)."""
    suffixes = UNIT_SUFFIXES | YAML_SUFFIXES
    found: set[Path] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        found.update(
            Path(dirpath) / n for n in filenames if Path(n).suffix.lower() in suffixes
        )
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True, check=True, timeout=60,
        ).stdout  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        out = b""
    for name in out.decode("utf-8", "replace").split("\0"):
        path = root / name
        if name and path.suffix.lower() in suffixes and path.is_file():
            found.add(path)
    return found


def _strings(node: object):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(node, list):
        for item in node:
            yield from _strings(item)


def _launches_brk(path: Path) -> bool:
    """True if the file looks like a BRK launcher; unparseable input fails closed."""
    try:
        text = path.read_bytes().decode("utf-8", "replace")
    except OSError:
        return True
    if path.suffix.lower() in UNIT_SUFFIXES:
        return bool(BRK_WORD.search(text))
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return bool(BRK_WORD.search(text))
    if not isinstance(doc, dict) or "services" not in doc:
        return False
    return any(BRK_WORD.search(s) for s in _strings(doc["services"]))


def _load_manifest(root: Path) -> tuple[list[str], list[str]]:
    """Return (listed relative paths, violations); invalid manifest fails closed."""
    try:
        manifest = json.loads((root / MANIFEST_REL).read_text(encoding="utf-8"))
        schema = json.loads((root / SCHEMA_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [], [
            f"{MANIFEST_REL}: manifest or schema unreadable ({type(e).__name__})"
        ]
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(manifest),
        key=lambda e: list(map(str, e.absolute_path)),
    )
    if errors:
        # Location and rule only: the message quotes the offending value.
        return [], [
            f"{MANIFEST_REL}: schema violation at {list(e.absolute_path)} ({e.validator})"
            for e in errors
        ]
    return manifest["files"], []


def _check_listed(root: Path, rel: str) -> list[str]:
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return [f"{rel}: listed in the manifest but not a file inside the repository"]
    lowered = path.read_bytes().lower().replace(b"\x00", b"")  # UTF-16 viewed as bytes
    violations = []
    for flag in FORBIDDEN_FLAGS:
        lines = [
            str(no)
            for no, line in enumerate(lowered.splitlines(), start=1)
            if flag.encode() in line
        ]
        if lines:
            violations.append(
                f"{rel}: forbidden '{flag}' at line(s) {', '.join(lines[:10])}"
            )
    if COOKIE_FLAG not in lowered:
        violations.append(f"{rel}: '--rpccookiefile' not found")
    return violations


def scan_repo(repo_root: Path) -> list[str]:
    """Run the gate over a tree and return all violations (empty list = pass)."""
    root = repo_root.resolve()
    listed, violations = _load_manifest(root)
    if violations:
        return violations
    listed_paths = {(root / rel).resolve() for rel in listed}
    for path in sorted(_candidate_files(root)):
        if path.resolve() not in listed_paths and _launches_brk(path):
            violations.append(
                f"{path.relative_to(root)}: launches BRK but is not in the manifest"
                f" {MANIFEST_REL}"
            )
    for rel in listed:
        violations.extend(_check_listed(root, rel))
    return violations
