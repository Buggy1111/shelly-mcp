# Changelog

All notable changes to `shelly-mcp` are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **Backends:** `CloudBackend` (Shelly Cloud, 1 req/s paced), `Gen2RpcBackend`
  (local `POST /rpc` + RFC 7616 SHA-256 Digest auth), `Gen1RestBackend` (local HTTP
  REST + Basic auth) behind one `Backend` protocol (ADR-006).
- **Normalizer:** Gen1/Gen2/Cloud → canonical `ChannelState`/`LightState`/`CoverState`,
  `None` ≠ fake-zero, transport-aware Gen1 energy units (ADR-005).
- **DeviceRegistry:** local-first routing (configured LAN ip → local, else cloud),
  single-call fleet listing, identity/capability caching.
- **Read tools:** `shelly_discover`, `shelly_list_devices`, `shelly_get_info`,
  `shelly_get_status`, `shelly_get_config`, `shelly_list_components`,
  `shelly_list_methods`.
- **Generic engine:** `shelly_rpc` (read-guarded) + `shelly_rpc_write` (confirm gate +
  data-loss double-gate), with method classification (READ/WRITE/DESTRUCTIVE,
  fail-safe-to-WRITE for unknowns).
- **Control tools:** `shelly_switch_set`/`toggle`, `shelly_light_set`,
  `shelly_cover_move` (Gen1↔Gen2 normalized, audit-logged, post-action state).
- **Energy:** `shelly_energy_live`, `shelly_energy_history` (best-effort/graceful).
- **System (destructive-gated):** `shelly_system_reboot`/`update`/`set_auth`.
- **Schedules:** `shelly_schedule_list`/`create`/`update`/`delete` (timespec + ≤20 +
  per-call validation; delete confirm-gated).
- **MCP resources & prompts:** `shelly://devices`, `shelly://device/{name}/status`;
  `shelly_evening_scene`, `shelly_energy_report`, `shelly_diagnose`.
- **Security:** append-only JSONL audit log with secret redaction; 0600 config
  enforcement; credentials never logged or echoed.

### Notes
- Cloud path is live-verified against real devices. The **local HTTP socket round-trip
  is pending live verification** on a real LAN (WSL mirrored networking) — request
  shaping, digest auth, and routing are unit-tested.
- 142 unit tests; `ruff` + `mypy --strict` clean.
