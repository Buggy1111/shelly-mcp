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
from shelly_mcp.backends.gen1_rest import Gen1RestBackend
from shelly_mcp.backends.gen2_rpc import Gen2RpcBackend

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
    "Gen1RestBackend",
    "Gen2RpcBackend",
]
