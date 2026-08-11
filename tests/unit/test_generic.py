"""Tests for the generic rpc engine — read-guard, confirm gate, data-loss double-gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shelly_mcp.tools.generic import shelly_list_methods, shelly_rpc, shelly_rpc_write


async def test_rpc_allows_read_method(wire: Any) -> None:
    out = await shelly_rpc(device="dev", method="Shelly.GetStatus")
    assert "error" not in out
    assert ("Shelly.GetStatus", {}) in wire.calls


async def test_rpc_rejects_write_method(wire: Any) -> None:
    out = await shelly_rpc(device="dev", method="Switch.Set", params={"on": True})
    assert "error" in out
    assert "shelly_rpc_write" in out["error"]
    assert wire.calls == []  # never reached the device


async def test_rpc_write_refuses_without_confirm(wire: Any) -> None:
    out = await shelly_rpc_write(
        device="dev", method="Switch.Set", params={"id": 0, "on": False}
    )
    assert out["confirmed"] is False
    assert out["would_call"]["method"] == "Switch.Set"
    assert wire.calls == []  # gate held — nothing executed


async def test_rpc_write_executes_with_confirm(wire: Any) -> None:
    out = await shelly_rpc_write(
        device="dev", method="Switch.Set", params={"id": 0, "on": False}, confirm=True
    )
    assert out["confirmed"] is True
    assert ("Switch.Set", {"id": 0, "on": False}) in wire.calls


async def test_rpc_write_rejects_read_method(wire: Any) -> None:
    out = await shelly_rpc_write(device="dev", method="Shelly.GetStatus", confirm=True)
    assert "error" in out
    assert "shelly_rpc" in out["error"]
    assert wire.calls == []


async def test_destructive_needs_data_loss_ack(wire: Any) -> None:
    # confirm alone is not enough for an irreversible method.
    out = await shelly_rpc_write(device="dev", method="Shelly.FactoryReset", confirm=True)
    assert out["confirmed"] is False
    assert out["destructive"] is True
    assert wire.calls == []


async def test_destructive_executes_with_both_gates(wire: Any) -> None:
    out = await shelly_rpc_write(
        device="dev",
        method="Shelly.FactoryReset",
        params={"i_understand_data_loss": True},
        confirm=True,
    )
    assert out["confirmed"] is True
    # The internal ack flag is stripped before the device call.
    method, params = wire.calls[-1]
    assert method == "Shelly.FactoryReset"
    assert "i_understand_data_loss" not in params


async def test_rpc_write_audits(wire: Any, tmp_path: Path) -> None:
    await shelly_rpc_write(device="dev", method="Switch.Set", params={"on": True}, confirm=True)
    lines = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert any(e["method"] == "Switch.Set" for e in lines)


async def test_list_methods(wire: Any) -> None:
    out = await shelly_list_methods(device="dev")
    assert "Switch.Set" in out["methods"]
