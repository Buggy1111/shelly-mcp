# Shelly MCP Server — Build Plan & Roadmap

> The implementation sequence to take this from empty repo to a published v1.0 on the marketplaces. Each milestone has a **Definition of Done (DoD)** — don't move on until it's green. Discipline mirrors `anonymize-mcp` (272 tests shipped).

## Pre-flight (start of first coding session)

1. **Enable WSL mirrored networking** (see `04-CONFIG-AND-DEPLOY.md §3`) — write `C:\Users\micha\.wslconfig`, `wsl --shutdown` from Windows, reopen. Verify: `ping 192.168.0.101` and `curl http://192.168.0.101/shelly` succeed from WSL. *Without this only the Cloud backend is testable.*
2. **Scaffold:** `uv init`, `pyproject.toml` (entry point `shelly-mcp`), pin `fastmcp`, `aioshelly`, `zeroconf`, `pydantic`, `pyyaml`, `aiohttp`. Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`.
3. Drop in `LICENSE` (see §License), `README.md` skeleton, `.gitignore`, GitHub repo `Buggy1111/shelly-mcp` (private until v1.0 polish, like silikon-manager).

## Milestones

> **Progress (2026-06-09):** **M0–M5 + scenes + v1.1 automation complete; local path live-verified on real hardware; pushed to a private repo.** 47 tools + 2 resources + 3 prompts, 205 tests, ruff + `mypy --strict` clean, ~3.4K LOC.
> - **M0** ✅ scaffold + `CloudBackend` (live-verified, 4 real devices).
> - **M1** ✅ `Normalizer` (transport-aware energy, ADR-005), `DeviceRegistry` (local-first), `methods.py` (classification + Gen1 REST map), read tools incl. `shelly_discover`/`get_config`/`list_methods`.
> - **M2** ✅ control tools (switch/light/cover), generic `rpc`/`rpc_write` (confirm + data-loss gates), `audit.py`, **local backends** `Gen2RpcBackend` (raw `/rpc` + Digest) / `Gen1RestBackend` (raw REST + Basic) per **ADR-006** (raw HTTP, not aioshelly WS/CoAP), mDNS discovery.
> - **M3** ✅ `shelly_energy_live` + best-effort `shelly_energy_history`.
> - **M4** ✅ `shelly_schedule_*` + `shelly_system_*` (destructive-gated).
> - **M5** ✅ resources/prompts, README tool surface, CHANGELOG, `server.json`/`glama.json`, security audit (no secret leaks).
> - **Scenes** ✅ `shelly_scene_*` (5 tools) — server-side named scenes, ADR-007 / `06-SCENES.md`.
> - **v1.1 automation** ✅ (brought forward) `shelly_kvs_*` (4), `shelly_webhook_*` (4), `shelly_script_*` (8, chunked `PutCode` + reassembled `GetCode`), `shelly_virtual_*` (3) — deletes confirm-gated, arbitrary-code paths (`put_code`/`eval`) confirm-gated (ASI05). Live KVS round-trip + confirm gate verified on real Gen2 HW.
> - **Local live-verification** ✅ **(2026-06-09)** — done **without** WSL mirrored networking by flattening the LAN onto one subnet (`192.168.0.x`); WSL reaches it through the Windows host. **Gen2** verified on real hardware (`POST /rpc`: Plus Plug S + Plus RGBW PM + Plus 1PM Mini) and **Gen1** verified (`SHPLG-S` over REST) — closes the only ADR-006 caveat. Cloud path also live-verified. *Still to re-confirm: the Gen1 local Wmin energy path against the Shelly app.*

### M0 — Foundation (the `ShellyClient` core)
- `backends/base.py`: `Backend` Protocol, `Capabilities`, exception hierarchy (`UnsupportedOnGeneration`, `UnsupportedOnCloud`, `AuthRequired`, `DeviceUnreachable`).
- `Gen2RpcBackend` + `Gen1RestBackend` via aioshelly; `CloudBackend` (reuse logic from the existing `~/.hermes/shelly/shelly.py`).
- `auth.py`, `config.py` (0600 enforce), `client.py` probe+branch (`GET /shelly`), `DeviceRegistry`.
- **DoD:** from a script, list + identify + read raw status of all 4 real devices (Gen1 `mycka` + Gen2 trio) over **local**; Cloud backend reads the same via `auth_key`. Per-device 6-channel semaphore in place.

### M1 — Normalization + read tools
- `normalize.py`: canonical Pydantic models + `Normalizer` (Gen1 `relays/meters/tmp` ↔ Gen2 `switch:0`). `None`≠0.
- `methods.py`: canonical method registry + Gen1 REST mapping + READ/WRITE/DESTRUCTIVE classification.
- Tools: `shelly_discover`, `shelly_list_devices`, `shelly_get_info`, `shelly_get_status`, `shelly_get_config`, `shelly_list_components`, `shelly_list_methods`, `shelly_rpc` (read-guarded).
- **DoD:** `shelly_get_status` returns identical canonical shape for Gen1 and Gen2; contract tests pass on recorded real fixtures; auto-onboarding (probe→GetComponents→capabilities) works for an unconfigured device.

### M2 — Control (typed, gated)
- `shelly_switch_set/toggle`, `shelly_light_set` (RGBW/CCT/white normalized), `shelly_cover_move`.
- Server-side `confirm` gate + `audit.py` (append-only JSONL, secrets redacted).
- `shelly_rpc_write` (gated generic escape hatch).
- **DoD:** toggle `televize`, set `led` to warm-white 40 %, all mutations audit-logged; `rpc_write` refuses without `confirm`; destructive double-gate verified.

### M3 — Energy
- `shelly_energy_live` (per-switch + EM/EM1; `None` on Gen1 for V/A), `shelly_energy_history` (per-switch `aenergy.by_minute`; Pro 3EM `EMData`/CSV; Gen1 `meters[].total` / `em_data.csv`). Optional SQLite cache for history.
- **DoD:** answer "how much did `mycka` use today/total?" accurately across Gen1 and Gen2.

### M4 — Schedules + system
- `shelly_schedule_{list,create,update,delete}` (6-field cron validate, ≤20 guard, validate calls against registry); `shelly_system_{reboot,update,set_auth}` (all D+confirm).
- **DoD:** create + list + delete a schedule on a real device; system tools gated and audited.

### M5 — Polish, test, publish v1.0
- Eval suite (§Eval), full unit+contract coverage, `ruff`+`mypy` clean.
- `README.md` (marketplace face), `glama.json`, `server.json` (`io.github.buggy1111/shelly-mcp`), CHANGELOG.
- `code-audit` + `owasp-security` on the diff; confirm no secrets, pinned deps.
- PyPI trusted-publish → MCP Registry → verify PulseMCP pickup → Glama → awesome-mcp PR → mcp.so.
- **DoD:** `uvx shelly-mcp` works from a clean machine; listed on Registry + Glama (target quality A).

### Post-v1.0
- v1.1: Webhook / Script / KVS / Virtual + push (Outbound WS event bus).
- v1.2: BLU / BTHome / Matter / Zigbee.
- **Apify cloud-mode Actor** (thin CloudBackend wrapper, Python FastMCP template, PPE billing) — secondary listing.

## License

**Recommendation: MIT** (or Apache-2.0 if patent grant matters). Rationale: this is community infrastructure meant for **maximum adoption** across the Shelly ecosystem — a permissive license removes all friction for users, integrators, and marketplace listing. This differs deliberately from `anonymize-mcp` (which was non-commercial because of the ÚFAL endorsement constraint); here there's no such constraint. **→ one open decision for Michal: MIT vs Apache-2.0.**

## Trademark / naming

"Shelly" is a trademark of **Allterco Robotics**. The project must state clearly in README + PyPI + listings: *"Unofficial community project. Not affiliated with, endorsed by, or sponsored by Allterco Robotics / Shelly."* Package name `shelly-mcp` (descriptive use, free on PyPI). Avoid any logo/branding that implies official status.

## Eval suite (mcp-builder Phase 4 — 10 read-only questions)

Realistic, verifiable, stable questions an LLM should answer via the tools (answers from the real test-bed where applicable):

1. Which of my devices are Gen1 vs Gen2? → mycka=Gen1, rest=Gen2.
2. What is the total lifetime energy (kWh) reported by `mycka`? → ~549 kWh.
3. Is the TV (`televize`) currently drawing power, and how much? → standby ~0.6 W.
4. Which device runs on DC voltage and what is it? → `led`, ~24 V.
5. How many devices are on the 192.168.1.x subnet? → 3.
6. Which devices have a firmware update available, and which channel? → led(beta 2.0.0), mycka(beta rc).
7. What components does `led` expose? → rgbw:0 + 4 inputs (via list_components).
8. Which device reports the highest silicon temperature right now? → (live).
9. Does `mycka` report voltage/current? → No (Gen1 limitation).
10. What is the current RGB colour set on `led`? → [255,23,47] @ brightness 10.

Format: XML `<evaluation><qa_pair>…` per mcp-builder. Run via the eval scripts.

## CI/CD

GitHub Actions: on PR → ruff + mypy + pytest (unit; contract uses recorded fixtures, no live device needed in CI). On tag → build + PyPI trusted publish (OIDC, no token). Mirrors anonymize-mcp's CI discipline.

## README plan (the marketplace face — drives adoption + Glama score)

Must contain: one-line value prop · install (`uvx shelly-mcp`) · quick config example · tool list with one-line each · **"what data leaves your machine" (none beyond your devices/cloud)** · local-vs-cloud capability table · supported devices (Gen1–Gen4 + BLU) · the trademark disclaimer · link to docs.
