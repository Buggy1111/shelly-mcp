# Shelly MCP Server — Project Log

> A plain, honest record of **what was built, where it lives, and how it came together** —
> so future-me (and anyone reading) can see the shape of the work at a glance, not reconstruct
> it from 28 commit messages.

## 1. What this is (one paragraph)

An **MCP server for the entire Shelly smart-home ecosystem** — read, control, and automate
Shelly devices of every generation (Gen1 → Gen4 + BLU) from any MCP client (Claude, Cursor,
Hermes…). **Local-first** (full device API over the LAN, no rate limit), with **Shelly Cloud as
a degraded fallback** for off-LAN access. It solves a real gap: the only existing Shelly MCP
servers are cloud-only and minimal (5–10 tools, no automation); this one unifies Gen1 + Gen2+
behind one tool surface, covers energy + automation + named scenes, and a generic RPC engine that
reaches **every** component — including hardware released after the server was written.

## 2. Status snapshot (2026-06-09)

| | |
|---|---|
| **Tools** | 47 (read · control · energy · schedule · system · scenes · automation · generic engine) |
| **Resources / prompts** | 2 resources + 3 prompts |
| **Code** | ~3.3K LOC (`src/`) + ~2.3K LOC tests |
| **Tests** | 243 unit + contract, all green |
| **Quality gates** | `ruff` clean · `mypy --strict` clean · CI on Python 3.11 / 3.12 / 3.13 |
| **Live-verified** | Gen2 `/rpc` + Gen1 REST on real hardware, Cloud path, Hermes/Izy integration |
| **Security** | Independent audit — confirm-gates / secrets / injection / validation / supply-chain all PASS |
| **Distribution** | Pushed to **private** GitHub; public PyPI + registries pending (launch decision) |

## 3. The repo / git

- **Remote:** `github.com/Buggy1111/shelly-mcp` (**private** for now), default branch `main`.
- **Released under:** MIT (community infra, max adoption).
- **Commit style:** conventional prefixes — `feat:` / `fix:` / `docs:` / `refactor:` / `harden:`.
  Each commit is one coherent, green step (tests pass at every commit).
- **Branch model:** trunk-based on `main`; risky/autonomous work happened on short `auto/*`
  branches and was fast-forwarded into `main` once green.
- **CI:** `.github/workflows/ci.yml` runs ruff + mypy + pytest on a 3.11/3.12/3.13 matrix;
  `release.yml` builds and publishes to PyPI on a `v*` tag via trusted publishing (no token).

## 4. How it's built (architecture in five lines)

1. **Two volatile boundaries get hard interfaces**, everything else is direct readable code:
   (a) transport/generation — `Gen2RpcBackend` / `Gen1RestBackend` / `CloudBackend` behind one
   `Backend` protocol; (b) the device API surface — a generic `rpc` engine + a `Normalizer`.
2. **Generic engine + typed polish (ADR-002):** a generic `shelly_rpc`/`shelly_rpc_write`
   guarantees total coverage; typed tools (switch/light/cover/energy/…) add ergonomics.
3. **Normalize at the edge (ADR-003):** Gen1 (`relays[]`/`meters[]`) and Gen2 (`switch:0`) fold
   into one canonical model; `None` ≠ fake-zero; `raw` always attached.
4. **Fail-closed, least-privilege:** reads are safe; mutations audited; destructive + arbitrary-code
   paths gated behind `confirm:true`; method classification is fail-safe (unknown → WRITE).
5. **Organised as vertical slices** (`tools/read.py`, `control.py`, … one module per group), not
   deep layers — the right call for a solo-maintained project. Full detail in `01-ARCHITECTURE.md`.

Stack: Python 3.11+, **FastMCP**, `aioshelly` (pinned), `pydantic`, `aiohttp`, stdio transport,
packaged with `uv`/`hatchling`, `uvx shelly-mcp` to run.

## 5. Build timeline (by day)

