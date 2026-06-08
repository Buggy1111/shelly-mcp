"""Gen2+ local backend — raw JSON-RPC over HTTP ``POST /rpc`` (ADR-006).

Gen2/3/4 devices expose every method at ``POST http://<ip>/rpc`` with a
``{"id","method","params"}`` body. Auth, when enabled, is HTTP **Digest** (SHA-256,
``qop=auth``, user ``admin``). We implement that directly rather than opening
aioshelly's WebSocket/WsServer stack — WS only buys push events, which are a v1.1
concern; for request/response this HTTP path is simpler and fully testable.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

import aiohttp

from shelly_mcp.backends.base import AuthRequired, BackendError, DeviceUnreachable
from shelly_mcp.models import Capabilities, DeviceIdentity, Generation

_GEN2_USER = "admin"  # Gen2 digest user is always 'admin'


def _parse_challenge(header: str) -> dict[str, str]:
    """Parse a ``WWW-Authenticate: Digest ...`` header into its key=value parts."""
    scheme, _, rest = header.partition(" ")
    if scheme.lower() != "digest":
        return {}
    parts: dict[str, str] = {}
    for token in rest.split(","):
        key, _, value = token.strip().partition("=")
        parts[key.strip()] = value.strip().strip('"')
    return parts


def digest_authorization(
    challenge: dict[str, str], *, user: str, password: str, method: str, uri: str, cnonce: str
) -> str:
    """Compute an RFC 7616 SHA-256 Digest ``Authorization`` header value.

    Pure + deterministic given ``cnonce`` (so it's unit-testable against a vector).
    """
    realm = challenge.get("realm", "")
    nonce = challenge.get("nonce", "")
    qop = challenge.get("qop", "auth")
    nc = "00000001"

    def h(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    ha1 = h(f"{user}:{realm}:{password}")
    ha2 = h(f"{method}:{uri}")
    response = h(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}")
    return (
        f'Digest username="{user}", realm="{realm}", nonce="{nonce}", uri="{uri}", '
        f'qop={qop}, nc={nc}, cnonce="{cnonce}", response="{response}", algorithm=SHA-256'
    )


class Gen2RpcBackend:
    """One Gen2+ device reached over local HTTP JSON-RPC. Implements the Backend protocol."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        ip: str,
        *,
        password: str | None = None,
        timeout_s: float = 10.0,
        port: int = 80,
    ) -> None:
        self._session = session
        self._ip = ip
        self._port = port
        self._password = password
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._caps = Capabilities()
        self._challenge: dict[str, str] = {}

    @property
    def _url(self) -> str:
        return f"http://{self._ip}:{self._port}/rpc"

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Invoke any RPC method, handling a Digest auth challenge transparently."""
        body = {"id": 1, "method": method, "params": params or {}}
        result = await self._post(body, auth_header=None)
        if result is _AUTH_CHALLENGE:
            if not self._password:
                raise AuthRequired(
                    f"Gen2 device {self._ip} requires a password — set it in config "
                    f"(devices.<name>.password)."
                )
            header = digest_authorization(
                self._challenge,
                user=_GEN2_USER,
                password=self._password,
                method="POST",
                uri="/rpc",
                cnonce=secrets.token_hex(8),
            )
            result = await self._post(body, auth_header=header)
            if result is _AUTH_CHALLENGE:
                raise AuthRequired(f"Gen2 device {self._ip} rejected the password.")
        assert isinstance(result, dict)  # not the sentinel once we get here
        return result

    async def _post(
        self, body: dict[str, Any], *, auth_header: str | None
    ) -> dict[str, Any] | object:
        headers = {"Authorization": auth_header} if auth_header else {}
        try:
            async with self._session.post(
                self._url, json=body, headers=headers, timeout=self._timeout
            ) as resp:
                if resp.status == 401:
                    self._challenge = _parse_challenge(resp.headers.get("WWW-Authenticate", ""))
                    return _AUTH_CHALLENGE
                if resp.status >= 500:
                    raise DeviceUnreachable(f"Gen2 device {self._ip} error ({resp.status})")
                payload: dict[str, Any] = await resp.json()
        except aiohttp.ClientError as exc:
            raise DeviceUnreachable(f"Gen2 device {self._ip} unreachable: {exc}") from exc
        if "error" in payload:
            raise BackendError(f"RPC error from {self._ip}: {payload['error']}")
        result = payload.get("result", {})
        return result if isinstance(result, dict) else {}

    async def probe(self) -> DeviceIdentity:
        info = await self.call("Shelly.GetDeviceInfo")
        comps = await self.list_components()
        status = await self.get_status()
        self._caps = Capabilities(
            can_automate=True,  # local Gen2 supports scripts/schedules/webhooks/KVS
            has_energy=any(isinstance(v, dict) and "apower" in v for v in status.values()),
            has_voltage_current=any(
                isinstance(v, dict) and "voltage" in v for v in status.values()
            ),
            components=comps,
        )
        gen_value = int(info.get("gen", 2))
        return DeviceIdentity(
            id=str(info.get("id", self._ip)),
            ip=self._ip,
            gen=Generation(gen_value if gen_value in (2, 3, 4) else 2),
            model=info.get("model"),
            mac=info.get("mac"),
            app=info.get("app"),
            fw=info.get("fw_id") or info.get("ver"),
            auth_needed=bool(info.get("auth_en", False)),
            backend="local_rpc",
        )

    async def get_status(self) -> dict[str, Any]:
        return await self.call("Shelly.GetStatus")

    async def get_config(self) -> dict[str, Any]:
        return await self.call("Shelly.GetConfig")

    async def list_components(self) -> list[str]:
        result = await self.call("Shelly.GetComponents")
        comps = result.get("components", []) if isinstance(result, dict) else []
        return [c["key"] for c in comps if isinstance(c, dict) and "key" in c]

    @property
    def capabilities(self) -> Capabilities:
        return self._caps


# Sentinel: a 401 came back and the challenge was stashed on the backend.
_AUTH_CHALLENGE = object()
