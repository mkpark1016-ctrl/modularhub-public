from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from src.env_config import load_project_dotenv
from tests.hermetic import CREDENTIAL_ENV_NAMES, hermetic_subprocess_env


ROOT = Path(__file__).resolve().parents[1]


def test_offline_suite_disables_dotenv_and_unsets_credentials() -> None:
    assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"
    assert all(name not in os.environ for name in CREDENTIAL_ENV_NAMES)
    assert load_project_dotenv() is False


def test_external_network_fails_fast() -> None:
    with pytest.raises(RuntimeError, match="External network disabled"):
        socket.getaddrinfo("example.com", 443)


def test_hermetic_subprocess_environment_removes_credentials() -> None:
    env = hermetic_subprocess_env({"KIPRIS_API_KEY": "fixture-only"})
    assert env["PYTHON_DOTENV_DISABLED"] == "1"
    assert env["KIPRIS_API_KEY"] == "fixture-only"
    assert all(name not in env for name in CREDENTIAL_ENV_NAMES if name != "KIPRIS_API_KEY")


def test_subprocess_cannot_reload_repository_dotenv() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; from src import config; "
            "raise SystemExit(0 if not config.DATA_GO_KR_SERVICE_KEY and not config.KIPRIS_API_KEY else 1)",
        ],
        cwd=ROOT,
        env=hermetic_subprocess_env(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
