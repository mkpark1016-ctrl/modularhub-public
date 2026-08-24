from __future__ import annotations

import os
from collections.abc import Mapping


CREDENTIAL_ENV_NAMES = (
    "DATA_GO_KR_SERVICE_KEY",
    "LH_SERVICE_KEY",
    "D2B_SERVICE_KEY",
    "KEPCO_API_KEY",
    "KIPRIS_API_KEY",
    "KAIA_API_KEY",
    "NTIS_API_KEY",
    "DART_API_KEY",
    "NAVER_API_HUB_CLIENT_ID",
    "NAVER_API_HUB_CLIENT_SECRET",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GITHUB_TOKEN",
)


def hermetic_subprocess_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a deterministic subprocess environment without live credentials."""

    env = os.environ.copy()
    env["PYTHON_DOTENV_DISABLED"] = "1"
    for name in CREDENTIAL_ENV_NAMES:
        env.pop(name, None)
    if overrides:
        env.update(overrides)
    return env