### 2026-06-08 — Design, then M0–M5 code-complete in one evening
- **Design first, no code** (Michal's rule: build only once the shape is certain). Wrote the full
  doc set: overview, architecture + ADR-001…006, tool surface, security threat model,
  config/deploy, build plan, and the authoritative Shelly API catalog.
- **M0–M5 then landed in ~80 minutes of commits** (`f7ee9be` … `8fb3fd6`):
  - **M0** scaffold + `CloudBackend`.
  - **M1** `Normalizer` (+ ADR-005: Gen1 energy unit is transport-dependent), `DeviceRegistry`
    (local-first routing), `methods.py` (READ/WRITE/DESTRUCTIVE classification + Gen1 REST map),
    read tools.
  - **M2** control tools, generic `rpc`/`rpc_write` engine (confirm + data-loss gates), audit log,
    **local HTTP backends** (ADR-006: raw `/rpc` + REST, not aioshelly WS/CoAP), mDNS discovery.
  - **M3** energy live + history. **M4** schedules + system tools (destructive-gated).
  - **M5** MCP resources + prompts, distribution manifests (`server.json`, `glama.json`),
    CHANGELOG, README.
- **End of day:** M0–M5 code-complete, ~142 tests, cloud path live-verified against 4 real
  devices; the local socket round-trip still unverified (no LAN access yet).

### 2026-06-09 — Hardening, scenes, automation, security, ship-prep
- **Early morning** (`4e5ee20` … `9523f61`): CI/CD workflows, file-name alignment with the
  architecture doc + centralised `auth.py`, **contract tests** (replay recorded real-device
  fixtures — locks normalization), the 10-question eval suite, and a fix to resolve friendly
  device names to cloud ids (`DeviceConfig.id`) so Hermes/Izy could address cloud-only devices.
- **Afternoon** (`2150a93` … `968eae8`): device **locations + aliases** (room-level control) and
  the **first live verification of the local Gen2 backend against real hardware**. Then the
  headline feature: **server-side named scenes** — design (ADR-007 / `06-SCENES.md`) followed by
  implementation (`shelly_scene_{list,get,run,create,delete}`). A scene is a saved, named batch of
  `{device, method, params}` reusing `execute_and_audit` — deterministic, schedulable, the one
  thing no competing Shelly MCP has.
  - *(Operational milestone, off-repo: the device fleet was flattened onto a single subnet and the
    local Gen1 + Gen2 paths were both confirmed end-to-end on real hardware — closing the last
    ADR-006 caveat.)*
- **Evening** (`3dcbee7` … `c878f7f`):
  - **Docs synced** to shipped reality (scenes in the tool surface, live-verified status).
  - **v1.1 automation tools** brought forward: `kvs_*`, `webhook_*`, `script_*` (chunked `PutCode`,
    reassembled `GetCode`), `virtual_*` — 19 tools, deletes + arbitrary-code paths confirm-gated.
    KVS round-trip + confirm gate live-verified on real Gen2 hardware.
  - **Pre-release review** (independent code review): fixed a scene-delete preview mislabel, an
    over-broad audit redaction that masked KVS key names, and a byte-offset bug in `GetCode`.
  - **Security hardening** (independent audit): audit redaction now recurses lists and strips URL
    credentials; `*.DeleteAll` is double-gated. All five audit dimensions PASS.
  - **DRY refactor:** a single `@backend_errors` decorator replaced ~31 repeated
    `try/except BackendError` blocks with a uniform `{"error": …}` contract (−30 net LOC), verified
    not to disturb the FastMCP tool schemas.
- **End of day:** 47 tools, 205 tests, security-audited, **pushed to a private GitHub repo.**

## 6. Where it stands

- **As an engineering artifact:** production-grade and release-ready — tested, typed, security-
  audited, documented with ADRs, live-verified on real hardware across both device generations.
- **As a product:** pre-launch — private repo, not yet on PyPI/registries, zero external users. The
  next step is purely distribution, not more code.

### 2026-06-10 — pre-launch audit & fixes (Fable 5)

An independent three-track audit (security / code quality / docs accuracy) ran against the
launch-ready tree and found two real gate bypasses plus a stack of housekeeping. All fixed
the same day on `auto/audit-fixes`:

- **Security:** scenes + schedules now accept only the control-method allowlist
  (`Switch/Light/RGB/RGBW/CCT/Cover`) — previously `Schedule.Create` accepted
  `Shelly.FactoryReset` (a deferred reset past both confirm gates) and a scene accepted
  `Script.Eval`/`Shelly.SetAuth`. Also: `get_config` credential redaction (Gen1 `/settings`
  leaks Wi-Fi PSK), webhook URLs restricted to absolute http(s).
- **Code:** latent circular import broken (backends package re-exports), `@backend_errors`
  on the whole tool surface (uniform `{"error": …}`), unused `aioshelly` dep and
  `discovery.subnets` option removed.
- **Docs:** stale aioshelly/WSL/license/namespace claims reconciled; tool table corrected
  (47 tools incl. `shelly_version`; real parameter lists); LLM preamble removed from
  `API-CATALOG.md`. Tests 205 → **243** (gate-bypass regressions, redaction, URL
  validation, standalone-import tests).

### Pending before public launch (decisions, not defects)
1. ~~Verify the MCP Registry namespace casing in `server.json`~~ ✅ done 2026-06-09 (`io.github.Buggy1111`, case-sensitive — see `08-LAUNCH-CHECKLIST.md §6`).
2. ~~Refresh the competitive section of `00-OVERVIEW.md`~~ ✅ done 2026-06-09.
3. Decide version + maturity wording (`0.1.0` / Alpha vs `1.0.0` / Beta) and confident README.
4. Publish: PyPI → MCP Registry → Glama → awesome-mcp.

### Possible future (only if a real need appears)
v1.1 push event bus (Outbound WebSocket / MQTT) · `scene_to_schedule` bridge · v1.2 BLU / Matter /
Zigbee · a small `@backend_errors`-style sweep is already done, so the codebase is clean to extend.
