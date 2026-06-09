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
- **Scenes (ADR-007):** `shelly_scene_list`/`get`/`run`/`create`/`delete` — server-side
  named, deterministic, schedulable multi-device routines stored in a dedicated
  `scenes.yaml` (atomic write, fail-soft read). Reuses `execute_and_audit`; best-effort
  sequential run with per-action `ok|partial|failed` results; create rejects READ and
  DESTRUCTIVE methods and unknown devices, warns on non-idempotent `Toggle`.
- **Automation tools (Gen2+ local-only):** `shelly_kvs_*` (get/set/list/delete),
  `shelly_webhook_*` (list/create/update/delete), `shelly_script_*` (list/get_code/create/
  put_code/start/stop/eval/delete — chunked `PutCode`, reassembled `GetCode`),
  `shelly_virtual_*` (list/add/delete). Deletes are confirm-gated; the arbitrary-code
  paths (`script_put_code`, `script_eval`) are confirm-gated (ASI05/LLM05). KVS round-trip
  + confirm gate live-verified on real Gen2 hardware.
- **MCP resources & prompts:** `shelly://devices`, `shelly://device/{name}/status`;
  `shelly_evening_scene`, `shelly_energy_report`, `shelly_diagnose`.
- **Security:** append-only JSONL audit log with secret redaction; 0600 config
  enforcement; credentials never logged or echoed.

### Notes
- **Live-verified (2026-06-09) on real hardware:** cloud path against all 4 devices, and
  the **local** path end-to-end — Gen2 `POST /rpc` (Plus Plug S, Plus RGBW PM, Plus 1PM
  Mini) and Gen1 REST (`SHPLG-S`) — once the fleet was flattened onto one subnet. Closes
  the ADR-006 local-socket caveat. Still to re-confirm: the Gen1 local Wmin energy path
  against the Shelly app.
- 199 unit tests; `ruff` + `mypy --strict` clean.
