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
from shelly_mcp.backends.gen1_rest import Gen1RestBackend
from shelly_mcp.backends.gen2_rpc import Gen2RpcBackend
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
        # Friendly-name (+ aliases) -> cloud device id. Seeded from config (the Cloud API
        # doesn't expose device names) and extended by the fleet listing.
        self._name_to_id: dict[str, str] = {}
        # cloud-id -> (friendly name, location) to overlay onto probed identities.
        self._id_meta: dict[str, tuple[str, str | None]] = {}
        for name, cfg in config.devices.items():
            if cfg.id:
                self._name_to_id[name] = cfg.id
                for alias in cfg.aliases:
                    self._name_to_id[alias] = cfg.id
                self._id_meta[cfg.id] = (name, cfg.location)
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
            ident, caps = identity_from_status(dev_id, status)
            ident = self._overlay_meta(ident)
            self._identities[dev_id] = ident
            self._caps[dev_id] = caps
            devices.append(ident)
        return devices

    def _overlay_meta(self, ident: DeviceIdentity) -> DeviceIdentity:
        """Apply the configured friendly name + location to a probed identity."""
        meta = self._id_meta.get(ident.id)
        if meta is None:
            return ident
        name, location = meta
        return ident.model_copy(update={"name": name, "location": location})

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
        """Probe a device (by the original name, so local-first routing holds) and cache it."""
        backend = await self.get_backend(device)  # original string → local routing preserved
        ident = self._overlay_for(device, await backend.probe())
        self._identities[ident.id] = ident
        self._caps[ident.id] = backend.capabilities
        if device != ident.id:
            self._name_to_id.setdefault(device, ident.id)
        return ident

    def _overlay_for(self, device: str, ident: DeviceIdentity) -> DeviceIdentity:
        """Overlay configured name + location, by cloud id and by the requested config key."""
        name: str | None = None
        location: str | None = None
        meta = self._id_meta.get(ident.id)
        if meta is not None:
            name, location = meta
        cfg = self._config.devices.get(device)
        if cfg is not None:
            name = device
            location = cfg.location or location
        if name is None and location is None:
            return ident
        return ident.model_copy(update={"name": name or ident.name, "location": location})

    def capabilities(self, device: str) -> Capabilities | None:
        """Cached capabilities for a previously-identified device, if any."""
        dev_id = self._name_to_id.get(device, device)
        return self._caps.get(dev_id) or self._caps.get(device)

    def _friendly_name(self, dev_id: str) -> str | None:
        ident = self._identities.get(dev_id)
        return ident.name if ident else None

    def known_devices(self) -> set[str]:
        """Every name a scene/tool may reference: config keys + aliases + cloud-id map.

        Purely local (no network) — used to validate scene actions at create time so a
        typo'd device name is caught immediately rather than only failing at run time.
        """
        names: set[str] = set(self._config.devices)
        for cfg in self._config.devices.values():
            names.update(cfg.aliases)
        names.update(self._name_to_id)
        return names

    async def require_identity(self, device: str) -> DeviceIdentity:
        """Identity for a device, from cache or by probing (raises if unreachable)."""
        dev_id = self._name_to_id.get(device, device)
        cached = self._identities.get(dev_id) or self._identities.get(device)
        return cached if cached is not None else await self.identify(device)

    async def aclose(self) -> None:
        if self._cloud is not None:
            await self._cloud.aclose()
        if self._http is not None and not self._http.closed:
            await self._http.close()
