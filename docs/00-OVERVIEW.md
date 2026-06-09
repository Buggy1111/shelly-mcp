# Shelly MCP Server — Overview & Scope

> **Status:** **M0–M5 + scenes + v1.1 automation tools complete; local (Gen1+Gen2) & cloud paths live-verified on real hardware (2026-06-09).** 47 tools + 2 resources + 3 prompts, 205 tests, ruff + `mypy --strict` clean. Pushed to a **private** GitHub repo; public publishing still pending — see `05-BUILD-PLAN.md`.
> **Date:** 2026-06-09 (design started 2026-06-08)

## 1. What this is

A **production-grade, community MCP server for the entire Shelly smart-home ecosystem**, distributed publicly on MCP marketplaces (MCP Registry, Glama, awesome-mcp, mcp.so). It lets any LLM client (Claude Desktop, Claude Code, Cursor, …) **read, control, and automate** Shelly devices of every generation (Gen1 → Gen4 + BLU) over local network or Shelly Cloud.

This is **not** a personal tool for Michal's 4 devices — those are the real-world test-bed. The product targets the whole Shelly community.

## 2. Why build it (the real problem)

- **The space is near-empty (competitive audit, 2026-06-09).** Only two narrow MCPs exist: `mslavov/shelly-mcp` (TypeScript, cloud-only, ~5 control tools) and `game4automation/shelly` (Python, energy-focused, ~10 tools, listed on LobeHub). The **official** Shelly MCP is *docs-only* — it answers questions about Shelly, it can't touch a device. Even Shelly Cloud's own paid "AI" is just two notification features, not programmatic control. The Glama "Home Automation & IoT" category (31 servers) still has **zero** general-purpose Shelly coverage.
- **No one does it properly.** No existing MCP unifies Gen1+Gen2, exposes automation (scripts/schedules/webhooks/KVS), or covers energy monitoring with history.
- **Fits Michal's ethos** — real, hard problem; B2B/practitioner credibility piece, like `anonymize-mcp`.

## 3. What makes it stand out (differentiation)

1. **Local-first, cloud-fallback** — full power locally (zero rate-limit, ~10 ms, 100 % of API); cloud as off-LAN fallback.
2. **Gen1 ↔ Gen2+ normalization** — one unified tool surface across a decade of hardware. Nobody does this.
3. **Two-tier coverage** — a *generic component engine* that self-discovers and exposes **every** component (even future ones) + *typed convenience tools* for the common ones. "Covers everything" is structural, not hand-coded.
4. **Automation as first-class** — schedules, webhooks, scripts, KVS, virtual components. Zero competitors have this.
5. **Server-side named scenes** — deterministic, schedulable, cross-client multi-device routines run by name (ADR-007). No competing Shelly MCP has this.
6. **Energy monitoring** — live + historical (per-switch `aenergy`, EM/EMData, CSV bulk export).
7. **Standalone install** — `uvx shelly-mcp` / `pip install`, bring-your-own-credentials, runs locally. No hosting, no lock-in.

## 4. Scope phasing

The **generic `rpc_call` + component discovery** ships in v1.0, so the server can technically reach *any* method from day one. The typed tiers are added progressively for polish.

| Capability | v1.0 | v1.1 | v1.2 |
|---|:--:|:--:|:--:|
| Discovery (mDNS + manual config + cloud list) | ✅ | | |
| Generation auto-detect (`GET /shelly`) | ✅ | | |
| Normalized `get_status` / `get_info` / `list_components` (Gen1↔Gen2) | ✅ | | |
| **Generic `rpc_call` (read) + `rpc_call` (write, gated)** | ✅ | | |
| Switch control (set/toggle) | ✅ | | |
| Light / RGB / RGBW / CCT control | ✅ | | |
| Cover control (open/close/stop/pos) | ✅ | | |
| Energy: live + history + CSV export | ✅ | | |
| Schedule CRUD (time automation) | ✅ | | |
| System: reboot / update (confirm-gated) | ✅ | | |
| Webhook CRUD (event automation) | ✅ | | |
| Script lifecycle (create/put_code/start/stop/eval) | ✅ | | |
| KVS + Virtual components | ✅ | | |
| Push: Outbound WebSocket / MQTT event bus | | ✅ | |
| BLU / BTHome enrolment + BLU TRV | | | ✅ |
| Matter / Zigbee (Gen4) | | | ✅ |

## 5. Success criteria

- **v1.0 done =** on a real LAN with mixed Gen1+Gen2 devices: discover them, read normalized status & energy, toggle a relay, set RGBW colour, create a schedule, and call an arbitrary RPC — all via an LLM client, with a passing test suite (unit + contract) and Glama-grade tool descriptions.
- **Distribution done =** listed on MCP Registry → auto-picked by PulseMCP; Glama quality ≥ B; PR to awesome-mcp; mcp.so submission.

## 6. Test-bed (Michal's devices)

See `[[shelly-devices]]` memory. Mixed fleet validating both backends:

| Name | SKU | Gen | Surface |
|---|---|---|---|
| televize | SNPL-00112EU (Plus Plug S) | G2 | `switch:0` + energy |
| mycka | SHPLG-S (Plug S) | **G1** | `relays[]` + `meters[]` |
| svetla-kuchyn | SNSW-001P8EU (Plus 1) | G2 | `switch:0` + `input:0` |
| led | SNDC-0D4P10WW (Plus RGBWW) | G2 | `rgbw:0` (24 V DC) |

Originally split across two subnets (192.168.0.x + 192.168.1.x); **flattened onto one subnet (192.168.0.x) on 2026-06-09**, which is what enabled local live-verification of both backends. Multi-subnet discovery is still supported (see Architecture §discovery).

## 6b. Project identity & legal

- **Package name:** `shelly-mcp` — verified **free on PyPI** (also `shelly-mcp-server`, `mcp-shelly`). MCP Registry namespace `io.github.buggy1111/shelly-mcp`. Tool prefix `shelly_*`.
- **License:** recommend **MIT** (max adoption for community infra; differs from anonymize-mcp's non-commercial because there's no endorsement constraint here). One open decision: MIT vs Apache-2.0 — see `05-BUILD-PLAN.md §License`.
- **Trademark:** "Shelly" © Allterco Robotics. README/listings must state *"Unofficial community project, not affiliated with or endorsed by Allterco/Shelly."* See `05-BUILD-PLAN.md §Trademark`.
- **No conflict** with existing `mslavov/shelly-mcp` (GitHub, ⭐1, never published to PyPI under that name).

## 7. Documentation map

- `00-OVERVIEW.md` — this file
- `01-ARCHITECTURE.md` — full architecture + ADRs
- `02-TOOL-SURFACE.md` — every MCP tool, params, returns, annotations
- `03-SECURITY.md` — threat model, OWASP/LLM/ASI mapping, secrets, gates
- `04-CONFIG-AND-DEPLOY.md` — config UX, credentials, WSL networking, distribution
- `05-BUILD-PLAN.md` — milestones, DoD, roadmap, license/trademark
- `06-SCENES.md` — server-side named scenes design (ADR-007)
- `07-PROJECT-LOG.md` — what was built, the git, and the build timeline by day
- `API-CATALOG.md` — authoritative Shelly API reference (~45 components, 150+ methods)
