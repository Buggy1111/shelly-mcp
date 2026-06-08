"""Gen1 local backend — raw HTTP REST over the LAN (ADR-006).

Gen1 devices speak a simple HTTP API: ``GET /status``, ``GET /settings``,
``GET /relay/0?turn=on`` … with optional HTTP **Basic** auth. We talk to it directly
with aiohttp (Basic auth is built in) rather than dragging in aioshelly's CoAP stack —
CoAP only matters for push events, which are a v1.1 concern. Control methods are
translated to Gen1 URLs by :func:`shelly_mcp.methods.gen1_rest_for`.
"""

from __future__ import annotations

from typing import Any

import aiohttp

from shelly_mcp.backends.base import AuthRequired, DeviceUnreachable
from shelly_mcp.methods import gen1_rest_for
from shelly_mcp.models import Capabilities, DeviceIdentity, Generation


def _gen1_component_keys(status: dict[str, Any]) -> list[str]:
    """Synthesise component keys from Gen1 status arrays (relays/meters/lights/rollers)."""
    keys: list[str] = []
    for arr, comp in (("relays", "relay"), ("meters", "meter"), ("emeters", "emeter"),
                      ("lights", "light"), ("rollers", "roller")):
        items = status.get(arr)
        if isinstance(items, list):
            keys.extend(f"{comp}:{i}" for i in range(len(items)))
    return keys


class Gen1RestBackend:
    """One Gen1 device reached over its local HTTP API. Implements the Backend protocol."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        ip: str,
        *,
        username: str = "admin",
        password: str | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._session = session
        self._ip = ip
        self._auth = aiohttp.BasicAuth(username, password) if password else None
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._caps = Capabilities()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"http://{self._ip}{path}"
        try:
            async with self._session.get(
                url, params=params, auth=self._auth, timeout=self._timeout
            ) as resp:
                if resp.status == 401:
                    raise AuthRequired(
                        f"Gen1 device {self._ip} requires a password — set it in config "
                        f"(devices.<name>.password)."
                    )
                if resp.status >= 500:
                    raise DeviceUnreachable(f"Gen1 device {self._ip} error ({resp.status})")
                data: dict[str, Any] = await resp.json()
                return data
        except aiohttp.ClientError as exc:
            raise DeviceUnreachable(f"Gen1 device {self._ip} unreachable: {exc}") from exc

    async def probe(self) -> DeviceIdentity:
        info = await self._get("/shelly")
        status = await self._get("/status")
        self._caps = Capabilities(
            can_automate=True,  # local Gen1 supports actions/timers
            has_energy=any(isinstance(status.get(a), list) for a in ("meters", "emeters")),
            has_voltage_current=any(
                isinstance(m, dict) and "voltage" in m for m in status.get("emeters", []) or []
            ),
            components=_gen1_component_keys(status),
        )
        return DeviceIdentity(
            id=str(info.get("mac", self._ip)).lower(),
            ip=self._ip,
            gen=Generation.GEN1,
            model=info.get("type"),
            mac=info.get("mac"),
            fw=info.get("fw"),
            auth_needed=bool(info.get("auth", False)),
            backend="local_rest",
        )

    async def get_status(self) -> dict[str, Any]:
        return await self._get("/status")

    async def get_config(self) -> dict[str, Any]:
        return await self._get("/settings")

    async def list_components(self) -> list[str]:
        return _gen1_component_keys(await self._get("/status"))

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        path, query = gen1_rest_for(method, params)  # raises UnsupportedOnGeneration if no map
        return await self._get(path, query)

    @property
    def capabilities(self) -> Capabilities:
        return self._caps
