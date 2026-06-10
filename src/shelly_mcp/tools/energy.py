"""Energy tools — live power/energy readings, normalized across Gen1/Gen2/EM.

``shelly_energy_live`` is the reliable everyday tool (derived from the same normalized
status). ``shelly_energy_history`` degrades gracefully: it surfaces whatever the device
and transport can offer (lifetime totals always; per-minute series when present) and
says so honestly rather than fabricating data.
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.app import backend_errors, mcp, resolve_status

_ENERGY_FIELDS = (
    "power_w", "voltage", "current", "pf", "freq", "energy_total_wh", "ret_energy_total_wh",
)


@mcp.tool(annotations={"readOnlyHint": True})
@backend_errors
async def shelly_energy_live(device: str, channel: int | None = None) -> dict[str, Any]:
    """Live power/energy per channel: power_w, voltage, current, pf, freq, totals.

    ``None`` where a device can't report it (e.g. Gen1 plugs have no voltage/current).
    Pass ``channel`` to narrow to one. Safe, read-only.
    """
    ident, normalized, _ = await resolve_status(device)
    readings: dict[str, dict[str, Any]] = {}
    for key, state in normalized.channels.items():
        if channel is not None and not key.endswith(f":{channel}"):
            continue
        dumped = state.model_dump()
        readings[key] = {field: dumped.get(field) for field in _ENERGY_FIELDS}
    return {"device": ident.id, "gen": int(ident.gen), "readings": readings}


@mcp.tool(annotations={"readOnlyHint": True})
@backend_errors
async def shelly_energy_history(device: str, channel: int | None = None) -> dict[str, Any]:
    """Best-effort energy history: lifetime totals plus any per-minute series the device
    exposes in its status; notes when richer history needs a local connection.

    Detailed historical queries (Pro 3EM ``EMData``/CSV, Gen1 ``em_data.csv``) land with
    the local backends (M2) — over cloud only totals + recent by-minute are available.
    """
    ident, normalized, raw = await resolve_status(device)
    out: dict[str, Any] = {
        "device": ident.id, "gen": int(ident.gen), "channels": {}, "degraded": [],
    }
    for key, state in normalized.channels.items():
        if channel is not None and not key.endswith(f":{channel}"):
            continue
        entry: dict[str, Any] = {"energy_total_wh": state.energy_total_wh}
        by_minute = _by_minute_for(raw, key)
        if by_minute is not None:
            entry["recent_by_minute_wh"] = by_minute
        else:
            out["degraded"].append(key)
        out["channels"][key] = entry
    if out["degraded"]:
        out["note"] = (
            "Only lifetime totals available for some channels over this transport; "
            "per-interval history needs a local connection (M2)."
        )
    return out


def _by_minute_for(raw: dict[str, Any], key: str) -> list[Any] | None:
    """Pull a Gen2 ``aenergy.by_minute`` series for a component key, if present."""
    comp = raw.get(key) if isinstance(raw, dict) else None
    if isinstance(comp, dict):
        aenergy = comp.get("aenergy")
        if isinstance(aenergy, dict):
            by_minute = aenergy.get("by_minute")
            if isinstance(by_minute, list):
                return list(by_minute)
    return None
