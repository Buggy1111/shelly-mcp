"""Tests for discovery — mDNS identity parsing + cloud/local merge + the discover tool.

The live mDNS browse is network-bound (pending real LAN); these cover the parse and
merge logic and the tool wiring (with the browse stubbed out, no network, no sleep).
"""

from __future__ import annotations

from typing import Any

import pytest

from shelly_mcp.client import DeviceRegistry
from shelly_mcp.config import Config
from shelly_mcp.discovery import identity_from_mdns, merge_discovered
from shelly_mcp.models import DeviceIdentity, Generation
from shelly_mcp.server import set_registry


def test_identity_from_mdns_gen2_reads_txt() -> None:
    ident = identity_from_mdns(
        "shellyplus1-abc._shelly._tcp.local.", "192.168.0.60", {b"gen": b"2", b"app": b"Plus1"}
    )
    assert ident.gen is Generation.GEN2
    assert ident.ip == "192.168.0.60"
    assert ident.app == "Plus1"
    assert ident.backend == "local_rpc"


def test_identity_from_mdns_gen1_when_no_gen_txt() -> None:
    ident = identity_from_mdns("shelly1-xyz._http._tcp.local.", "192.168.0.50", {})
    assert ident.gen is Generation.GEN1
    assert ident.backend == "local_rest"


def test_merge_prefers_local_ip_keeps_cloud_detail() -> None:
    cloud = [DeviceIdentity(id="abc", gen=Generation.GEN2, model="SNSW-001", online=True)]
    mdns = [DeviceIdentity(id="abc", gen=Generation.GEN2, ip="192.168.0.60")]
    merged = merge_discovered(mdns, cloud)
    assert len(merged) == 1
    assert merged[0].ip == "192.168.0.60"   # local ip filled in
    assert merged[0].model == "SNSW-001"    # cloud detail retained


def test_merge_unions_distinct_devices() -> None:
    cloud = [DeviceIdentity(id="a", gen=Generation.GEN1)]
    mdns = [DeviceIdentity(id="b", gen=Generation.GEN2, ip="10.0.0.2")]
    merged = merge_discovered(mdns, cloud)
    assert {d.id for d in merged} == {"a", "b"}


async def test_discover_tool_merges_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    from shelly_mcp import discovery
    from shelly_mcp.tools.read import shelly_discover

    async def fake_mdns(timeout_s: float = 5.0) -> list[DeviceIdentity]:
        return [DeviceIdentity(id="local1", gen=Generation.GEN2, ip="192.168.0.99")]

    monkeypatch.setattr(discovery, "discover_mdns", fake_mdns)
    set_registry(DeviceRegistry(Config()))  # cloud disabled -> list_devices raises, handled
    try:
        out = await shelly_discover(timeout_s=0.0, use_cloud=False)
    finally:
        set_registry(None)
    assert out["count"] == 1
    assert out["devices"][0]["ip"] == "192.168.0.99"


async def test_discover_tool_handles_cloud_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from shelly_mcp import discovery
    from shelly_mcp.tools.read import shelly_discover

    async def empty_mdns(timeout_s: float = 5.0) -> list[Any]:
        return []

    monkeypatch.setattr(discovery, "discover_mdns", empty_mdns)
    set_registry(DeviceRegistry(Config()))  # cloud not configured -> BackendError swallowed
    try:
        out = await shelly_discover(timeout_s=0.0, use_cloud=True)
    finally:
        set_registry(None)
    assert out["count"] == 0
