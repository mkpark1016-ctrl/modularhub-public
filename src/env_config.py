"""Environment loading helpers.

Local development may use a repository-root .env file, while hosted runs
should prefer already configured environment variables. This module never
prints or returns secret values.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_project_dotenv() -> bool:
    """Load repository-root .env without overriding existing environment values."""

    if os.getenv("PYTHON_DOTENV_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False

    env_path = ROOT / ".env"
    if not env_path.exists():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:
        return load_simple_dotenv(env_path)
    return bool(load_dotenv(env_path, override=False))


def load_simple_dotenv(path: Path) -> bool:
    """Minimal .env fallback with python-dotenv override=False semantics."""

    loaded = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value
        loaded = True
    return loaded


def env_status(name: str, *, expected_length: int | None = None) -> dict[str, object]:
    """Return non-secret environment diagnostics for a variable."""

    load_project_dotenv()
    value = os.getenv(name, "")
    status: dict[str, object] = {
        "name": name,
        "configured": bool(value),
        "length": len(value),
    }
    if expected_length is not None:
        status["expected_length_match"] = len(value) == expected_length
    return status
