"""Schedule tools — list / create / update / delete device schedules (Gen2+, local-only).

Schedules are automation: they live on the device and only exist over a local
connection (the cloud API can't manage them — the backend raises UnsupportedOnCloud,
surfaced as ``{"error": …}`` by the ``backend_errors`` decorator). Create validates the
6-field cron timespec, the ≤20-per-device limit, and every call's method against the
control-method allowlist — a schedule must never become a deferred bypass of the
confirm gates (no ``Shelly.FactoryReset`` at 3am, no ``Script.Eval``; see
docs/03-SECURITY §5.3). Delete is destructive-gated; create/update are audited.
"""

from __future__ import annotations

from typing import Any

from shelly_mcp.app import backend_errors, confirm_refusal, execute_and_audit, get_registry, mcp
from shelly_mcp.methods import Classification, automation_allowed, classify

_MAX_SCHEDULES = 20


def _validate_timespec(timespec: str) -> str | None:
    """Return an error string if the 6-field cron timespec is malformed, else None."""
    fields = timespec.split()
    if len(fields) != 6:
        return (
            "timespec must be a 6-field cron string (sec min hour day month dow), "
            f"got {len(fields)} fields"
        )
    return None


def _validate_calls(calls: list[dict[str, Any]]) -> str | None:
    """Each scheduled call must be an allowlisted device-control method (no gate bypass)."""
    if not calls or not isinstance(calls, list):
        return "calls must be a non-empty list of {method, params} objects"
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
    """Create a schedule: ``timespec`` 6-field cron, ``calls`` list of {method, params}.

    Validates the timespec, the ≤20-per-device limit, and each call's method. Audit-logged.
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
