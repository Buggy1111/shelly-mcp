"""Shared fakes for tool-layer tests: a controllable backend + registry, no network.

These let the control/generic/system/schedule tools be exercised against arbitrary
methods (which the real CloudBackend would reject) so the gate, audit, and post-action
logic can be tested directly. The backend records every ``call`` and reflects switch
state so post-action reads are meaningful.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from shelly_mcp.audit import AuditLog
from shelly_mcp.models import Capabilities, DeviceIdentity, Generation
from shelly_mcp.server import set_audit, set_registry


class FakeBackend:
    """Records calls, reflects switch state, returns canned results for everything else."""

    def __init__(self, gen: Generation, status: dict[str, Any]) -> None:
        self.gen = gen
        self._status = status
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._caps = Capabilities()

    async def probe(self) -> DeviceIdentity:
        return DeviceIdentity(id="dev", gen=self.gen, backend="local_rpc")

    async def get_status(self) -> dict[str, Any]:
        return self._status

    async def get_config(self) -> dict[str, Any]:
        return {"sys": {"device": {"name": "fake"}}}

    async def list_components(self) -> list[str]:
        return [k for k in self._status if ":" in k]

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        p = params or {}
        self.calls.append((method, p))
        ch = f"switch:{int(p.get('id', 0))}"
        if method == "Switch.Set" and ch in self._status:
            self._status[ch]["output"] = bool(p.get("on"))
        elif method == "Switch.Toggle" and ch in self._status:
            self._status[ch]["output"] = not self._status[ch].get("output", False)
        elif method == "Schedule.List":
            return {"jobs": self._status.get("_schedules", [])}
        elif method == "Shelly.ListMethods":
            return {"methods": ["Switch.Set", "Shelly.GetStatus"]}
        return {"ok": True}

    @property
    def capabilities(self) -> Capabilities:
        return self._caps


class FakeRegistry:
    """Minimal registry returning one fake backend + identity for every device name."""

    def __init__(self, backend: FakeBackend) -> None:
        self._backend = backend
        self._ident = DeviceIdentity(id="dev", gen=backend.gen, backend="local_rpc")

    async def require_identity(self, device: str) -> DeviceIdentity:
        return self._ident

    async def get_backend(self, device: str) -> FakeBackend:
        return self._backend

    async def list_devices(self) -> list[DeviceIdentity]:
        return [self._ident]

    def capabilities(self, device: str) -> Capabilities:
        return self._backend.capabilities


@pytest.fixture
def gen2_status() -> dict[str, Any]:
    return {
        "switch:0": {"output": True, "apower": 12.0, "voltage": 230.0, "current": 0.05,
                     "aenergy": {"total": 1000.0, "by_minute": [10, 11, 9]}},
        "rgbw:0": {"output": False, "brightness": 50, "rgb": [10, 20, 30], "white": 0},
        "cover:0": {"state": "stopped", "current_pos": 50},
    }


@pytest.fixture
def wire(gen2_status: dict[str, Any], tmp_path: Path) -> Any:
    """Wire a fake registry + temp audit log; yield the backend for assertions."""
    backend = FakeBackend(Generation.GEN2, gen2_status)
    set_registry(FakeRegistry(backend))  # type: ignore[arg-type]
    set_audit(AuditLog(tmp_path / "audit.jsonl"))
    yield backend
    set_registry(None)
    set_audit(None)
