"""R5-M4: the resume commands in the cookie-migration runbook match the real batch CLIs.

The runbook is parsed with markdown-it-py (fenced code blocks and inline code), each
`python -m scripts.bootstrap.<batch>` line is tokenised with shlex, and every `--flag`
is checked against the argparse parser the batch really builds. The parser is captured
in a subprocess with a clean environment (no secrets, no RPC, no database): `parse_args`
is patched to hand back the parser instead of parsing.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

REPO = Path(__file__).resolve().parent.parent
RUNBOOK = REPO / "docs" / "BRK_COOKIE_MIGRATION_RUNBOOK.md"
BATCHES = (
    "historical_spent_backfill",
    "fast_spent_sync",
    "fast_spent_sync_v2",
    "run_combined_bootstrap",
    "build_block_heights",
)

# argparse has no public API to enumerate options; _option_string_actions is the
# registry add_argument fills and parse_args consults.
_CAPTURE = """
import argparse, json, runpy, sys

class Captured(Exception):
    pass

def capture(self, *args, **kwargs):
    raise Captured(sorted(self._option_string_actions))

argparse.ArgumentParser.parse_args = capture
try:
    runpy.run_module(sys.argv[1], run_name="__main__")
except Captured as done:
    print(json.dumps(done.args[0]))
"""


def _real_options(batch: str, tmp_path: Path) -> set[str]:
    # The batches import the shared secrets_loader from a path that only exists on the Dell: stub it,
    # as tests/conftest.py does in-process, so the check also runs on a CI runner.
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    (stubs / "secrets_loader.py").write_text(
        "def load_secrets(*args, **kwargs):\n    return None\n"
    )
    env = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": os.pathsep.join([str(REPO), str(stubs)]),
        "HOME": str(tmp_path),
    }
    out = subprocess.run(
        [sys.executable, "-c", _CAPTURE, f"scripts.bootstrap.{batch}"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout
    return set(json.loads(out.strip().splitlines()[-1]))


def _runbook_tokens():
    return MarkdownIt().parse(RUNBOOK.read_text(encoding="utf-8"))


def _batch_commands() -> list[tuple[str, list[str]]]:
    """(batch, flags) for each `-m scripts.bootstrap.<batch>` line in a fenced block."""
    found = []
    for token in _runbook_tokens():
        if token.type != "fence":
            continue
        for line in token.content.splitlines():
            words = shlex.split(line, comments=True)
            for i, word in enumerate(words[:-1]):
                if word == "-m" and words[i + 1].startswith("scripts.bootstrap."):
                    batch = words[i + 1].removeprefix("scripts.bootstrap.")
                    found.append((batch, [w for w in words[i + 2 :] if w[:2] == "--"]))
    return found


def test_every_inventoried_batch_has_a_resume_command():
    assert {batch for batch, _ in _batch_commands()} == set(BATCHES)


def test_runbook_flags_exist_in_the_real_batch_parsers(tmp_path):
    options = {batch: _real_options(batch, tmp_path) for batch in BATCHES}
    missing = [
        (batch, flag)
        for batch, flags in _batch_commands()
        for flag in flags
        if flag not in options[batch]
    ]
    assert missing == []


def test_resume_flag_is_only_cited_in_the_checked_commands():
    inline = [
        child.content
        for token in _runbook_tokens()
        if token.type == "inline"
        for child in token.children
        if child.type == "code_inline"
    ]
    assert [c for c in inline if "--resume" in c] == []


@pytest.mark.parametrize("batch", ["fast_spent_sync", "fast_spent_sync_v2"])
def test_fast_spent_sync_resume_relaunches_the_same_range(batch):
    """No checkpoint exists for these batches: the command must carry the range."""
    (flags,) = [f for b, f in _batch_commands() if b == batch]
    assert "--resume" not in flags
    assert {"--start-block", "--end-block"} <= set(flags)


def test_parser_capture_is_not_vacuous(tmp_path):
    """Guards the gate itself: --resume exists for one batch and not for the other."""
    assert "--resume" in _real_options("historical_spent_backfill", tmp_path)
    assert "--resume" not in _real_options("fast_spent_sync_v2", tmp_path)
