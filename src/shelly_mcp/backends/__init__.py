"""Device backends: the volatile transport/generation boundary (ADR-001/004).

Each backend hides one way of talking to a Shelly device behind a common
``Backend`` protocol, so the tool layer never branches on generation/transport.
"""

from shelly_mcp.backends.base import (
    AuthRequired,
    Backend,
    BackendError,
    DeviceUnreachable,
    UnsupportedOnCloud,
    UnsupportedOnGeneration,
)
from shelly_mcp.backends.cloud import CloudBackend, CloudClient, identity_from_status

__all__ = [
    "Backend",
    "BackendError",
    "AuthRequired",
    "DeviceUnreachable",
    "UnsupportedOnCloud",
    "UnsupportedOnGeneration",
    "CloudBackend",
    "CloudClient",
    "identity_from_status",
]
