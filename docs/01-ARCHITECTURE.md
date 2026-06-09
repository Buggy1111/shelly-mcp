# Shelly MCP Server — Architecture

> Design phase. Authored with senior-architect + mcp-builder guidance. Mantra: *build the smallest thing that really lasts, isolate what will change, write it so it can be deleted without fear.*

## 1. Design principles (what governs every decision)

1. **Local-first.** The local device API is the source of truth and full capability. Cloud is a degraded fallback. The abstraction must never assume cloud.
2. **Isolate what changes.** Two volatile boundaries get hard interfaces: (a) **transport/generation** (Gen1 REST vs Gen2 RPC vs Cloud) and (b) **the device API surface** (Shelly adds components yearly). Everything else is direct, readable code — no speculative layering.
3. **Generic engine + typed polish.** Don't hand-code 45 components. A generic component layer guarantees total coverage; typed tools add ergonomics where it pays.
4. **Fail-closed, least-privilege.** Read tools are read-only. Mutating tools are explicit. Destructive tools require human confirmation. Errors deny, never silently allow.
5. **Normalize at the edge, not the core.** Convert Gen1/Gen2 shapes into one canonical model in the backend layer, so tools and the LLM see one consistent world.

## 2. Layered architecture

```
┌─────────────────────────────────────────────────────────────┐
│  MCP CLIENT (Claude Desktop / Code / Cursor …) via stdio     │
└───────────────────────────────┬─────────────────────────────┘
                                 │  MCP protocol (stdio, JSON-RPC)
┌───────────────────────────────▼─────────────────────────────┐
│  TOOL LAYER  (FastMCP @mcp.tool)                             │
│  ── Tier 2: typed tools (switch/light/cover/energy/schedule) │
│  ── Tier 1: generic engine (rpc_call, list_components,       │
│             get_status, discover)                            │
│  Pydantic input/output schemas · annotations · confirm gates │
└───────────────────────────────┬─────────────────────────────┘
                                 │  canonical calls
┌───────────────────────────────▼─────────────────────────────┐
│  DEVICE LAYER  (ShellyClient — the core abstraction)         │
│  ── DeviceRegistry  (discovery + config + identity cache)    │
│  ── ShellyDevice    (resolves to one backend per device)     │
│       ├── Gen2RpcBackend   (aioshelly RpcDevice / WS+HTTP)   │
│       ├── Gen1RestBackend  (aioshelly BlockDevice / REST)    │
│       └── CloudBackend     (auth_key, v1/v2 endpoints)       │
│  ── Normalizer      (Gen1/Gen2/Cloud → canonical model)      │
│  ── AuthManager     (digest SHA-256 / basic / cloud key)     │
└───────────────────────────────┬─────────────────────────────┘
                                 │
┌───────────────────────────────▼─────────────────────────────┐
│  SHELLY DEVICES (LAN)        │  SHELLY CLOUD (fallback)       │
│  Gen2+ RPC /rpc · Gen1 REST  │  shelly-NN-eu.shelly.cloud     │
└──────────────────────────────┴────────────────────────────────┘
```

## 3. The core abstraction: `ShellyClient`

One probe, one branch. On first contact with a device IP, call `GET /shelly` (unauthenticated, works on every generation):

- Gen1 → `{type, mac, auth, fw, num_outputs}` → `Gen1RestBackend`
- Gen2+ → `{id, mac, model, gen, fw_id, app, auth_en}` → `Gen2RpcBackend`
- Unreachable on LAN but configured for cloud → `CloudBackend`

The `gen` integer / `model` SKU is authoritative and cached in the `DeviceRegistry`.

### Backend interface (the volatile boundary #1)

```python
class Backend(Protocol):
    async def probe(self) -> DeviceIdentity: ...
    async def get_status(self) -> dict: ...          # raw, per-generation
    async def get_config(self) -> dict: ...
    async def list_components(self) -> list[str]: ...
    async def call(self, method: str, params: dict) -> dict: ...  # generic RPC / mapped REST
    @property
    def capabilities(self) -> Capabilities: ...      # what this device/backend can do
```

