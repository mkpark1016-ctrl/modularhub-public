from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any

import pytest

from tests.hermetic import CREDENTIAL_ENV_NAMES


os.environ["PYTHON_DOTENV_DISABLED"] = "1"
for _name in CREDENTIAL_ENV_NAMES:
    os.environ.pop(_name, None)


def _is_loopback_host(host: Any) -> bool:
    if host is None:
        return True
    normalized = str(host).strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail fast when an offline test attempts an external network call."""

    original_getaddrinfo = socket.getaddrinfo
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any):
        if not _is_loopback_host(host):
            raise RuntimeError(f"External network disabled in tests: host={host!r}")
        return original_getaddrinfo(host, *args, **kwargs)

    def guarded_connect(sock: socket.socket, address: Any):
        host = address[0] if isinstance(address, tuple) and address else address
        if not _is_loopback_host(host):
            raise RuntimeError(f"External network disabled in tests: host={host!r}")
        return original_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: Any):
        host = address[0] if isinstance(address, tuple) and address else address
        if not _is_loopback_host(host):
            raise RuntimeError(f"External network disabled in tests: host={host!r}")
        return original_connect_ex(sock, address)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
