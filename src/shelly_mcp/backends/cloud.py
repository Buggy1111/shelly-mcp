"""Cloud backend — Shelly Cloud Control API (off-LAN fallback).

The cloud surface is deliberately thin (ADR-004): control + live status only. It
**cannot** do scripts/schedules/webhooks/KVS or energy history — those raise
:class:`UnsupportedOnCloud`. The cloud API is also rate-limited to ~1 req/s per
account, so :class:`CloudClient` paces requests.

The account-wide ``auth_key`` is a secret: never logged, never echoed.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from shelly_mcp.backends.base import (
    AuthRequired,
    BackendError,
    DeviceUnreachable,
    UnsupportedOnCloud,
)
from shelly_mcp.models import Capabilities, DeviceIdentity, Generation

_MIN_INTERVAL_S = 1.0  # Shelly Cloud: "limited to 1 request per second"
_GEN_MAP = {"G1": Generation.GEN1, "G2": Generation.GEN2}


class CloudClient:
    """Shared, account-wide Shelly Cloud client. One per ``auth_key``.

    Holds the aiohttp session and a 1 req/s pacer. Reused by every
    :class:`CloudBackend` so the whole fleet shares one rate budget.
    """

    def __init__(
        self,
        server: str,
        auth_key: str,
        *,
        timeout_s: float = 10.0,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        if not server or not auth_key:
            raise AuthRequired("Cloud backend needs both a server host and an auth_key")
        self._server = server.replace("https://", "").replace("http://", "").rstrip("/")
        self._auth_key = auth_key
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._session = session
        self._owns_session = session is None
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            self._owns_session = True
        return self._session

    async def post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        """POST a form body to the cloud, with auth_key injected and 1 req/s pacing."""
        body = {k: str(v) for k, v in data.items() if v is not None}
        body["auth_key"] = self._auth_key
        url = f"https://{self._server}{endpoint}"
        session = await self._ensure_session()

        async with self._lock:
            wait = _MIN_INTERVAL_S - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with session.post(url, data=body) as resp:
                    if resp.status == 401:
                        raise AuthRequired("Shelly Cloud rejected the auth_key (401)")
                    if resp.status >= 500:
                        raise DeviceUnreachable(f"Shelly Cloud server error ({resp.status})")
                    payload: dict[str, Any] = await resp.json()
            except aiohttp.ClientError as exc:
                raise DeviceUnreachable(f"Shelly Cloud request failed: {exc}") from exc
            finally:
                self._last_call = time.monotonic()

        if not payload.get("isok", False):
            raise BackendError(f"Shelly Cloud returned an error: {payload.get('errors')}")
        data = payload.get("data", {})
        return data if isinstance(data, dict) else {}

    async def all_status(self, *, show_info: bool = True) -> dict[str, Any]:
        """Whole-account status in one call (coalesced fleet read)."""
        data = await self.post(
            "/device/all_status",
            {"show_info": "true" if show_info else None, "no_shared": "true"},
        )
        result = data.get("devices_status", {})
        return result if isinstance(result, dict) else {}

    async def device_status(self, device_id: str) -> dict[str, Any]:
        data = await self.post("/device/status", {"id": device_id})
        status = data.get("device_status", {})
        return status if isinstance(status, dict) else {}

    async def aclose(self) -> None:
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()


def _component_keys(status: dict[str, Any]) -> list[str]:
    """Derive component keys from a cloud status payload (Gen1 + Gen2 shapes)."""
    keys: list[str] = []
    for key in status:
        if ":" in key and not key.startswith("_"):
            keys.append(key)
    # Gen1 arrays -> synthesise canonical-ish keys
    for arr, comp in (("relays", "relay"), ("meters", "meter"), ("lights", "light"),
                      ("rollers", "roller")):
        items = status.get(arr)
        if isinstance(items, list):
            keys.extend(f"{comp}:{i}" for i in range(len(items)))
    return sorted(set(keys))


def _has_field(status: dict[str, Any], field: str) -> bool:
    """True if any component (Gen2 dict value) or Gen1 array element carries ``field``."""
    for val in status.values():
        if isinstance(val, dict) and field in val:
            return True
    for arr in ("meters", "emeters", "relays"):
        items = status.get(arr)
        if isinstance(items, list) and any(isinstance(it, dict) and field in it for it in items):
            return True
    return False


def identity_from_status(
    device_id: str, status: dict[str, Any], name: str | None = None
) -> tuple[DeviceIdentity, Capabilities]:
    """Build identity + capabilities from one device's cloud status payload.

    Shared by :meth:`CloudBackend.probe` and the registry's fleet listing so the
    latter can identify every device from a *single* ``all_status`` call instead of
    one rate-limited round-trip per device.
    """
    info = status.get("_dev_info", {})
    gen = _GEN_MAP.get(str(info.get("gen")), Generation.GEN2)
    caps = Capabilities(
        can_automate=False,  # cloud can never automate
        has_energy=_has_field(status, "apower") or _has_field(status, "power"),
        has_voltage_current=_has_field(status, "voltage"),
        components=_component_keys(status),
    )
    ident = DeviceIdentity(
        id=device_id,
        name=name,
        gen=gen,
        model=info.get("code"),
        online=bool(info.get("online", True)),
        backend="cloud",
    )
    return ident, caps


class CloudBackend:
    """One device, reached over Shelly Cloud. Implements the :class:`Backend` protocol."""

    def __init__(self, client: CloudClient, device_id: str, name: str | None = None) -> None:
        self._client = client
        self._id = device_id
        self._name = name
        self._caps = Capabilities()  # populated by probe()

    async def probe(self) -> DeviceIdentity:
        statuses = await self._client.all_status()
        status = statuses.get(self._id)
        if status is None:
            raise DeviceUnreachable(f"Device '{self._id}' not found in this Shelly Cloud account")
        ident, self._caps = identity_from_status(self._id, status, self._name)
        return ident

    async def get_status(self) -> dict[str, Any]:
        return await self._client.device_status(self._id)

    async def get_config(self) -> dict[str, Any]:
        raise UnsupportedOnCloud(
            "The Shelly Cloud API does not expose device config — use a local connection"
        )

    async def list_components(self) -> list[str]:
        return _component_keys(await self.get_status())

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        p = params or {}
        channel = int(p.get("id", 0))

        if method in ("Shelly.GetStatus", "Switch.GetStatus", "Light.GetStatus"):
            return await self.get_status()

        if method in ("Switch.Set", "Switch.Toggle"):
            turn = "toggle" if method == "Switch.Toggle" else ("on" if p.get("on") else "off")
            return await self._client.post(
                "/device/relay/control", {"id": self._id, "channel": channel, "turn": turn}
            )

        if method in ("Light.Set", "RGB.Set", "RGBW.Set", "CCT.Set"):
            data: dict[str, Any] = {"id": self._id, "channel": channel}
            if "on" in p:
                data["turn"] = "on" if p["on"] else "off"
            rgb = p.get("rgb")
            if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
                data["red"], data["green"], data["blue"] = rgb
            if "white" in p:
                data["white"] = p["white"]
            if "brightness" in p:
                # cloud uses 'gain' for colour, 'brightness' for plain dimmers
                data["gain" if rgb else "brightness"] = p["brightness"]
            return await self._client.post("/device/light/control", data)

        if method in ("Cover.Open", "Cover.Close", "Cover.Stop"):
            direction = {"Cover.Open": "open", "Cover.Close": "close", "Cover.Stop": "stop"}[method]
            return await self._client.post(
                "/device/relay/roller/control",
                {"id": self._id, "channel": channel, "direction": direction},
            )

        if method == "Cover.GoToPosition":
            return await self._client.post(
                "/device/relay/roller/control",
                {"id": self._id, "channel": channel, "pos": p.get("pos")},
            )

        raise UnsupportedOnCloud(
            f"'{method}' is not available over Shelly Cloud — connect to the device locally"
        )

    @property
    def capabilities(self) -> Capabilities:
        return self._caps
