"""Unit tests for CloudBackend mapping + capabilities, using a fake client (no network).

Fixtures mirror real payloads captured from Michal's devices (see [[shelly-devices]]).
"""

from __future__ import annotations

from typing import Any

import pytest

from shelly_mcp.backends.base import UnsupportedOnCloud
from shelly_mcp.backends.cloud import CloudBackend
from shelly_mcp.models import Generation

# Real-shaped cloud all_status payloads (trimmed).
TELEVIZE = {  # Gen2 Plus Plug S
    "switch:0": {"output": True, "apower": 0.6, "voltage": 220.4, "current": 0.04,
                 "aenergy": {"total": 379998.094}},
    "_dev_info": {"id": "80646fe72f38", "gen": "G2", "code": "SNPL-00112EU", "online": True},
}
MYCKA = {  # Gen1 Plug S — relays[]/meters[], no per-channel voltage
    "relays": [{"ison": False, "source": "cloud"}],
    "meters": [{"power": 0, "total": 548723}],
    "_dev_info": {"id": "3ce90ed7c30e", "gen": "G1", "code": "SHPLG-S", "online": True},
}


class FakeCloudClient:
    """Records control posts; returns canned status. Mimics CloudClient's used surface."""

    def __init__(self, statuses: dict[str, dict[str, Any]]) -> None:
        self._statuses = statuses
        self.posts: list[tuple[str, dict[str, Any]]] = []

    async def all_status(self, *, show_info: bool = True) -> dict[str, Any]:
        return self._statuses

    async def device_status(self, device_id: str) -> dict[str, Any]:
        return self._statuses[device_id]

    async def post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        self.posts.append((endpoint, data))
        return {"ok": True}


def _backend(device_id: str) -> tuple[CloudBackend, FakeCloudClient]:
    client = FakeCloudClient({"80646fe72f38": TELEVIZE, "3ce90ed7c30e": MYCKA})
    return CloudBackend(client, device_id), client  # type: ignore[arg-type]


async def test_probe_gen2_identity_and_caps() -> None:
    backend, _ = _backend("80646fe72f38")
    ident = await backend.probe()
    assert ident.gen is Generation.GEN2
    assert ident.model == "SNPL-00112EU"
    assert ident.online is True
    assert ident.backend == "cloud"
    caps = backend.capabilities
    assert caps.can_automate is False  # cloud can never automate
    assert caps.has_energy is True
    assert caps.has_voltage_current is True
    assert "switch:0" in caps.components


async def test_probe_gen1_caps_no_voltage() -> None:
    backend, _ = _backend("3ce90ed7c30e")
    ident = await backend.probe()
    assert ident.gen is Generation.GEN1
    caps = backend.capabilities
    assert caps.has_energy is True            # meters[].power present
    assert caps.has_voltage_current is False  # Gen1 plug reports no voltage
    assert "relay:0" in caps.components


async def test_probe_missing_device_raises() -> None:
    backend, _ = _backend("does-not-exist")
    with pytest.raises(Exception, match="not found"):
        await backend.probe()


async def test_switch_set_on_maps_to_relay_control() -> None:
    backend, client = _backend("80646fe72f38")
    await backend.call("Switch.Set", {"id": 0, "on": True})
    endpoint, data = client.posts[-1]
    assert endpoint == "/device/relay/control"
    assert data["turn"] == "on"
    assert data["channel"] == 0


async def test_switch_set_off_and_toggle() -> None:
    backend, client = _backend("80646fe72f38")
    await backend.call("Switch.Set", {"on": False})
    assert client.posts[-1][1]["turn"] == "off"
    await backend.call("Switch.Toggle", {})
    assert client.posts[-1][1]["turn"] == "toggle"


async def test_light_set_rgb_maps_colour_and_gain() -> None:
    backend, client = _backend("80646fe72f38")
    await backend.call("RGBW.Set", {"on": True, "rgb": [255, 23, 47], "brightness": 40, "white": 0})
    endpoint, data = client.posts[-1]
    assert endpoint == "/device/light/control"
    assert (data["red"], data["green"], data["blue"]) == (255, 23, 47)
    assert data["gain"] == 40           # colour -> gain, not brightness
    assert data["turn"] == "on"


async def test_cover_open_maps_direction() -> None:
    backend, client = _backend("80646fe72f38")
    await backend.call("Cover.Open", {"id": 0})
    endpoint, data = client.posts[-1]
    assert endpoint == "/device/relay/roller/control"
    assert data["direction"] == "open"


async def test_get_config_unsupported_on_cloud() -> None:
    backend, _ = _backend("80646fe72f38")
    with pytest.raises(UnsupportedOnCloud):
        await backend.get_config()


async def test_unknown_method_unsupported_on_cloud() -> None:
    backend, _ = _backend("80646fe72f38")
    with pytest.raises(UnsupportedOnCloud, match="connect to the device locally"):
        await backend.call("Schedule.Create", {"timespec": "0 0 22 * * *"})


async def test_list_components_from_status() -> None:
    backend, _ = _backend("3ce90ed7c30e")
    comps = await backend.list_components()
    assert "relay:0" in comps and "meter:0" in comps
