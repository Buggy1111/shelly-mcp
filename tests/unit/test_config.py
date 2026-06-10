"""Unit tests for config loading + secret-safety (no device needed)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from shelly_mcp.config import Config, load_config


def test_empty_when_no_file(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.yaml")
    assert isinstance(cfg, Config)
    assert cfg.devices == {}
    assert cfg.defaults.require_confirm is True
    assert cfg.cloud.enabled is False


def test_loads_devices_and_discovery(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "devices:\n"
        "  televize:\n"
        "    ip: 192.168.0.101\n"
        "discovery:\n"
        "  mdns: false\n"
        "  subnets: ['192.168.0.0/24']\n"  # removed option — old configs must still load
    )
    p.chmod(0o600)
    cfg = load_config(p)
    assert cfg.devices["televize"].ip == "192.168.0.101"
    assert cfg.devices["televize"].username == "admin"
    assert cfg.discovery.mdns is False


def test_world_readable_secret_file_is_refused(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("cloud:\n  enabled: true\n  auth_key: SECRET123\n")
    p.chmod(0o644)  # group/world readable + a secret present -> must fail closed
    with pytest.raises(PermissionError, match="chmod 600"):
        load_config(p)


def test_world_readable_without_secret_is_ok(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("devices:\n  led:\n    ip: 192.168.1.116\n")
    p.chmod(0o644)  # no secret -> permissive perms are fine
    cfg = load_config(p)
    assert cfg.devices["led"].ip == "192.168.1.116"


def test_env_overrides_cloud_and_device_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("devices:\n  mycka:\n    ip: 192.168.1.118\n")
    p.chmod(0o600)
    monkeypatch.setenv("SHELLY_CLOUD_AUTH_KEY", "envkey")
    monkeypatch.setenv("SHELLY_PW_mycka", "envpw")
    cfg = load_config(p)
    assert cfg.cloud.auth_key == "envkey"
    assert cfg.cloud.enabled is True  # enabling is implied by providing the key
    assert cfg.devices["mycka"].password == "envpw"


def test_password_not_in_repr(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("devices:\n  x:\n    ip: 1.2.3.4\n    password: topsecret\n")
    p.chmod(0o600)
    cfg = load_config(p)
    assert "topsecret" not in repr(cfg.devices["x"])


def test_non_mapping_yaml_rejected(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("- just\n- a\n- list\n")
    p.chmod(0o600)
    with pytest.raises(ValueError, match="YAML mapping"):
        load_config(p)


def test_default_path_respects_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from shelly_mcp.config import default_config_path

    target = tmp_path / "custom.yaml"
    monkeypatch.setenv("SHELLY_MCP_CONFIG", str(target))
    assert default_config_path() == target
    monkeypatch.delenv("SHELLY_MCP_CONFIG")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_config_path() == tmp_path / "shelly-mcp" / "config.yaml"


def test_secret_file_with_mode_600_passes(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("cloud:\n  enabled: true\n  auth_key: SECRET123\n")
    p.chmod(0o600)
    cfg = load_config(p)
    assert cfg.cloud.auth_key == "SECRET123"
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
