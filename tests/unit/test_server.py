"""Unit tests for the M1 read tools, driven through an injected registry (no network).

Tools are FastMCP ``FunctionTool`` objects; ``.fn`` is the underlying coroutine.
"""

from __future__ import annotations

from typing import Any

import pytest

from shelly_mcp.audit import AuditLog
from shelly_mcp.client import DeviceRegistry
from shelly_mcp.config import Config
from shelly_mcp.server import set_audit, set_registry
from shelly_mcp.tools.read import (
    shelly_get_config,
    shelly_get_info,
    shelly_get_status,
    shelly_list_components,
    shelly_list_devices,
    shelly_version,
)

TELEVIZE = {
    "switch:0": {"output": True, "apower": 0.6, "voltage": 220.4, "current": 0.04,
                 "aenergy": {"total": 379998.094}},
    "_dev_info": {"id": "80646fe72f38", "gen": "G2", "code": "SNPL-00112EU", "online": True},
}
MYCKA = {
    "relays": [{"ison": False, "source": "cloud"}],
    "meters": [{"power": 0, "total": 548723}],  # Watt-minutes
    "_dev_info": {"id": "3ce90ed7c30e", "gen": "G1", "code": "SHPLG-S", "online": True},
}


class FakeCloudClient:
    def __init__(self) -> None:
        self.statuses: dict[str, dict[str, Any]] = {
            "80646fe72f38": TELEVIZE, "3ce90ed7c30e": MYCKA,
        }

    async def all_status(self, *, show_info: bool = True) -> dict[str, Any]:
        return self.statuses

    async def device_status(self, device_id: str) -> dict[str, Any]:
        return self.statuses[device_id]

    async def post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    async def aclose(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _wire_registry(tmp_path: Any) -> Any:
    reg = DeviceRegistry(Config(), cloud_client=FakeCloudClient())  # type: ignore[arg-type]
    set_registry(reg)
    set_audit(AuditLog(tmp_path / "audit.jsonl"))
    yield
    set_registry(None)
    set_audit(None)


def test_version_health_check() -> None:
    from shelly_mcp import __version__

    out = shelly_version.fn()
    assert out["name"] == "shelly-mcp"
    assert out["version"] == __version__


def test_server_reports_own_version_not_framework() -> None:
    # Regression: FastMCP's serverInfo.version defaults to the framework version; the
    # MCP handshake must advertise *our* version (0.1.x), not fastmcp's, so clients
    # display the right thing. See the clean-install smoke test.
    from shelly_mcp import __version__
    from shelly_mcp.app import mcp

    assert mcp.version == __version__


async def test_list_devices_tool() -> None:
    out = await shelly_list_devices.fn()
    assert out["count"] == 2
    ids = {d["id"] for d in out["devices"]}
    assert ids == {"80646fe72f38", "3ce90ed7c30e"}


async def test_get_info_tool_includes_capabilities() -> None:
    out = await shelly_get_info.fn(device="80646fe72f38")
    assert out["identity"]["model"] == "SNPL-00112EU"
    assert out["capabilities"]["has_voltage_current"] is True


async def test_get_status_gen2_normalized() -> None:
    out = await shelly_get_status.fn(device="80646fe72f38")
    assert out["gen"] == 2
    ch = out["channels"]["switch:0"]
    assert ch["output"] is True
    assert ch["energy_total_wh"] == 379998.094  # Wh passthrough
    assert "raw" in out


async def test_get_status_gen1_cloud_energy_is_wh_passthrough() -> None:
    # mycka is cloud-backed: Shelly Cloud already returns Gen1 total in Wh, so the
    # tool must NOT ÷60. 548723 Wh == ~549 kWh, the real dishwasher reading (ADR-005).
    out = await shelly_get_status.fn(device="3ce90ed7c30e")
    assert out["gen"] == 1
    ch = out["channels"]["switch:0"]
    assert ch["energy_total_wh"] == 548723.0


async def test_get_status_component_filter_narrows_and_scopes_raw() -> None:
    out = await shelly_get_status.fn(device="80646fe72f38", component="switch:0")
    assert set(out["channels"]) == {"switch:0"}
    assert out["raw"] == TELEVIZE["switch:0"]  # raw scoped to the one component


async def test_list_components_tool() -> None:
    out = await shelly_list_components.fn(device="3ce90ed7c30e")
    assert "relay:0" in out["components"]
    assert "meter:0" in out["components"]


async def test_get_config_masks_device_credentials(wire: Any) -> None:
    """Gen1-style cleartext Wi-Fi/MQTT credentials must never reach the model."""
    out = await shelly_get_config.fn(device="dev")
    assert out["config"]["wifi_sta"] == {"ssid": "homenet", "key": "***"}
    assert out["config"]["mqtt"]["pass"] == "***"
    assert out["config"]["sys"] == {"device": {"name": "fake"}}
