"""Configuration loading: file + environment, with secret-safety enforced.

Precedence: environment overrides file (per ``04-CONFIG-AND-DEPLOY.md``).
Secrets (device passwords, cloud auth_key) are loaded at runtime and NEVER written
back, logged, or echoed. The config file must be ``0600`` if it contains any
secret — we fail-closed (refuse to load) on a world-readable secret file (A02/A04).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class DeviceConfig(BaseModel):
    ip: str | None = None
    id: str | None = Field(
        default=None,
        description="Shelly Cloud device id (e.g. '3ce90ed7c30e'), for naming cloud-only "
        "devices. The Cloud API doesn't expose device names, so this maps a friendly "
        "config key to its cloud id.",
    )
    password: str | None = Field(default=None, repr=False)  # never shown in repr/logs
    username: str = "admin"  # Gen1 basic-auth / Gen2 digest user


class DiscoveryConfig(BaseModel):
    subnets: list[str] = Field(default_factory=list)
    mdns: bool = True


class CloudConfig(BaseModel):
    enabled: bool = False
    server: str | None = None
    auth_key: str | None = Field(default=None, repr=False)


class Defaults(BaseModel):
    timeout_s: float = 10.0
    require_confirm: bool = True


class Config(BaseModel):
    devices: dict[str, DeviceConfig] = Field(default_factory=dict)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    defaults: Defaults = Field(default_factory=Defaults)


def default_config_path() -> Path:
    """Resolve the config path from ``$SHELLY_MCP_CONFIG`` or the XDG default."""
    env = os.environ.get("SHELLY_MCP_CONFIG")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(base).expanduser() / "shelly-mcp" / "config.yaml"


def _is_world_or_group_readable(path: Path) -> bool:
    mode = path.stat().st_mode
    return bool(mode & (stat.S_IRWXG | stat.S_IRWXO))


def _file_has_secret(data: dict[str, Any]) -> bool:
    if data.get("cloud", {}).get("auth_key"):
        return True
    return any(d.get("password") for d in (data.get("devices") or {}).values())


def load_config(path: Path | None = None) -> Config:
    """Load config from file (if present) then overlay environment secrets.

    Fail-closed: a config file that contains a secret but is not ``0600`` is refused.
    """
    path = path or default_config_path()
    data: dict[str, Any] = {}

    if path.exists():
        raw = yaml.safe_load(path.read_text()) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"Config at {path} must be a YAML mapping, got {type(raw).__name__}")
        data = raw
        if _file_has_secret(data) and _is_world_or_group_readable(path):
            raise PermissionError(
                f"Config {path} contains a secret but is group/world-readable. "
                f"Run: chmod 600 {path}"
            )

    config = Config.model_validate(data)
    _apply_env_overrides(config)
    return config


def _apply_env_overrides(config: Config) -> None:
    """Env wins over file. ``SHELLY_PW_<name>`` per device, ``SHELLY_CLOUD_AUTH_KEY`` for cloud."""
    if key := os.environ.get("SHELLY_CLOUD_AUTH_KEY"):
        config.cloud.auth_key = key
        config.cloud.enabled = True
    if server := os.environ.get("SHELLY_CLOUD_SERVER"):
        config.cloud.server = server
    for name, dev in config.devices.items():
        if pw := os.environ.get(f"SHELLY_PW_{name}"):
            dev.password = pw
