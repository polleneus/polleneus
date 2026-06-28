"""Pytest session config. P6 (continuous verification): when POLLENEUS_OFFLINE_CI=1 the test session runs
with the socket module's connection entry points blocked (in-process), so CI exercises the suite with no
reachable network. This is a REGRESSION GUARD, not a proof: it rebinds socket.socket / create_connection /
getaddrinfo only (the path http.client/urllib/requests/asyncio all build on); subprocess and C-level
(_socket / ctypes / raw syscalls) network are out of scope. NB the default `addopts = -m 'not slow'` means
this covers the FAST suite (the slow sweeps are deselected; they contain no network code either). Off by
default so local dev is unaffected; the always-on in-repo guard is tests/test_offline_first.py."""
import os
import socket


class _NoNetworkSocket:
    """Stub bound over socket.socket (kept a class so isinstance/subclass sites don't spuriously TypeError)."""
    def __new__(cls, *_a, **_k):
        raise RuntimeError("network access attempted — polleneus is offline-first (POLLENEUS_OFFLINE_CI=1)")


def _deny(*_a, **_k):
    raise RuntimeError("network access attempted — polleneus is offline-first (POLLENEUS_OFFLINE_CI=1)")


def pytest_configure(config):
    if os.environ.get("POLLENEUS_OFFLINE_CI") == "1":
        socket.socket = _NoNetworkSocket    # type: ignore[assignment]
        socket.create_connection = _deny     # type: ignore[assignment]
        socket.getaddrinfo = _deny           # type: ignore[assignment]
