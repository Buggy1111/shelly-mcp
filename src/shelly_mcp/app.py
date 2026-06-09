"""Application core: the FastMCP instance + shared registry/audit state + helpers.

Tool modules (``tools/*.py``) import ``mcp`` from here and register their tools, so
the server is organised as vertical slices (read / control / energy / schedule /
system / generic) without a circular import back through ``server.py``.

The registry and audit log are process-global and lazily built from config; tests
inject fakes via :func:`set_registry` / :func:`set_audit` so no tool needs a network
or a real filesystem to be exercised.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec

from fastmcp import FastMCP

from shelly_mcp import __version__
from shelly_mcp.audit import AuditLog
from shelly_mcp.backends.base import BackendError
from shelly_mcp.client import DeviceRegistry
from shelly_mcp.config import load_config
from shelly_mcp.models import DeviceIdentity
from shelly_mcp.normalize import NormalizedStatus, Normalizer

mcp: FastMCP = FastMCP(
    name="shelly-mcp",
    version=__version__,
    instructions=(
        "Control and automate Shelly smart-home devices (Gen1-Gen4 + BLU), local-first. "
        "Read tools are safe; the generic write tool and destructive system tools require "
        "confirm:true (a hijacked LLM still can't silently destroy). To act on a room "
        "(e.g. 'turn off the kitchen'), call shelly_list_devices, filter by each device's "
        "'location', then act on those devices. For a repeated multi-device routine, define "
        "a named scene once (shelly_scene_create) and run it deterministically afterwards "
        "(shelly_scene_run) — same result every time, schedulable from any client. Unofficial "
        "community project, not affiliated with Allterco/Shelly."
    ),
)

_registry: DeviceRegistry | None = None
_audit: AuditLog | None = None


def get_registry() -> DeviceRegistry:
    global _registry
    if _registry is None:
        _registry = DeviceRegistry(load_config())
    return _registry


def set_registry(registry: DeviceRegistry | None) -> None:
    global _registry
    _registry = registry


def get_audit() -> AuditLog:
    global _audit
    if _audit is None:
        _audit = AuditLog()
    return _audit


def set_audit(audit: AuditLog | None) -> None:
    global _audit
    _audit = audit


async def resolve_status(device: str) -> tuple[DeviceIdentity, NormalizedStatus, dict[str, Any]]:
    """Identify a device and return its (identity, normalized status, raw status)."""
    registry = get_registry()
    ident = await registry.require_identity(device)
    backend = await registry.get_backend(device)
    raw = await backend.get_status()
    normalized = Normalizer.normalize_status(
        raw, ident.gen, backend=ident.backend or "local_rest"
    )
    return ident, normalized, raw


async def execute_and_audit(
    device: str, method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run a mutating backend call and audit-log the outcome (ok or error)."""
    backend = await get_registry().get_backend(device)
    try:
        result = await backend.call(method, params)
    except BackendError as exc:
        get_audit().record(device=device, method=method, params=params, ok=False, error=str(exc))
        raise
    get_audit().record(device=device, method=method, params=params, ok=True, result=result)
    return result


_P = ParamSpec("_P")


def backend_errors(
    fn: Callable[_P, Awaitable[dict[str, Any]]],
) -> Callable[_P, Awaitable[dict[str, Any]]]:
    """Turn a ``BackendError`` raised inside a tool into a uniform ``{"error": msg}`` dict.

    Saves every device-touching tool from repeating ``try/except BackendError``. Apply it
    **under** ``@mcp.tool`` so FastMCP still introspects the real signature (``functools.wraps``
    preserves it). Only ``BackendError`` is caught — real bugs still surface. Tools that need
    partial results (e.g. ``scene_run``'s per-action loop) catch errors themselves and are not
    decorated.
    """

    @functools.wraps(fn)
    async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> dict[str, Any]:
        try:
            return await fn(*args, **kwargs)
        except BackendError as exc:
            return {"error": str(exc)}

    return wrapper


def confirm_refusal(device: str, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """Structured preview returned when a gated tool is called without ``confirm:true``.

    The human (not just the LLM) must decide — so we describe the action and refuse
    rather than perform it (docs/03-SECURITY §5.2).
    """
    return {
        "confirmed": False,
        "would_call": {"device": device, "method": method, "params": params or {}},
        "message": (
            f"This is a mutating action on '{device}'. Re-call with confirm=true to proceed."
        ),
    }
