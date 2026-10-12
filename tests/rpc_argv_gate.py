"""Gate library: BRK must authenticate to bitcoind with the cookie, never with argv credentials.

Fail-closed allowlist over every versioned systemd unit, Compose file, .env file
and referenced env_file (the repository tree is the only trusted source):

1. Substring ban: ``rpcpassword`` / ``rpcuser`` (case-insensitive) must not occur
   anywhere in those files, comments included. The ban is applied to the raw
   bytes and, in addition, to the spellings a parser reduces the text to (quotes
   removed, C escapes and YAML escapes decoded), so splitting the word cannot hide it.
2. No unverifiable sources in BRK services: ``EnvironmentFile=`` / ``env_file:``
   are accepted only when they resolve to a versioned in-repo file that passes
   rule 1; variable expansions in the BRK command are rejected (it must be literal).
3. Positive: the BRK command carries the cookie flag with a literal path, and the
   directory holding the cookie is mounted read-only.

A "BRK service" is any Compose service or systemd unit that mentions ``brk`` in
its name, image or command. Diagnostics carry only file, directive and numeric
positions, never a configuration value or parser message.
"""

from __future__ import annotations

import codecs
import fnmatch
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Iterator

import yaml

# The only file allowed to spell the forbidden words: this gate's own test.
GATE_TEST_FILE = Path(__file__).resolve().with_name("test_rpc_security.py")

FORBIDDEN_SUBSTRINGS = ("rpcpassword", "rpcuser")
COOKIE_FLAG = re.compile(r"^--?rpccookiefile(?:=(.*))?$", re.IGNORECASE)

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".cache",
    ".tox",
}

COMPOSE_PATTERNS = ("*compose*.yml", "*compose*.yaml")
UNIT_SUFFIXES = (
    "service",
    "socket",
    "timer",
    "path",
    "mount",
    "automount",
    "swap",
    "target",
    "slice",
    "scope",
)
UNIT_PATTERNS = tuple(f"*.{suffix}" for suffix in UNIT_SUFFIXES)
UNIT_DROPIN_DIR_PATTERNS = tuple(f"*.{suffix}.d" for suffix in UNIT_SUFFIXES)
ENV_PATTERNS = (".env", ".env.*", "*.env")
SYSTEMD_EXEC_KEYS = (
    "execstart",
    "execstartpre",
    "execstartpost",
    "execcondition",
    "execreload",
    "execstop",
    "execstoppost",
)
COMPOSE_FIELDS_SAFE_TO_NAME = {
    "command",
    "entrypoint",
    "environment",
    "env_file",
    "image",
    "volumes",
    "labels",
    "healthcheck",
    "container_name",
    "build",
}


# --- file discovery -------------------------------------------------------------


