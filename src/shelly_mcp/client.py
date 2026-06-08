"""DeviceRegistry — resolves a device name/id to a live backend, caches identity.

This is the routing seam (the "which transport reaches this device" boundary). The
policy is **local-first**: a device configured with a LAN IP is reached over its local
RPC/REST backend (fast, full-featured, can automate); Shelly Cloud is the off-LAN
fallback (control + live status only). Routing picks the local backend by probing
``GET /shelly`` (Gen2 reports ``gen``; Gen1 doesn't) and caches the result.

The registry owns one shared :class:`CloudClient` for the account (one 1 req/s budget)
and one shared aiohttp session for all local HTTP.
"""

from __future__ import annotations

import aiohttp

from shelly_mcp.backends.base import Backend, BackendError, DeviceUnreachable
from shelly_mcp.backends.cloud import CloudBackend, CloudClient, identity_from_status
from shelly_mcp.backends.local_rest import Gen1RestBackend
from shelly_mcp.backends.local_rpc import Gen2RpcBackend
from shelly_mcp.config import Config, DeviceConfig
from shelly_mcp.models import Capabilities, DeviceIdentity


class DeviceRegistry:
    """Maps device identifiers to backends. One per server process."""

    def __init__(
        self,
        config: Config,
        *,
        cloud_client: CloudClient | None = None,
        http_session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._config = config
        self._cloud = cloud_client  # injected in tests; otherwise built lazily from config
        self._http = http_session  # shared session for local HTTP (injected in tests)
        self._identities: dict[str, DeviceIdentity] = {}
        self._caps: dict[str, Capabilities] = {}
        # Friendly-name -> cloud device id, learned from the fleet listing.
        self._name_to_id: dict[str, str] = {}
        self._local_backends: dict[str, Backend] = {}

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

    # ------------------------------------------------------------------ local
    def _ensure_http(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession()
        return self._http

    async def _probe_gen(self, ip: str, timeout_s: float) -> int:
        """GET /shelly to branch Gen1 vs Gen2 (Gen2 reports ``gen``; Gen1 doesn't)."""
        session = self._ensure_http()
        try:
            async with session.get(
                f"http://{ip}/shelly", timeout=aiohttp.ClientTimeout(total=timeout_s)
            ) as resp:
                info = await resp.json()
        except aiohttp.ClientError as exc:
            raise DeviceUnreachable(f"Local device {ip} unreachable: {exc}") from exc
        return int(info.get("gen", 1)) if isinstance(info, dict) else 1

    async def _build_local(self, name: str, cfg: DeviceConfig) -> Backend:
        """Build (and cache) the right local backend for a configured device with an ip."""
        if name in self._local_backends:
            return self._local_backends[name]
        assert cfg.ip is not None  # only called when ip is set
        timeout = self._config.defaults.timeout_s
        gen = await self._probe_gen(cfg.ip, timeout)
        session = self._ensure_http()
        backend: Backend
        if gen >= 2:
            backend = Gen2RpcBackend(session, cfg.ip, password=cfg.password, timeout_s=timeout)
        else:
            backend = Gen1RestBackend(
                session, cfg.ip, username=cfg.username, password=cfg.password, timeout_s=timeout
            )
        self._local_backends[name] = backend
        return backend

    # --------------------------------------------------------------- resolve
    async def get_backend(self, device: str) -> Backend:
        """Return a backend for ``device`` — local-first, cloud fallback.

        A device configured with a LAN ip is reached locally (full-featured); anything
        else falls back to Shelly Cloud (control + status only).
        """
        cfg = self._config.devices.get(device)
        if cfg is not None and cfg.ip:
            return await self._build_local(device, cfg)
        dev_id = self._name_to_id.get(device, device)
        client = self._ensure_cloud()
        return CloudBackend(client, dev_id, self._friendly_name(dev_id))

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
        if self._http is not None and not self._http.closed:
            await self._http.close()
