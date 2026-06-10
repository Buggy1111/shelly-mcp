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
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.statuses: dict[str, dict[str, Any]] = {
            "80646fe72f38": TELEVIZE, "3ce90ed7c30e": MYCKA,
        }

    async def all_status(self, *, show_info: bool = True) -> dict[str, Any]:
        self.all_status_calls += 1
        return self.statuses

    async def device_status(self, device_id: str) -> dict[str, Any]:
        return self.statuses[device_id]

    async def post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        self.posts.append((endpoint, data))
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


async def test_config_name_maps_to_cloud_id() -> None:
    # The Cloud API doesn't expose device names, so a friendly name -> cloud id mapping
    # comes from config; get_backend must resolve the name to the right device.
    from shelly_mcp.config import DeviceConfig

    client = FakeCloudClient()
    config = Config(devices={"mycka": DeviceConfig(id="3ce90ed7c30e")})
    reg = DeviceRegistry(config, cloud_client=client)  # type: ignore[arg-type]
    ident = await reg.require_identity("mycka")
    assert ident.id == "3ce90ed7c30e"
    assert ident.gen is Generation.GEN1
    backend = await reg.get_backend("mycka")
    await backend.call("Switch.Set", {"id": 0, "on": False})
    # The control post targeted the real cloud id, not the literal name "mycka".
    assert client.posts[-1][1]["id"] == "3ce90ed7c30e"


async def test_aliases_and_location_resolve_and_overlay() -> None:
    from shelly_mcp.config import DeviceConfig

    config = Config(
        devices={
            "mycka": DeviceConfig(
                id="3ce90ed7c30e", location="kuchyň", aliases=["myčka", "myčku"]
            )
        }
    )
    reg = DeviceRegistry(config, cloud_client=FakeCloudClient())  # type: ignore[arg-type]
    # An alias resolves to the same device...
    ident = await reg.require_identity("myčka")
    assert ident.id == "3ce90ed7c30e"
    # ...and the identity carries the configured friendly name + location.
    assert ident.name == "mycka"
    assert ident.location == "kuchyň"


async def test_list_devices_exposes_location() -> None:
    from shelly_mcp.config import DeviceConfig

    config = Config(devices={"mycka": DeviceConfig(id="3ce90ed7c30e", location="kuchyň")})
    reg = DeviceRegistry(config, cloud_client=FakeCloudClient())  # type: ignore[arg-type]
    devices = await reg.list_devices()
    mycka = next(d for d in devices if d.id == "3ce90ed7c30e")
    assert mycka.location == "kuchyň"


async def test_list_devices_shows_local_routing_for_configured_ip() -> None:
    """The listing must reflect how commands will route, not the cloud listing source.

    A device with a configured LAN ip is controlled locally (local-first routing in
    get_backend), so the fleet listing shows its ip and the local backend kind —
    local_rpc for Gen2+, local_rest for Gen1.
    """
    from shelly_mcp.config import DeviceConfig

    config = Config(
        devices={
            "televize": DeviceConfig(id="80646fe72f38", ip="192.168.0.101"),  # Gen2
            "mycka": DeviceConfig(id="3ce90ed7c30e", ip="192.168.0.107"),  # Gen1
        }
    )
    reg = DeviceRegistry(config, cloud_client=FakeCloudClient())  # type: ignore[arg-type]
    devices = {d.id: d for d in await reg.list_devices()}
    assert devices["80646fe72f38"].backend == "local_rpc"
    assert devices["80646fe72f38"].ip == "192.168.0.101"
    assert devices["3ce90ed7c30e"].backend == "local_rest"
    assert devices["3ce90ed7c30e"].ip == "192.168.0.107"


async def test_list_devices_keeps_cloud_backend_without_ip() -> None:
    """A configured device without an ip really is cloud-routed — listing says so."""
    from shelly_mcp.config import DeviceConfig

    config = Config(devices={"mycka": DeviceConfig(id="3ce90ed7c30e", location="kuchyň")})
    reg = DeviceRegistry(config, cloud_client=FakeCloudClient())  # type: ignore[arg-type]
    devices = {d.id: d for d in await reg.list_devices()}
    assert devices["3ce90ed7c30e"].backend == "cloud"
    assert devices["3ce90ed7c30e"].ip is None
