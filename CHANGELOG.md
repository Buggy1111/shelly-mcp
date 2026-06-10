# Changelog

All notable changes to `shelly-mcp` are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [0.1.1] — 2026-06-10

### Fixed
- MCP Registry ownership marker (`mcp-name: io.github.Buggy1111/shelly-mcp`) added to the
  README so the Registry can verify the PyPI package; Registry `server.json` description
  shortened to the 100-char limit. No code changes.

## [0.1.0] — 2026-06-10

Initial public release.

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
  sequential run with per-action `ok|partial|failed` results; create accepts only the
  control-method allowlist (see Security below) and known devices, warns on
  non-idempotent `Toggle`.
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

### Security (pre-launch audit, 2026-06-10)
- **Scenes and schedules accept only the control-method allowlist**
  (`Switch/Light/RGB/RGBW/CCT/Cover`). Previously a schedule accepted any non-READ method —
  `shelly_schedule_create(calls=[{"method": "Shelly.FactoryReset"}])` would arm a deferred
  factory reset past *both* confirm gates — and a scene accepted any non-destructive WRITE,
  including `Script.Eval` and `Shelly.SetAuth`. Anything off the allowlist must go through
  its dedicated confirm-gated tool, live (docs/03-SECURITY §5.3).
- **`shelly_get_config` masks credential fields** before the config reaches the model —
  Gen1 `/settings` returns the Wi-Fi PSK and MQTT/login passwords in cleartext.
- **Webhook URLs must be absolute http(s)** — the device calls them on events; LAN targets
  stay allowed, other schemes are refused.

### Fixed
- **Latent circular import:** `import shelly_mcp.methods` as a process's first import crashed
  (`backends/__init__` eagerly re-exported concrete backends). The package now re-exports only
  the protocol + error types; each module is regression-tested to import standalone.
- **Uniform error shape:** control/read/energy tools now wear `@backend_errors` like the rest
  of the surface, so a `DeviceUnreachable` always surfaces as `{"error": …}`, never a raw
  exception.
- **Unused `discovery.subnets` config option removed** (documented but never implemented;
  old configs carrying the key still load). mDNS browses the local subnet; off-subnet devices
  are addressed by their configured `ip`.
- **Dropped unused `aioshelly` dependency** (raw HTTP per ADR-006 — it was never imported);
  installs no longer pull its BLE chain. Added the Python 3.13 classifier.
- **MCP handshake advertises our version, not the framework's.** `FastMCP` was instantiated
  without `version=`, so `serverInfo.version` reported the bundled FastMCP version (e.g. `2.14.7`)
  instead of `shelly-mcp`'s own `0.1.0`. Now passes `version=__version__`; covered by a regression
  test. Caught by a clean-room install + over-the-wire `initialize` smoke test.

### Notes
- **Clean-install verified (2026-06-09):** built wheel installed into a fresh venv (deps resolve
  from `pyproject` alone), the `shelly-mcp` console script serves a real MCP `initialize` +
  `tools/list` (47 tools) over stdio, and a tool call with **no config** returns a clean, actionable
  error (no traceback) instead of crashing.
- **Live-verified (2026-06-09) on real hardware:** cloud path against all 4 devices, and
  the **local** path end-to-end — Gen2 `POST /rpc` (Plus Plug S, Plus RGBW PM, Plus 1PM
  Mini) and Gen1 REST (`SHPLG-S`) — once the fleet was flattened onto one subnet. Closes
  the ADR-006 local-socket caveat. Still to re-confirm: the Gen1 local Wmin energy path
  against the Shelly app.
- 243 unit + contract tests; `ruff` + `mypy --strict` clean.
