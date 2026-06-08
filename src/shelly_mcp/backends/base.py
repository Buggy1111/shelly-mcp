"""The ``Backend`` protocol + exception hierarchy.

A backend is responsible for ONE device over ONE transport. It exposes a raw,
per-generation surface (``get_status``/``call``/...); normalization into canonical
models happens one layer up (``normalize.py``), so backends stay thin and testable.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from shelly_mcp.models import Capabilities, DeviceIdentity


class BackendError(Exception):
    """Base class for all backend failures. Messages are user/LLM-facing and actionable."""


class DeviceUnreachable(BackendError):
    """The device did not respond (timeout, network, offline)."""


class AuthRequired(BackendError):
    """The device needs credentials we don't have, or they were rejected."""


class UnsupportedOnGeneration(BackendError):
    """Capability absent on this device's generation (e.g. Gen1 plugs have no voltage/current)."""


class UnsupportedOnCloud(BackendError):
    """Cloud API can't do this (scripts/schedules/webhooks/KVS/energy-history are local-only)."""


@runtime_checkable
class Backend(Protocol):
    """Common interface over a single device. Implementations: Gen2RpcBackend,
    Gen1RestBackend, CloudBackend.

    All methods are async (device I/O must never block the event loop). ``call`` is
    the generic escape hatch: Gen2+ maps it straight to JSON-RPC; Gen1 translates a
    canonical method name to its REST endpoint; Cloud maps the small supported subset
    and raises :class:`UnsupportedOnCloud` otherwise.
    """

    async def probe(self) -> DeviceIdentity:
        """Identify the device (``GET /shelly``) — cheap, unauthenticated where possible."""
        ...

    async def get_status(self) -> dict[str, Any]:
        """Raw, per-generation full status."""
        ...

    async def get_config(self) -> dict[str, Any]:
        """Raw, per-generation full config."""
        ...

    async def list_components(self) -> list[str]:
        """Component keys present on this device (e.g. ['switch:0', 'input:0'])."""
        ...

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Invoke a (canonical) method. Raises Unsupported* when the device/transport can't."""
        ...

    @property
    def capabilities(self) -> Capabilities:
        """What this device/backend can actually do (computed at onboarding)."""
        ...
