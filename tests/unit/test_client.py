"""Unit tests for DeviceRegistry — fleet listing, resolution, identity caching.

No network: a FakeCloudClient is injected, so the whole routing layer is exercised
offline against real-shaped cloud payloads.
"""

from __future__ import annotations

from typing import Any

import pytest

from shelly_mcp.backends.base import BackendError
from shelly_mcp.client import DeviceRegistry
from shelly_mcp.config import CloudConfig, Config
from shelly_mcp.models import Generation

TELEVIZE = {
    "switch:0": {"output": True, "apower": 0.6, "voltage": 220.4, "current": 0.04,
                 "aenergy": {"total": 379998.094}},
    "_dev_info": {"id": "80646fe72f38", "gen": "G2", "code": "SNPL-00112EU", "online": True},
}
MYCKA = {
    "relays": [{"ison": False, "source": "cloud"}],
    "meters": [{"power": 0, "total": 548723}],
    "_dev_info": {"id": "3ce90ed7c30e", "gen": "G1", "code": "SHPLG-S", "online": True},
}


class FakeCloudClient:
    def __init__(self) -> None:
        self.all_status_calls = 0
        self.statuses = {"80646fe72f38": TELEVIZE, "3ce90ed7c30e": MYCKA}

    async def all_status(self, *, show_info: bool = True) -> dict[str, Any]:
        self.all_status_calls += 1
        return self.statuses

    async def device_status(self, device_id: str) -> dict[str, Any]:
        return self.statuses[device_id]

    async def post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    async def aclose(self) -> None:
        pass


def _registry() -> tuple[DeviceRegistry, FakeCloudClient]:
    client = FakeCloudClient()
    reg = DeviceRegistry(Config(), cloud_client=client)  # type: ignore[arg-type]
    return reg, client


async def test_list_devices_identifies_whole_fleet_in_one_call() -> None:
    reg, client = _registry()
    devices = await reg.list_devices()
    ids = {d.id for d in devices}
    assert ids == {"80646fe72f38", "3ce90ed7c30e"}
    gens = {d.id: d.gen for d in devices}
    assert gens["80646fe72f38"] is Generation.GEN2
    assert gens["3ce90ed7c30e"] is Generation.GEN1
    # The whole point of the refactor: one all_status for the fleet, not one-per-device.
    assert client.all_status_calls == 1


async def test_list_devices_caches_identity_and_caps() -> None:
    reg, _ = _registry()
    await reg.list_devices()
    caps = reg.capabilities("80646fe72f38")
    assert caps is not None
    assert caps.has_voltage_current is True
    assert caps.can_automate is False  # cloud can never automate


async def test_require_identity_uses_cache_after_listing() -> None:
    reg, client = _registry()
    await reg.list_devices()
    calls_before = client.all_status_calls
    ident = await reg.require_identity("3ce90ed7c30e")
    assert ident.gen is Generation.GEN1
    assert client.all_status_calls == calls_before  # served from cache, no extra probe


async def test_require_identity_probes_when_not_cached() -> None:
    reg, client = _registry()
    ident = await reg.require_identity("80646fe72f38")
    assert ident.model == "SNPL-00112EU"
    assert client.all_status_calls >= 1


async def test_get_backend_returns_working_cloud_backend() -> None:
    reg, _ = _registry()
    backend = await reg.get_backend("80646fe72f38")
    status = await backend.get_status()
    assert "switch:0" in status


async def test_cloud_not_configured_fails_closed() -> None:
    # No injected client and cloud disabled -> actionable error, not a silent None.
    reg = DeviceRegistry(Config(cloud=CloudConfig(enabled=False)))
    with pytest.raises(BackendError, match="cloud is not configured"):
        await reg.list_devices()
