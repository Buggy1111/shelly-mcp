"""Device backends: the volatile transport/generation boundary (ADR-001/004).

Each backend hides one way of talking to a Shelly device behind a common
``Backend`` protocol, so the tool layer never branches on generation/transport.

Only the protocol + error types from ``base`` are re-exported here. The concrete
backends (``gen1_rest``/``gen2_rpc``/``cloud``) must be imported from their own
modules: re-exporting them eagerly created a circular import (``methods`` needs
``backends.base``, ``gen1_rest`` needs ``methods``) that made
``import shelly_mcp.methods`` order-dependent.
"""

from shelly_mcp.backends.base import (
    AuthRequired,
    Backend,
    BackendError,
    DeviceUnreachable,
    UnsupportedOnCloud,
    UnsupportedOnGeneration,
)

__all__ = [
    "Backend",
    "BackendError",
    "AuthRequired",
    "DeviceUnreachable",
    "UnsupportedOnCloud",
    "UnsupportedOnGeneration",
]