- **Gen2RpcBackend** wraps `aioshelly.rpc_device.RpcDevice`. Generic `call()` maps straight to JSON-RPC `method`/`params`. Uses the shared `WsServer` so many devices share one inbound socket; respects the **6-channel concurrency limit** per device via a per-device semaphore.
- **Gen1RestBackend** wraps `aioshelly.block_device.BlockDevice`. Generic `call()` translates a *canonical* method name to the Gen1 REST endpoint (e.g. `Switch.Set{id:0,on:true}` → `GET /relay/0?turn=on`). Methods with no Gen1 equivalent raise `UnsupportedOnGeneration`.
- **CloudBackend** posts to the per-account host with `auth_key`. Only `Switch/Light/Cover` control + live status are mapped; everything else raises `UnsupportedOnCloud` (the cloud API genuinely cannot do scripts/schedules/webhooks/KVS/EMData).

### Capabilities — honest about limits

Each backend exposes a `Capabilities` object so the tool layer (and the LLM) never attempt the impossible. `CloudBackend.capabilities.can_automate == False`. A Gen1 device reports `has_voltage_current == False`. This is how we avoid lying to the user (per `[[feedback_thorough_verify]]`).

## 4. Normalization (the volatile boundary #2)

The `Normalizer` turns raw per-generation status into a canonical model. Example for a relay/plug:

```
Gen2  switch:0.{output, apower, voltage, current, aenergy.total, temperature.tC}
Gen1  relays[0].ison + meters[0].{power, total} + tmp.tC
        ▼  both normalize to:
ChannelState(output: bool, power_w: float|None, energy_total_wh: float|None,
             temperature_c: float|None, voltage: float|None, current: float|None,
             source: str, raw: dict)   # raw kept for power users / debugging
```

Canonical models (Pydantic): `DeviceIdentity`, `ChannelState`, `LightState` (rgb/white/brightness/temp), `CoverState` (pos/state), `EnergyReading`, `EnergyHistory`, `ComponentInfo`. `None` means "this generation/device doesn't report it" — never a fake zero.

