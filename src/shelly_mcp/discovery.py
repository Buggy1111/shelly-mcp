"""Device discovery — mDNS (zeroconf) + cloud listing, merged into one device list.

Shelly devices advertise over mDNS (``_shelly._tcp`` for Gen2+, ``_http._tcp`` named
``shelly*`` for Gen1). :func:`discover_mdns` browses for a short window and returns
lightweight identities (ip + name + best-effort generation); richer details come from
a follow-up probe. The cloud account list is always available even off-LAN.

mDNS is inherently network-bound; the parsing/merge logic here is unit-tested, and the
live browse is exercised once on a real LAN (pending WSL mirrored networking).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from zeroconf import ServiceListener, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from shelly_mcp.models import DeviceIdentity, Generation

_SERVICE_TYPES = ["_shelly._tcp.local.", "_http._tcp.local."]


def _ip_from_info(info: AsyncServiceInfo) -> str | None:
    addresses = info.parsed_scoped_addresses() if info else []
    return addresses[0] if addresses else None


def identity_from_mdns(
    name: str, ip: str | None, props: dict[bytes, bytes | None]
) -> DeviceIdentity:
    """Build a lightweight identity from an mDNS service name + TXT properties.

    Gen2+ advertise ``gen`` and ``app`` in TXT records; Gen1 doesn't, so absence of a
    ``gen`` property is treated as Gen1.
    """
    short = name.split(".", 1)[0]
    gen_raw = props.get(b"gen")
    gen = Generation.GEN1
    if gen_raw is not None:
        with contextlib.suppress(ValueError):
            gen = Generation(int(gen_raw))
    app = props.get(b"app")
    return DeviceIdentity(
        id=short.lower(),
        name=short,
        ip=ip,
        gen=gen,
        app=app.decode() if isinstance(app, bytes) else None,
        backend="local_rpc" if gen.is_rpc else "local_rest",
    )


class _ShellyListener(ServiceListener):
    """Collects Shelly service names seen during a browse window."""

    def __init__(self) -> None:
        self.names: set[tuple[str, str]] = set()

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        if name.split(".", 1)[0].lower().startswith("shelly"):
            self.names.add((type_, name))

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self.add_service(zc, type_, name)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        self.names.discard((type_, name))


async def discover_mdns(timeout_s: float = 5.0) -> list[DeviceIdentity]:
    """Browse mDNS for Shelly devices for ``timeout_s`` seconds. Best-effort, never raises."""
    found: list[DeviceIdentity] = []
    try:
        azc = AsyncZeroconf()
    except OSError:
        return found  # no network / mDNS unavailable
    listener = _ShellyListener()
    browser = AsyncServiceBrowser(azc.zeroconf, _SERVICE_TYPES, listener)
    try:
        await asyncio.sleep(timeout_s)
        for type_, name in listener.names:
            info = AsyncServiceInfo(type_, name)
            if await info.async_request(azc.zeroconf, 2000):
                found.append(identity_from_mdns(name, _ip_from_info(info), dict(info.properties)))
    finally:
        await browser.async_cancel()
        await azc.async_close()
    return _dedupe(found)


def merge_discovered(
    mdns: list[DeviceIdentity], cloud: list[DeviceIdentity]
) -> list[DeviceIdentity]:
    """Merge mDNS (has ip) + cloud (has model/online) results, preferring local detail."""
    by_id: dict[str, DeviceIdentity] = {}
    for ident in cloud:
        by_id[ident.id] = ident
    for ident in mdns:  # local wins on ip; keep cloud's model/online if we had it
        existing = by_id.get(ident.id)
        if existing is not None:
            merged = existing.model_copy(update={"ip": ident.ip or existing.ip})
            by_id[ident.id] = merged
        else:
            by_id[ident.id] = ident
    return list(by_id.values())


def _dedupe(devices: list[DeviceIdentity]) -> list[DeviceIdentity]:
    seen: dict[str, DeviceIdentity] = {}
    for d in devices:
        seen.setdefault(d.id, d)
    return list(seen.values())


def _props_str(props: dict[bytes, bytes | None]) -> dict[str, Any]:  # pragma: no cover - debug aid
    return {k.decode(): (v.decode() if isinstance(v, bytes) else v) for k, v in props.items()}
