"""Contract tests — replay recorded real-device fixtures through the full stack.

These lock the normalization + identity contract against the *shapes Michal's real
devices actually return* (Gen1 SHPLG-S, Gen2 Plus Plug S + Plus RGBW). If a refactor
silently changes how Gen1↔Gen2 fold into canonical models — or breaks the
transport-dependent Gen1 energy unit (ADR-005) — a contract test fails.

The fixture is a recorded Shelly Cloud ``all_status`` payload; each device is replayed
through CloudBackend (probe) and the Normalizer (status), asserting the public shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from shelly_mcp.backends.cloud import CloudBackend
from shelly_mcp.models import Generation
from shelly_mcp.normalize import Normalizer

_FIXTURE = Path(__file__).parent / "fixtures" / "cloud_all_status.json"


@pytest.fixture(scope="module")
def all_status() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_FIXTURE.read_text())
    return data


class ReplayClient:
    """Serves the recorded fixture as a CloudClient would (no network)."""

    def __init__(self, statuses: dict[str, Any]) -> None:
        self._statuses = statuses

    async def all_status(self, *, show_info: bool = True) -> dict[str, Any]:
        return self._statuses

    async def device_status(self, device_id: str) -> dict[str, Any]:
        status: dict[str, Any] = self._statuses[device_id]
        return status


async def test_identity_contract_all_devices(all_status: dict[str, Any]) -> None:
    client = ReplayClient(all_status)
    expected = {
        "80646fe72f38": (Generation.GEN2, "SNPL-00112EU"),
        "3ce90ed7c30e": (Generation.GEN1, "SHPLG-S"),
        "c4dd57aabbcc": (Generation.GEN2, "SNDC-0D4P10WW"),
        "a8032ab1d2e3": (Generation.GEN1, "SHPLG-S"),
    }
    for dev_id, (gen, model) in expected.items():
        backend = CloudBackend(client, dev_id)  # type: ignore[arg-type]
        ident = await backend.probe()
        assert ident.gen is gen, dev_id
        assert ident.model == model, dev_id


async def test_gen1_capabilities_no_voltage_current(all_status: dict[str, Any]) -> None:
    backend = CloudBackend(ReplayClient(all_status), "3ce90ed7c30e")  # type: ignore[arg-type]
    await backend.probe()
    caps = backend.capabilities
    assert caps.has_energy is True
    assert caps.has_voltage_current is False  # Gen1 plug — the contract for mycka
    assert caps.can_automate is False         # cloud transport


async def test_gen2_capabilities_have_voltage_current(all_status: dict[str, Any]) -> None:
    backend = CloudBackend(ReplayClient(all_status), "80646fe72f38")  # type: ignore[arg-type]
    await backend.probe()
    assert backend.capabilities.has_voltage_current is True


def test_normalization_contract_gen1_energy_is_wh_over_cloud(all_status: dict[str, Any]) -> None:
    # mycka over cloud: total 548723 stays Wh (== ~549 kWh dishwasher), NOT ÷60 (ADR-005).
    ns = Normalizer.normalize_status(all_status["3ce90ed7c30e"], Generation.GEN1, backend="cloud")
    ch = ns.channels["switch:0"]
    assert ch.energy_total_wh == 548723.0
    assert ch.voltage is None  # None, never a fake 0
    assert ch.output is False
    assert ns.device_temp_c == 38.5


def test_normalization_contract_gen2_switch(all_status: dict[str, Any]) -> None:
    ns = Normalizer.normalize_status(all_status["80646fe72f38"], Generation.GEN2, backend="cloud")
    ch = ns.channels["switch:0"]
    assert ch.energy_total_wh == 379998.094  # Wh passthrough
    assert ch.voltage == 220.4
    assert ch.temperature_c == 44.6


def test_normalization_contract_gen2_rgbw_light(all_status: dict[str, Any]) -> None:
    ns = Normalizer.normalize_status(all_status["c4dd57aabbcc"], Generation.GEN2, backend="cloud")
    light = ns.lights["rgbw:0"]
    assert light.rgb == (255, 23, 47)
    assert light.brightness == 10
    assert ns.channels == {}  # an RGBW bulb has no switch channel
