"""DeviceRegistry — resolves a device name/id to a live backend, caches identity.

This is the routing seam (the "which transport reaches this device" boundary). The
intended policy is **local-first**: a device with a known LAN IP is reached over its
local RPC/REST backend (fast, full-featured, can automate); Shelly Cloud is the
off-LAN fallback (control + live status only). Local backends arrive in M2 once WSL
mirrored networking is in place — until then the registry routes everything it can
through cloud and raises an actionable error when only-local would be required.

The registry owns one shared :class:`CloudClient` for the whole account so the fleet
shares a single 1 req/s rate budget.
"""

from __future__ import annotations

from shelly_mcp.backends.base import Backend, BackendError
from shelly_mcp.backends.cloud import CloudBackend, CloudClient, identity_from_status
from shelly_mcp.config import Config
from shelly_mcp.models import Capabilities, DeviceIdentity


class DeviceRegistry:
    """Maps device identifiers to backends. One per server process."""

    def __init__(self, config: Config, *, cloud_client: CloudClient | None = None) -> None:
        self._config = config
        self._cloud = cloud_client  # injected in tests; otherwise built lazily from config
        self._identities: dict[str, DeviceIdentity] = {}
        self._caps: dict[str, Capabilities] = {}
        # Friendly-name -> cloud device id, learned from the fleet listing.
        self._name_to_id: dict[str, str] = {}

    # ------------------------------------------------------------------ cloud
    def _ensure_cloud(self) -> CloudClient:
        """Return the shared cloud client, building it from config (fail-closed)."""
        if self._cloud is not None:
            return self._cloud
        cc = self._config.cloud
        if not cc.enabled or not cc.server or not cc.auth_key:
            raise BackendError(
                "This device is only reachable over Shelly Cloud, but cloud is not "
                "configured. Set cloud.server + cloud.auth_key (or SHELLY_CLOUD_* env), "
                "or connect the device locally."
            )
        self._cloud = CloudClient(cc.server, cc.auth_key, timeout_s=self._config.defaults.timeout_s)
        return self._cloud

    # --------------------------------------------------------------- listing
    async def list_devices(self) -> list[DeviceIdentity]:
        """Identify every device in the account from a single ``all_status`` call."""
        client = self._ensure_cloud()
        statuses = await client.all_status()
        devices: list[DeviceIdentity] = []
        for dev_id, status in statuses.items():
            if not isinstance(status, dict):
                continue
            name = self._config_name_for(dev_id)
            ident, caps = identity_from_status(dev_id, status, name)
            self._identities[dev_id] = ident
            self._caps[dev_id] = caps
            if name:
                self._name_to_id[name] = dev_id
            devices.append(ident)
        return devices

    def _config_name_for(self, dev_id: str) -> str | None:
        """Friendly name if the device was configured under its cloud id, else None.

        Cloud status carries no LAN ip, so a richer alias->id match waits for M2 local
        backends (which key naturally on configured name + ip).
        """
        return dev_id if dev_id in self._config.devices else None

    # --------------------------------------------------------------- resolve
    async def get_backend(self, device: str) -> Backend:
        """Return a backend for ``device`` (a cloud id or a configured name).

        Cloud-only for now; the local-first routing lands with M2 local backends.
        """
        dev_id = self._name_to_id.get(device, device)
        client = self._ensure_cloud()
        backend = CloudBackend(client, dev_id, self._friendly_name(dev_id))
        return backend

    async def identify(self, device: str) -> DeviceIdentity:
        """Resolve + probe a single device, caching its identity and capabilities."""
        dev_id = self._name_to_id.get(device, device)
        backend = await self.get_backend(dev_id)
        ident = await backend.probe()
        self._identities[dev_id] = ident
        self._caps[dev_id] = backend.capabilities
        return ident

    def capabilities(self, device: str) -> Capabilities | None:
        """Cached capabilities for a previously-identified device, if any."""
        dev_id = self._name_to_id.get(device, device)
        return self._caps.get(dev_id)

    def _friendly_name(self, dev_id: str) -> str | None:
        ident = self._identities.get(dev_id)
        return ident.name if ident else None

    async def require_identity(self, device: str) -> DeviceIdentity:
        """Identity for a device, from cache or by probing (raises if unreachable)."""
        dev_id = self._name_to_id.get(device, device)
        cached = self._identities.get(dev_id)
        return cached if cached is not None else await self.identify(dev_id)

    async def aclose(self) -> None:
        if self._cloud is not None:
            await self._cloud.aclose()
