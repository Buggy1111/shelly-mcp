"""Tests for the local HTTP backends + registry routing + digest auth (ADR-006).

A fake aiohttp session (async-context-manager responses) drives Gen1 GET and Gen2
POST /rpc offline. Live verification against real devices is pending WSL mirrored
networking — these lock the request shaping, auth flow, and routing logic.
"""

from __future__ import annotations

from typing import Any

import pytest

from shelly_mcp.auth import digest_authorization
from shelly_mcp.backends.base import AuthRequired
from shelly_mcp.backends.gen1_rest import Gen1RestBackend
from shelly_mcp.backends.gen2_rpc import Gen2RpcBackend
from shelly_mcp.client import DeviceRegistry
from shelly_mcp.config import Config, DeviceConfig
from shelly_mcp.models import Generation


class FakeResponse:
    def __init__(self, payload: Any, status: int = 200, headers: dict[str, str] | None = None):
        self.status = status
        self._payload = payload
        self.headers = headers or {}

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def json(self) -> Any:
        return self._payload


class FakeSession:
    """Returns queued responses per HTTP verb+path; records each request."""

    def __init__(self) -> None:
        self.closed = False
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self._queues: dict[str, list[FakeResponse]] = {"get": [], "post": []}

    def queue_get(self, *responses: FakeResponse) -> None:
        self._queues["get"].extend(responses)

    def queue_post(self, *responses: FakeResponse) -> None:
        self._queues["post"].extend(responses)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append(("get", url, kwargs))
        return self._queues["get"].pop(0)

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append(("post", url, kwargs))
        return self._queues["post"].pop(0)


# ----------------------------------------------------------------- Gen1 REST
async def test_gen1_probe_identity_and_caps() -> None:
    session = FakeSession()
    session.queue_get(
        FakeResponse({"type": "SHPLG-S", "mac": "3CE90ED7C30E", "auth": False, "fw": "1.0"}),
        FakeResponse({"relays": [{"ison": False}], "meters": [{"power": 0, "total": 100}]}),
    )
    backend = Gen1RestBackend(session, "192.168.0.50")  # type: ignore[arg-type]
    ident = await backend.probe()
    assert ident.gen is Generation.GEN1
    assert ident.model == "SHPLG-S"
    assert ident.backend == "local_rest"
    assert backend.capabilities.has_energy is True


async def test_gen1_switch_set_builds_relay_url() -> None:
    session = FakeSession()
    session.queue_get(FakeResponse({"ison": True}))
    backend = Gen1RestBackend(session, "192.168.0.50")  # type: ignore[arg-type]
    await backend.call("Switch.Set", {"id": 0, "on": True})
    _, url, kwargs = session.requests[-1]
    assert url == "http://192.168.0.50/relay/0"
    assert kwargs["params"] == {"turn": "on"}


async def test_gen1_401_raises_auth_required() -> None:
    session = FakeSession()
    session.queue_get(FakeResponse({}, status=401))
    backend = Gen1RestBackend(session, "192.168.0.50")  # type: ignore[arg-type]
    with pytest.raises(AuthRequired):
        await backend.get_status()


# ------------------------------------------------------------------ Gen2 RPC
def test_digest_authorization_is_deterministic() -> None:
    challenge = {"realm": "shellyplus1-abc", "nonce": "deadbeef", "qop": "auth"}
    header = digest_authorization(
        challenge, user="admin", password="secret", method="POST", uri="/rpc",
        cnonce="0123456789abcdef",
    )
    assert header.startswith("Digest ")
    assert 'username="admin"' in header
    assert 'algorithm=SHA-256' in header
    # Recomputing with the same inputs is stable (locks the hashing).
    again = digest_authorization(
        challenge, user="admin", password="secret", method="POST", uri="/rpc",
        cnonce="0123456789abcdef",
    )
    assert header == again


async def test_gen2_call_returns_result_no_auth() -> None:
    session = FakeSession()
    session.queue_post(FakeResponse({"result": {"was_on": True}}))
    backend = Gen2RpcBackend(session, "192.168.0.60")  # type: ignore[arg-type]
    out = await backend.call("Switch.Set", {"id": 0, "on": False})
    assert out == {"was_on": True}
    _, url, kwargs = session.requests[-1]
    assert url == "http://192.168.0.60:80/rpc"
    assert kwargs["json"]["method"] == "Switch.Set"


async def test_gen2_digest_challenge_then_success() -> None:
    session = FakeSession()
    session.queue_post(
        FakeResponse({}, status=401, headers={
            "WWW-Authenticate": 'Digest qop="auth", realm="shellyplus1-abc", nonce="abc123"'}),
        FakeResponse({"result": {"ok": True}}),
    )
    backend = Gen2RpcBackend(session, "192.168.0.60", password="mypassword12")  # type: ignore[arg-type]
    out = await backend.call("Switch.Set", {"id": 0, "on": True})
    assert out == {"ok": True}
    # Second request carried the Authorization header.
    _, _, kwargs = session.requests[-1]
    assert kwargs["headers"]["Authorization"].startswith("Digest ")


async def test_gen2_401_without_password_raises() -> None:
    session = FakeSession()
    session.queue_post(FakeResponse({}, status=401, headers={
        "WWW-Authenticate": 'Digest qop="auth", realm="x", nonce="y"'}))
    backend = Gen2RpcBackend(session, "192.168.0.60")  # type: ignore[arg-type]
    with pytest.raises(AuthRequired):
        await backend.call("Shelly.GetStatus")


# --------------------------------------------------------- registry routing
async def test_registry_routes_configured_ip_to_local_gen2() -> None:
    session = FakeSession()
    session.queue_get(FakeResponse({"id": "shellyplus1-abc", "gen": 2, "model": "SNSW-001"}))
    config = Config(devices={"kitchen": DeviceConfig(ip="192.168.0.60")})
    reg = DeviceRegistry(config, http_session=session)  # type: ignore[arg-type]
    backend = await reg.get_backend("kitchen")
    assert isinstance(backend, Gen2RpcBackend)


async def test_registry_routes_configured_ip_to_local_gen1() -> None:
    session = FakeSession()
    session.queue_get(FakeResponse({"type": "SHPLG-S", "mac": "abc"}))  # no 'gen' -> Gen1
    config = Config(devices={"plug": DeviceConfig(ip="192.168.0.50")})
    reg = DeviceRegistry(config, http_session=session)  # type: ignore[arg-type]
    backend = await reg.get_backend("plug")
    assert isinstance(backend, Gen1RestBackend)


async def test_registry_caches_local_backend() -> None:
    session = FakeSession()
    session.queue_get(FakeResponse({"id": "x", "gen": 2}))
    config = Config(devices={"kitchen": DeviceConfig(ip="192.168.0.60")})
    reg = DeviceRegistry(config, http_session=session)  # type: ignore[arg-type]
    first = await reg.get_backend("kitchen")
    second = await reg.get_backend("kitchen")  # no second /shelly probe
    assert first is second
    assert len(session.requests) == 1