def _git_tracked(repo_root: Path) -> list[Path]:
    """Versioned files, so that an excluded directory can never hide one."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [repo_root / p for p in out.decode("utf-8", "replace").split("\0") if p]


def _matches(path: Path, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path.name, pat) for pat in patterns)


def _is_unit_file(path: Path) -> bool:
    if _matches(path, UNIT_PATTERNS):
        return True
    return path.suffix == ".conf" and any(
        fnmatch.fnmatch(path.parent.name, pat) for pat in UNIT_DROPIN_DIR_PATTERNS
    )


def find_repo_files(
    repo_root: Path, patterns: tuple[str, ...] | str | None = None, *, kind: str = ""
) -> list[Path]:
    """Files of a kind ('compose', 'unit', 'env') or matching glob patterns."""
    if isinstance(patterns, str):
        patterns = (patterns,)
    if kind == "compose":
        predicate = lambda p: _matches(p, COMPOSE_PATTERNS)  # noqa: E731
    elif kind == "unit":
        predicate = _is_unit_file
    elif kind == "env":
        predicate = lambda p: _matches(p, ENV_PATTERNS)  # noqa: E731
    else:
        predicate = lambda p: _matches(p, patterns or ())  # noqa: E731

    root = repo_root.resolve()
    found: set[Path] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            candidate = Path(dirpath) / name
            if predicate(candidate):
                found.add(candidate)
    found.update(
        p.resolve() for p in _git_tracked(root) if p.is_file() and predicate(p)
    )
    found.discard(GATE_TEST_FILE)
    return sorted(found)


# --- invariant 1: substring ban -------------------------------------------------


def _spellings(text: str) -> list[str]:
    """Spellings a parser may reduce `text` to: raw, unquoted, C-unescaped."""
    try:
        unescaped = codecs.decode(
            text.encode("latin-1", "backslashreplace"), "unicode_escape"
        )
    except (UnicodeDecodeError, ValueError):
        unescaped = text

    def strip(value: str) -> str:
        return re.sub(r"[\"'\\]", "", value).lower()

    return [text.lower(), strip(text), strip(unescaped)]


def _forbidden_terms(text: str) -> list[str]:
    spellings = _spellings(text)
    return [t for t in FORBIDDEN_SUBSTRINGS if any(t in s for s in spellings)]


def check_forbidden_substrings(raw: bytes, filename: str) -> list[str]:
    """Invariant 1 on raw bytes (UTF-16 handled by dropping NULs)."""
    violations: list[str] = []
    lowered = raw.lower().replace(b"\x00", b"")
    for term in FORBIDDEN_SUBSTRINGS:
        needle = term.encode()
        if needle not in lowered:
            continue
        lines = [
            str(no)
            for no, line in enumerate(lowered.splitlines(), start=1)
            if needle in line
        ]
        shown = ", ".join(lines[:10]) + (" ..." if len(lines) > 10 else "")
        violations.append(
            f"{filename}: forbidden substring '{term}' (invariant 1) at line(s) {shown}"
        )
    return violations


# --- invariant 2/3 helpers ------------------------------------------------------


def _shlex(text: str) -> list[str]:
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        return text.split()


def _words(value: Any) -> list[str]:
    """Argv words of a Compose command/entrypoint, including `sh -c` payloads."""
    items = value if isinstance(value, list) else [value]
    words: list[str] = []
    for item in items:
        if item is None:
            continue
        parts = _shlex(item) if isinstance(value, str) else [str(item)]
        for word in parts:
            words.append(word)
            if re.search(r"\s", word):
                words.extend(_shlex(word))
    return words


def _mentions_brk(*texts: str) -> bool:
    return any("brk" in s for text in texts for s in _spellings(text))


def _cookie_path(words: list[str]) -> str | None:
    """Literal value of the cookie flag, or None when absent or not literal."""
    for idx, word in enumerate(words):
        match = COOKIE_FLAG.match(word)
        if not match:
            continue
        value = match.group(1)
        if value is None:
            value = words[idx + 1] if idx + 1 < len(words) else ""
        if value.startswith("/") and "$" not in value:
            return value
    return None


def _covers(mount_target: str, path: str) -> bool:
    target = mount_target.rstrip("/")
    return path == target or path.startswith(target + "/")


def _resolve_in_repo(
    ref: str, base_dir: Path | None, repo_root: Path | None
) -> Path | None:
    """A referenced file, only if it is an existing file inside the repository."""
    if repo_root is None:
        return None
    candidate = Path(ref.lstrip("-"))
    if not candidate.is_absolute():
        if base_dir is None:
            return None
        candidate = base_dir / candidate
    try:
        resolved = candidate.resolve()
        root = repo_root.resolve()
    except OSError:
        return None
    if resolved == GATE_TEST_FILE or not resolved.is_file():
        return None
    return resolved if resolved.is_relative_to(root) else None


def _check_env_source(
    ref: str,
    *,
    owner: str,
    required: bool,
    base_dir: Path | None,
    repo_root: Path | None,
) -> list[str]:
    """Env file referenced by a service/unit: must be a clean in-repo file when required."""
    resolved = _resolve_in_repo(ref, base_dir, repo_root)
    if resolved is None:
        if required:
            return [
                f"{owner}: environment source is not a versioned in-repo file "
                "(invariant 2)"
            ]
        return []
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        return [f"{owner}: environment source unreadable ({type(exc).__name__})"]
    rel = resolved.relative_to(repo_root.resolve()) if repo_root else resolved
    return check_forbidden_substrings(raw, str(rel))


# --- Compose --------------------------------------------------------------------


def _yaml_error_location(error: yaml.YAMLError) -> str:
    """Describe a parser failure by type and numeric position only.

    str(error) embeds the offending source line, which may hold a credential.
    """
    mark = getattr(error, "problem_mark", None) or getattr(error, "context_mark", None)
    where = (
        f"line {mark.line + 1}, column {mark.column + 1}"
        if mark is not None
        else "unknown position"
    )
    return f"failed to parse YAML ({type(error).__name__}) at {where}"


def _walk_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(key)
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def _compose_mount_read_only(volumes: Any, path: str) -> bool:
    mounts: list[tuple[str, bool]] = []
    for vol in volumes if isinstance(volumes, list) else []:
        if isinstance(vol, str):
            parts = vol.split(":")
            if len(parts) >= 2:
                mode = parts[2].lower().split(",") if len(parts) > 2 else []
                mounts.append((parts[1], "ro" in mode))
        elif isinstance(vol, dict) and "target" in vol:
            mounts.append((str(vol["target"]), vol.get("read_only") is True))
    covering = [m for m in mounts if _covers(m[0], path)]
    return bool(covering) and max(covering, key=lambda m: len(m[0]))[1]


def _env_file_refs(value: Any) -> list[str]:
    refs = value if isinstance(value, list) else [value]
    out: list[str] = []
    for ref in refs:
        if isinstance(ref, dict):
            ref = ref.get("path")
        if isinstance(ref, str):
            out.append(ref)
    return out


def _check_compose_service(
    name: str,
    conf: dict[str, Any],
    filename: str,
    base_dir: Path | None,
    repo_root: Path | None,
    raw_hit: bool,
) -> list[str]:
    violations: list[str] = []
    owner = f"{filename}: service '{name}'"

    for field in ("command", "entrypoint"):
        value = conf.get(field)
        if value is None:
            continue
        if not isinstance(value, (str, list)) or (
            isinstance(value, list)
            and not all(isinstance(i, (str, int, float, bool)) for i in value)
        ):
            violations.append(f"{owner} has invalid schema for '{field}'")

    for field, value in conf.items():
        if not raw_hit and any(_forbidden_terms(s) for s in _walk_strings(value)):
            shown = field if field in COMPOSE_FIELDS_SAFE_TO_NAME else "<other>"
            violations.append(
                f"{owner}: decoded value of '{shown}' contains a forbidden substring"
                " (invariant 1)"
            )

    argv = _words(conf.get("entrypoint")) + _words(conf.get("command"))
    is_brk = _mentions_brk(
        name,
        str(conf.get("image", "")),
        str(conf.get("container_name", "")),
        *argv,
    )

    for ref in _env_file_refs(conf.get("env_file")):
        violations.extend(
            _check_env_source(
                ref,
                owner=owner,
                required=is_brk,
                base_dir=base_dir,
                repo_root=repo_root,
            )
        )
    if not is_brk:
        return violations

    # Invariant 2: nothing the repo cannot verify may reach a BRK service.
    if conf.get("env_file") is not None and not _env_file_refs(conf.get("env_file")):
        violations.append(f"{owner}: unrecognised env_file form (invariant 2)")
    env = conf.get("environment")
    if isinstance(env, list) and any(
        isinstance(item, str) and "=" not in item for item in env
    ):
        violations.append(
            f"{owner}: environment entry inherited from the host (invariant 2)"
        )
    if any("$" in w or "`" in w for w in argv):
        violations.append(
            f"{owner}: variable expansion in the BRK command (invariant 2)"
        )

    # Invariant 3: cookie flag and read-only datadir mount.
    cookie = _cookie_path(argv)
    if cookie is None:
        violations.append(
            f"{owner}: BRK command lacks a literal --rpccookiefile (invariant 3)"
        )
    elif not _compose_mount_read_only(conf.get("volumes"), cookie):
        violations.append(
            f"{owner}: cookie directory is not mounted read-only (invariant 3)"
        )
    return violations


def check_compose_content(
    content: str,
    filename: str = "compose.yml",
    base_dir: Path | None = None,
    repo_root: Path | None = None,
) -> list[str]:
    """Inspect Compose YAML content and return violations."""
    violations = check_forbidden_substrings(content.encode("utf-8"), filename)
    raw_hit = bool(violations)
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        violations.append(f"{filename}: {_yaml_error_location(e)}")
        return violations

    if not isinstance(data, dict):
        return violations
    services = data.get("services")
    if isinstance(services, dict):
        for svc_name, svc_conf in services.items():
            if isinstance(svc_conf, dict):
                violations.extend(
                    _check_compose_service(
                        str(svc_name), svc_conf, filename, base_dir, repo_root, raw_hit
                    )
                )
    if not raw_hit:
        for key, value in data.items():
            if key != "services" and any(
                _forbidden_terms(s) for s in _walk_strings(value)
            ):
                violations.append(
                    f"{filename}: decoded top-level value contains a forbidden "
                    "substring (invariant 1)"
                )
    return violations


# --- systemd --------------------------------------------------------------------


def parse_systemd_lines(content: str) -> list[tuple[int, str]]:
    """Logical lines per systemd.syntax: comment lines are dropped even inside a
    continuation, then trailing-backslash lines are joined."""
    logical: list[tuple[int, str]] = []
    current = ""
    start = 1
    for line_no, raw in enumerate(content.splitlines(), start=1):
        if raw.strip().startswith(("#", ";")):
            continue
        if not current:
            start = line_no
        line = raw.rstrip()
        if line.endswith("\\"):
            current += line[:-1] + " "
            continue
        current += line
        if current.strip():
            logical.append((start, current.strip()))
        current = ""
    if current.strip():
        logical.append((start, current.strip()))
    return logical


def _unit_directives(content: str) -> list[tuple[int, str, str]]:
    out: list[tuple[int, str, str]] = []
    for line_no, line in parse_systemd_lines(content):
        key, sep, value = line.partition("=")
        if sep:
            out.append((line_no, key.strip().lower(), value.strip()))
    return out


def _unit_read_only_paths(directives: list[tuple[int, str, str]]) -> list[str]:
    paths: list[str] = []
    for _, key, value in directives:
        if key == "readonlypaths":
            paths.extend(p.lstrip("-+") for p in value.split())
        elif key == "bindreadonlypaths":
            for entry in value.split():
                parts = entry.lstrip("-+").split(":")
                paths.append(parts[1] if len(parts) > 1 else parts[0])
    return paths


def _inline_read_only_mount(words: list[str], path: str) -> bool:
    """`-v src:dst:ro` / `--mount ...,target=dst,readonly` carried by the command itself."""
    for idx, word in enumerate(words):
        spec = None
        if word in ("-v", "--volume", "--mount") and idx + 1 < len(words):
            spec = words[idx + 1]
        elif word.startswith(("--volume=", "--mount=")):
            spec = word.split("=", 1)[1]
        if spec is None:
            continue
        if "target=" in spec or "dst=" in spec:
            fields = dict(p.split("=", 1) for p in spec.split(",") if "=" in p)
            target = fields.get("target") or fields.get("dst") or ""
            ro = (
                "readonly" in spec.split(",")
                or fields.get("readonly")
                in (
                    "true",
                    "1",
                )
                or fields.get("ro") in ("true", "1")
            )
        else:
            parts = spec.split(":")
            target = parts[1] if len(parts) > 1 else ""
            ro = len(parts) > 2 and "ro" in parts[2].lower().split(",")
        if target and _covers(target, path) and ro:
            return True
    return False


def check_unit_content(
    content: str,
    filename: str = "unit.service",
    base_dir: Path | None = None,
    repo_root: Path | None = None,
) -> list[str]:
    """Inspect systemd unit content and return violations."""
    violations = check_forbidden_substrings(content.encode("utf-8"), filename)
    directives = _unit_directives(content)
    execs = [(n, v) for n, k, v in directives if k in SYSTEMD_EXEC_KEYS]
    brk_execs = [(n, v) for n, v in execs if _mentions_brk(v)]
    is_brk = _mentions_brk(Path(filename).name) or bool(brk_execs)

    raw_hit = bool(violations)
    for line_no, key, value in directives:
        # Quotes/escapes can hide the word from the raw scan only.
        if not raw_hit and _forbidden_terms(value):
            violations.append(
                f"{filename}:{line_no}: decoded '{key}' contains a forbidden "
                "substring (invariant 1)"
            )
        if key == "environmentfile":
            violations.extend(
                _check_env_source(
                    value,
                    owner=f"{filename}:{line_no}",
                    required=is_brk,
                    base_dir=base_dir,
                    repo_root=repo_root,
                )
            )
        elif key == "passenvironment" and is_brk:
            violations.append(
                f"{filename}:{line_no}: PassEnvironment is not verifiable (invariant 2)"
            )
    if not is_brk:
        return violations

    if not brk_execs:
        violations.append(
            f"{filename}: BRK unit has no verifiable BRK command (invariant 3)"
        )
    read_only = _unit_read_only_paths(directives)
    for line_no, value in brk_execs:
        if "$" in value or "%" in value:
            violations.append(
                f"{filename}:{line_no}: variable or specifier expansion in the BRK"
                " command (invariant 2)"
            )
        words = _shlex(re.sub(r"^[-@+!:]+", "", value))
        cookie = _cookie_path(words)
        if cookie is None:
            violations.append(
                f"{filename}:{line_no}: BRK command lacks a literal --rpccookiefile"
                " (invariant 3)"
            )
        elif not (
            any(_covers(p, cookie) for p in read_only)
            or _inline_read_only_mount(words, cookie)
        ):
            violations.append(
                f"{filename}:{line_no}: cookie directory is not read-only (invariant 3)"
            )
    return violations


# --- on-disk entry points -------------------------------------------------------


def _read(path: Path, repo_root: Path) -> tuple[bytes | None, str, list[str]]:
    resolved = path.resolve()
    root = repo_root.resolve()
    rel = (
        str(resolved.relative_to(root)) if resolved.is_relative_to(root) else str(path)
    )
    try:
        return path.read_bytes(), rel, []
    except OSError as e:
        return None, rel, [f"{rel}: could not read file ({type(e).__name__})"]


def check_compose_file(path: Path, repo_root: Path) -> list[str]:
    raw, rel, errors = _read(path, repo_root)
    if raw is None:
        return errors
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return check_forbidden_substrings(raw, rel) + [
            f"{rel}: not valid UTF-8 ({type(e).__name__})"
        ]
    return check_compose_content(content, rel, path.parent, repo_root)


def check_unit_file(path: Path, repo_root: Path) -> list[str]:
    raw, rel, errors = _read(path, repo_root)
    if raw is None:
        return errors
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return check_forbidden_substrings(raw, rel) + [
            f"{rel}: not valid UTF-8 ({type(e).__name__})"
        ]
    return check_unit_content(content, rel, path.parent, repo_root)


def check_env_file(path: Path, repo_root: Path) -> list[str]:
    raw, rel, errors = _read(path, repo_root)
    return errors if raw is None else check_forbidden_substrings(raw, rel)


def scan_repo(repo_root: Path) -> list[str]:
    """Run every gate over a tree and return all violations."""
    violations: list[str] = []
    for path in find_repo_files(repo_root, kind="compose"):
        violations.extend(check_compose_file(path, repo_root))
    for path in find_repo_files(repo_root, kind="unit"):
        violations.extend(check_unit_file(path, repo_root))
    for path in find_repo_files(repo_root, kind="env"):
        violations.extend(check_env_file(path, repo_root))
    return violations
