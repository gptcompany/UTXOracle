"""Project environment loading shared by the API and the token CLI.

Kept apart from api.config so a consumer can resolve the same environment (for example
AUTH_ENABLED from .env) without api.config's JWT_SECRET requirement.
"""

import logging
import os
import sys
from pathlib import Path

from api.secret_values import is_encrypted

_logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _select_loader():
    """Return (loader, mode): SOPS-encrypted secrets when available, otherwise dotenv or plain env."""
    try:
        sys.path.insert(0, "/media/sam/1TB/claude-hooks-shared/scripts")
        from secrets_loader import load_secrets

        return load_secrets, "sops"
    except ImportError:
        pass
    try:
        from dotenv import load_dotenv

        return load_dotenv, "dotenv"
    except ImportError:

        def load_secrets(_path: str | None = None):
            return False

        return load_secrets, "env"


def load_project_environment(loader, path: Path | None) -> list[str]:
    """Run ``loader`` without letting it override the environment; return the names of dropped ciphertext keys."""
    preset = dict(os.environ)
    loader(str(path) if path else None)
    # Preset ciphertext is not restored: the loader may have decrypted that key from the env file.
    os.environ.update(
        {key: value for key, value in preset.items() if not is_encrypted(value)}
    )
    dropped = sorted(key for key, value in os.environ.items() if is_encrypted(value))
    for key in dropped:
        del os.environ[key]
    if dropped:
        # Names only: a value must never reach the log.
        _logger.error(
            "Dropped still-encrypted environment values: %s", ", ".join(dropped)
        )
    return dropped


def load_environment(project_root: Path | None = None) -> list[str]:
    """Load the project env file into os.environ (the process environment wins for every key).

    The env file only fills keys that are still missing. A value that is still ciphertext is
    never left in os.environ: used verbatim it would turn committed ciphertext into a signing key.
    """
    root = project_root or _PROJECT_ROOT
    loader, mode = _select_loader()
    env_enc_path = root / ".env.enc"
    env_path = root / ".env"
    if mode == "sops" and env_enc_path.exists():
        env_file = env_enc_path
    elif env_path.exists():
        env_file = env_path
    else:
        env_file = None
    return load_project_environment(loader, env_file)
