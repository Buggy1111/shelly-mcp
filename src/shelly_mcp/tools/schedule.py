"""Schedule tools — list / create / update / delete device schedules (Gen2+, local-only).

Schedules are automation: they live on the device and only exist over a local
connection (the cloud API can't manage them — the backend raises UnsupportedOnCloud,
surfaced as ``{"error": …}`` by the ``backend_errors`` decorator). Create validates the
timespec grammar (cron 5/6/7 fields, @sunrise/@sunset±offset, shorthands), ≤5 calls,
the ≤20-per-device limit, and every call's method against the
control-method allowlist — a schedule must never become a deferred bypass of the
confirm gates (no ``Shelly.FactoryReset`` at 3am, no ``Script.Eval``; see
docs/03-SECURITY §5.3). Delete is destructive-gated; create/update are audited.
"""

from __future__ import annotations

import re
from typing import Any

from shelly_mcp.app import backend_errors, confirm_refusal, execute_and_audit, get_registry, mcp
from shelly_mcp.methods import Classification, automation_allowed, classify

_MAX_SCHEDULES = 20


_SHORTHANDS = frozenset(
    {"@yearly", "@annually", "@monthly", "@weekly", "@daily", "@midnight", "@hourly"}
)
_SUN_RE = re.compile(r"@(sunrise|sunset)(?:([+-])((?:\d+(?:\.\d+)?[hms]?)+))?", re.IGNORECASE)
_OFFSET_SEGMENT_RE = re.compile(r"(\d+(?:\.\d+)?)([hms]?)")
_UNIT_SECONDS = {"h": 3600, "m": 60, "s": 1, "": 1}
_MAX_SUN_OFFSET_S = 12 * 3600
_MAX_CALLS = 5


def _validate_timespec(timespec: str) -> str | None:
    """Return an error string if the timespec is structurally malformed, else None.

    Mirrors the Gen2+ Schedule grammar: a 5/6/7-field cron expression, a shorthand
    (``@daily``…), ``@random:{…}``, or ``@sunrise``/``@sunset`` with an optional offset
    (max ±12 h) and optional ``day month weekday`` fields. Field *values* are left to the
    device, which is the authority and reports its own error.
    """
    fields = timespec.split()
    if not fields:
        return "timespec is empty"
    head = fields[0]
    if head.lower().startswith("@random:"):
        return None
    if head.lower() in _SHORTHANDS:
        return None if len(fields) == 1 else f"'{head}' takes no further fields"
    if head.startswith("@"):
        sun = _SUN_RE.fullmatch(head)
        if sun is None:
            return (
                f"unknown timespec shorthand '{head}' — use @sunrise/@sunset[+-offset], "
                "@daily-style shorthands, or a 5/6/7-field cron string"
            )
        if sun.group(3):
            seconds = sum(
                float(num) * _UNIT_SECONDS[unit]
                for num, unit in _OFFSET_SEGMENT_RE.findall(sun.group(3))
            )
            if seconds > _MAX_SUN_OFFSET_S:
                hours = seconds / 3600
                return f"sunrise/sunset offset is {hours:g} h — the device allows max ±12 h"
        if len(fields) not in (1, 4):
            return (
                f"'{head}' may be followed only by 'day month weekday' (3 fields), "
                f"got {len(fields) - 1}"
            )
        return None
    if len(fields) not in (5, 6, 7):
        return (
            "timespec must be a cron string with 5 (min hour day month dow), "
            "6 (sec min hour day month dow) or 7 (… year) fields, "
            f"got {len(fields)} fields"
        )
    return None


def _validate_calls(calls: list[dict[str, Any]]) -> str | None:
    """Each scheduled call must be an allowlisted device-control method (no gate bypass)."""
    if not calls or not isinstance(calls, list):
        return "calls must be a non-empty list of {method, params} objects"
    if len(calls) > _MAX_CALLS:
        return f"a schedule can hold at most {_MAX_CALLS} calls (got {len(calls)}) — split it"
    for call in calls:
        method = call.get("method") if isinstance(call, dict) else None
        if not isinstance(method, str):
            return "each call needs a 'method' string"
        if classify(method) is Classification.READ:
            return f"scheduling a read method ('{method}') has no effect — use a control method"
        if not automation_allowed(method):
            return (
                f"'{method}' is not allowed in a schedule — schedules may only call device "
                "control methods (Switch/Light/RGB/RGBW/CCT/Cover). Anything else must go "
                "through its dedicated confirm-gated tool."
            )
    return None


@mcp.tool(annotations={"readOnlyHint": True})
@backend_errors
async def shelly_schedule_list(device: str) -> dict[str, Any]:
    """List the schedules configured on a device. Local-only (cloud can't manage schedules)."""
    backend = await get_registry().get_backend(device)
    result = await backend.call("Schedule.List")
    jobs = result.get("jobs", []) if isinstance(result, dict) else []
    return {"device": device, "schedules": jobs}


@mcp.tool(annotations={"idempotentHint": True})
@backend_errors
async def shelly_schedule_create(
    device: str, timespec: str, calls: list[dict[str, Any]], enable: bool = True
) -> dict[str, Any]:
    """Create a schedule: ``timespec`` + ``calls`` (1-5 × {method, params}).

    ``timespec``: cron ``"sec min hour day month dow"`` (e.g. ``"0 0 22 * * MON-THU"``; 5 or 7
    fields also accepted), a shorthand (``@daily``), or sun-relative ``"@sunset"``,
    ``"@sunset+30m"``, ``"@sunrise-1h * * MON-FRI"`` (offset max ±12 h; the device needs its
    location set). Validates the timespec, ≤5 calls, the ≤20-per-device limit, and each
    call's method. Audit-logged.
    """
    if (err := _validate_timespec(timespec)) is not None:
        return {"error": err}
    if (err := _validate_calls(calls)) is not None:
        return {"error": err}

    backend = await get_registry().get_backend(device)
    existing = await backend.call("Schedule.List")
    count = len(existing.get("jobs", [])) if isinstance(existing, dict) else 0
    if count >= _MAX_SCHEDULES:
        return {"error": f"device already has {count} schedules (max {_MAX_SCHEDULES})"}
    result = await execute_and_audit(
        device, "Schedule.Create", {"enable": enable, "timespec": timespec, "calls": calls}
    )
    return {"device": device, "created": result}


@mcp.tool(annotations={"idempotentHint": True})
@backend_errors
async def shelly_schedule_update(
    device: str,
    id: int,
    timespec: str | None = None,
    calls: list[dict[str, Any]] | None = None,
    enable: bool | None = None,
) -> dict[str, Any]:
    """Update fields of an existing schedule by ``id``. Audit-logged."""
    if timespec is not None and (err := _validate_timespec(timespec)) is not None:
        return {"error": err}
    if calls is not None and (err := _validate_calls(calls)) is not None:
        return {"error": err}

    params: dict[str, Any] = {"id": id}
    for name, value in (("timespec", timespec), ("calls", calls), ("enable", enable)):
        if value is not None:
            params[name] = value
    result = await execute_and_audit(device, "Schedule.Update", params)
    return {"device": device, "updated": result}


@mcp.tool(annotations={"destructiveHint": True})
@backend_errors
async def shelly_schedule_delete(device: str, id: int, confirm: bool = False) -> dict[str, Any]:
    """Delete a schedule by ``id``. Requires ``confirm:true``. Audit-logged."""
    if not confirm:
        return confirm_refusal(device, "Schedule.Delete", {"id": id})
    result = await execute_and_audit(device, "Schedule.Delete", {"id": id})
    return {"device": device, "deleted": result, "confirmed": True}