> **Rule:** the canonical model is a **one-way door** (it's the public contract the LLM and any downstream see). Design it carefully; keep `raw` attached so we never block a power user who needs an un-normalized field.

## 5. Two-tier tool design

**Tier 1 — generic engine (total coverage, ships v1.0):**
- `shelly_discover`, `shelly_list_devices`, `shelly_get_info`, `shelly_get_status`, `shelly_get_config`, `shelly_list_components`, `shelly_list_methods`
- `shelly_rpc` — call any **read** method (`*.GetStatus/GetConfig/List*`) on Gen2+; safe, `readOnlyHint`.
- `shelly_rpc_write` — call any **mutating** method; `destructiveHint`, **requires `confirm: true`**, audit-logged. This is the escape hatch that makes the server cover 100 % of the API without 150 hand-written tools.

**Tier 2 — typed tools (ergonomics + Glama score):** `shelly_switch_set`, `shelly_light_set`, `shelly_cover_move`, `shelly_energy_live`, `shelly_energy_history`, `shelly_schedule_*`, `shelly_system_*`. Each normalizes Gen1↔Gen2, validates input, returns structured output.

> **Trade-off:** Tier 1's `rpc_write` is powerful and therefore risky (it can reach `FactoryReset`). Mitigation is in §security: method classification + confirm gate + audit. We accept the power because the alternative (no generic tool) means the server silently *can't* do most of what Shelly offers — a worse failure for a "covers everything" product.

## 6. Discovery

Three sources, merged into `DeviceRegistry`:
1. **mDNS** (`_shelly._tcp.local.`, `_http._tcp.local.`) — zero-config on a single subnet. ⚠️ Does **not** cross subnets (Michal's fleet spans 192.168.0.x + 192.168.1.x) → also support:
2. **Manual config** — explicit IP list + per-device auth in the config file (see `04-CONFIG-AND-DEPLOY.md`). Always authoritative.
3. **Cloud list** — `/device/all_status` returns the whole account in one call (off-LAN discovery).

Registry caches identity (`gen`, `model`, `mac`, auth-needed) with a persistent fallback list, because some firmwares (Pro 3EM) respond poorly to active mDNS. Discovery is **passive + cached**, never a blocking dependency for a known device.

### New-device auto-onboarding (zero-code)

When a device the registry hasn't seen appears (fresh mDNS hit, a new IP added to config, or a new entry in the cloud list), the registry onboards it automatically without any code change:

1. `GET /shelly` → detect generation + `model` SKU → pick backend.
2. `Shelly.GetComponents` + `Shelly.ListMethods` (Gen2+) / `/shelly` capability fields (Gen1) → enumerate what *this specific unit* exposes.
3. Compute its `Capabilities` and cache the identity.

The result: the typed tools light up only for components the device actually has, and the generic `rpc`/`rpc_write` engine can already reach **everything** the device reports — including an SKU released after this server was written. The LLM can ask "what can this new device do?" (`shelly_list_components`) and get a live, accurate answer. Onboarding is also triggerable on demand via `shelly_discover` (rescan), so a user who just plugged in a device doesn't restart anything.

## 7. Connection & concurrency

- Per-device **semaphore = 6** (hard Gen2 limit on simultaneous RPC channels). The MCP server is the single polling authority; we never starve the device.
- Shared `aioshelly.WsServer` for inbound notifications (v1.1 push).
- Retries with backoff on retryable errors (`-104` deadline, `-108` resource-exhausted, `503` battery-sleep). No retry on `-103`/`-105` (caller error).
- Hard per-call timeout (default 10 s) — fail-closed on hang.

## 8. Transport & runtime

- **stdio** transport (mcp-builder guidance for local servers). The server runs on the user's machine, on their LAN, with their credentials. No network listener, no hosting, no inbound attack surface.
- **async throughout** (`anyio`/`asyncio`) — aioshelly is async; device I/O must never block the event loop.
- Python **3.11+**, packaged with **uv**, entry point `shelly-mcp` (runnable via `uvx shelly-mcp`).

## 9. Project structure (planned)

```
shelly-mcp/
├── pyproject.toml            # uv, deps pinned, entry point, MCP Registry server.json next to it
├── README.md
├── glama.json
├── server.json               # MCP Registry manifest (io.github.buggy1111/shelly-mcp)
├── src/shelly_mcp/
│   ├── __init__.py
│   ├── server.py             # FastMCP app, tool registration
│   ├── client.py             # ShellyClient, DeviceRegistry
│   ├── backends/
│   │   ├── base.py           # Backend Protocol, Capabilities, exceptions
│   │   ├── gen2_rpc.py
│   │   ├── gen1_rest.py
│   │   └── cloud.py
│   ├── normalize.py          # Normalizer + canonical Pydantic models
│   ├── discovery.py          # mDNS + cloud list + registry
│   ├── auth.py               # digest/basic/cloud credential handling
│   ├── config.py             # config file + env loading (0600 enforced)
│   ├── audit.py              # structured audit log for mutations
│   ├── tools/                # one module per tool group (vertical slices)
│   │   ├── read.py  control.py  energy.py  schedule.py  system.py  generic.py
│   └── methods.py            # canonical method registry + Gen1 REST mapping + classification
├── tests/
│   ├── unit/                 # normalizer, mapping, classification
│   ├── contract/             # recorded real-device fixtures (Michal's 4 kits) — Gen1+Gen2
│   └── eval/                 # 10 MCP eval questions (mcp-builder Phase 4)
└── docs/                     # this folder
```

Organized as **vertical slices** (a tool group keeps its logic together), not deep horizontal layers — right call for a solo-maintained project.

## 10. Testing strategy

- **Unit:** normalizer (Gen1↔Gen2 fixtures from real dumps), Gen1 REST mapping, method classification (read vs write vs destructive).
- **Contract:** recorded JSON fixtures from Michal's real devices (already captured — see `[[shelly-devices]]`) replayed against backends. Locks the normalization contract so a refactor can't silently break Gen1.
- **Eval:** 10 realistic LLM questions per mcp-builder Phase 4 ("how much did the dishwasher use today?", "turn the LED warm-white at 40 %", "schedule the TV off at 23:00").
- Mirrors `anonymize-mcp` discipline (272 tests shipped).

---

## ADRs (Architecture Decision Records)

### ADR-001 — Language: Python + FastMCP (not TypeScript)
**Context:** mcp-builder recommends TypeScript by default (SDK maturity, MCPB packaging, model code-gen quality).
**Options:** (a) TypeScript + `@taulfsime/shelly-rpc-ts`; (b) Python + `aioshelly`.
**Decision:** **Python + FastMCP + aioshelly.**
**Why:** `aioshelly` is the canonical, battle-tested Shelly client (powers Home Assistant) — it already solves Gen1 `BlockDevice`, Gen2 `RpcDevice`, digest auth, the shared WS pool, and mDNS discovery. The TS options are thin type-defs or framework-coupled; we'd reimplement years of edge-case handling. Michal ships Python (anonymize-mcp, 272 tests). PyPI/uvx distribution works on every target marketplace.
**Consequences:** We forgo Smithery's MCPB packaging — acceptable, we're skipping Smithery anyway (it killed stdio Sept 2025). Pin `aioshelly` (supply chain, A03). If aioshelly ever stalls, the Backend Protocol isolates us — we can swap implementations behind it.

### ADR-002 — Generic `rpc` engine as a first-class tool
**Context:** Shelly has ~45 components and grows yearly; hand-coding all is brittle and incomplete.
**Decision:** Ship a generic `shelly_rpc` (read) + `shelly_rpc_write` (gated) from v1.0, alongside self-discovery (`GetComponents`/`ListMethods`).
**Why:** Guarantees total coverage structurally (including future devices) without 150 tools. Typed tools become *optional polish*, not the only path to a capability.
**Consequences:** The write variant is a sharp tool → must be gated (confirm + audit + method classification, see security). Worth it.

### ADR-003 — Normalize Gen1↔Gen2 in the backend, expose canonical models
**Context:** Gen1 (`relays[]`/`meters[]`) and Gen2 (`switch:0`) shapes differ fundamentally.
**Decision:** A `Normalizer` produces canonical Pydantic models with `None` for unsupported fields and a `raw` passthrough.
**Why:** The LLM sees one world; tools stay generation-agnostic. `None`-not-zero keeps us honest about what Gen1 can't measure.
**Consequences:** Canonical model is a one-way door (public contract) — design carefully, version if it must change.

### ADR-004 — stdio transport, bring-your-own-credentials, no hosting
**Context:** The server talks to the user's *local* devices and/or their *own* cloud key.
**Decision:** stdio local server; credentials supplied by the user via config/env; no hosted endpoint.
**Why:** Right security posture (no inbound surface), right distribution fit (Registry/Glama/PulseMCP all support stdio), matches the data-locality reality. Also why Smithery is a poor fit.
**Consequences:** Each user runs it locally near their LAN. For Michal's WSL test-bed, local access needs WSL mirrored networking (see deploy doc).

### ADR-005 — Gen1 energy unit is transport-dependent (Watt-minutes local, Wh cloud)
**Context:** A Gen1 `meters[].total` does **not** carry the same unit on both transports. The official Gen1 API documents the device-native `/status` `meters[].total` as **Watt-minutes**. But Shelly Cloud pre-divides that counter and returns **Wh** in `device/status`. Captured real data confirms it: `mycka` (a SHPLG-S on the dishwasher) returns `total: 548723` over cloud, which is ~549 kWh as **Wh** — physically right for a dishwasher; as Watt-minutes it would be an implausible 9 kWh.
**Decision:** `Normalizer.normalize_status(..., backend=...)` converts ÷60 only for `local_rest`; cloud data passes through as Wh. Canonical `energy_total_wh` is always Wh regardless of transport.
**Why:** Normalization correctness can't depend on generation alone — the transport changes the unit. A naive always-÷60 would under-report cloud energy by 60×.
**Consequences:** The Gen1 normalizer takes a `meter_total_is_wh` flag threaded from the backend kind. `emeters[]` (Gen1 EM/3EM) and Gen2 `aenergy.total` are Wh on both transports. To be re-verified live against the Shelly app once local backends land (M2) so the local Wmin path is confirmed end-to-end.

### ADR-006 — Local backends use raw HTTP for v1.0 (not aioshelly's WS/CoAP)
**Context:** ADR-001 picked aioshelly. In practice its `RpcDevice` drives Gen2 over a WebSocket (`WsRPC` + a `WsServer` context) and its `BlockDevice` drives Gen1 with a CoAP context. Both exist mainly to deliver **push events** — a v1.1 concern (the roadmap lists the Outbound WS event bus under v1.1). For a request/response MCP, that machinery is overhead that also can't be exercised without live hardware on the LAN.
**Decision:** v1.0 local backends talk raw HTTP. **Gen1** = `GET /status|/settings|/relay/0?...` with optional HTTP Basic auth (aiohttp native). **Gen2+** = `POST /rpc` with `{id,method,params}` and a small RFC 7616 SHA-256 **Digest** helper for auth. No WebSocket, no CoAP.
**Why:** Simpler, fewer moving parts, and **fully unit-testable offline** (fake aiohttp session). The `/rpc` and Gen1 REST endpoints are stable documented APIs.
**Consequences:** No push/subscribe in v1.0 (we poll on demand — fine for an MCP). aioshelly stays a pinned dep for a possible v1.1 event bus. **Live-verified 2026-06-09** on real hardware once the fleet was flattened onto one subnet (`192.168.0.x`, reachable from WSL through the Windows host — no WSL mirrored networking needed): Gen2 `POST /rpc` against a Plus Plug S, Plus RGBW PM and Plus 1PM Mini, and Gen1 REST against an `SHPLG-S`. Digest auth + request shaping were already unit-tested; the socket round-trip is now confirmed end-to-end.

### ADR-007 — Server-side named scenes (storage, model, execution, scheduling)
**Context:** The server has LLM-driven scenes (prompts like `shelly_evening_scene`) but no **deterministic, named, schedulable, cross-client** scenes — the #1 differentiator (no competing Shelly MCP has it). Full design in `docs/06-SCENES.md`.
**Decision:** A scene is a saved, named, ordered batch of `{device, method, params}` — the same shape `Schedule.Create`'s `calls` and `execute_and_audit` already use. (a) **Storage:** a dedicated `scenes.yaml` (default `~/.config/shelly-mcp/scenes.yaml`, env `SHELLY_MCP_SCENES`), atomic write, **not** in `config.yaml` (secret-bearing, 0600, hand-authored) and **not** in device KVS (per-device, cross-device coupling) and **not** Shelly Cloud (not local-first). (b) **Execution:** best-effort **sequential**, per-action result + overall `ok|partial|failed` status — **no transactions** (physical actions can't roll back). (c) **Security:** actions must classify WRITE and **not** DESTRUCTIVE (rejected at create) → `scene_run` needs no confirm gate. (d) **Scheduling:** lean on device-native `Schedule.Create` (single-device scenes) + client crons (Hermes/Claude Code) calling `scene_run`; **no server-side scheduler daemon** — the stdio server stays request/response (ADR-004/006).
**Why:** Reuses the entire existing execution path (Gen1↔Gen2 normalization, audit, classification, device resolution) for free — the feature is just storage + validation + an honest runner (~150–200 LOC). Best-effort + per-action reporting honours `[[feedback_thorough_verify]]`. Non-destructive-only keeps a schedulable, LLM-runnable scene from being a backdoor to `FactoryReset` (LLM06/ASI02).
**Consequences:** Scene model (`{device, method, params}`) is a public one-way-door contract — versioned if it must change. Scenes live in a file the user doesn't already know (mitigated: sibling of config, documented). Server-side scheduler deferred until a concrete need crons can't serve appears — and then as a separate process, not bolted into stdio.
