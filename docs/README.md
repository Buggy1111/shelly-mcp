# shelly-mcp — Documentation

The full design, security model, and build history of `shelly-mcp` — an MCP server for the entire
Shelly smart-home ecosystem (Gen1–Gen4 + BLU), local-first with cloud fallback. Start at the
overview, then dive into whichever layer you need.

> New here? Read **[00-OVERVIEW](./00-OVERVIEW.md)** first, then **[01-ARCHITECTURE](./01-ARCHITECTURE.md)**.

## Design

| Doc | What's inside |
|---|---|
| [00-OVERVIEW](./00-OVERVIEW.md) | Scope, why it exists, competitive landscape, what makes it stand out, identity/licence/trademark. |
| [01-ARCHITECTURE](./01-ARCHITECTURE.md) | Layers, `ShellyClient`, the three backends, the `Normalizer`, discovery, zero-code auto-onboarding, and the ADRs (001–007). |
| [02-TOOL-SURFACE](./02-TOOL-SURFACE.md) | Every tool, resource, and prompt — signatures, behaviour, and MCP annotations. |
| [03-SECURITY](./03-SECURITY.md) | Threat model, OWASP / LLM / Agentic-AI mapping, the confirm-gate design, and the audit log. |
| [06-SCENES](./06-SCENES.md) | Server-side named scenes — storage, execution semantics, safety (ADR-007). |

## Operate

| Doc | What's inside |
|---|---|
| [04-CONFIG-AND-DEPLOY](./04-CONFIG-AND-DEPLOY.md) | Config file UX, env overrides, WSL networking, and distribution. |

## Build & process

| Doc | What's inside |
|---|---|
| [05-BUILD-PLAN](./05-BUILD-PLAN.md) | The milestone sequence (M0–M5 + scenes + automation) with a Definition of Done per step. |
| [07-PROJECT-LOG](./07-PROJECT-LOG.md) | An honest narrative of what was built, the repo/git, and the day-by-day timeline. |
| [08-LAUNCH-CHECKLIST](./08-LAUNCH-CHECKLIST.md) | The runbook to go public (PyPI → MCP Registry → Glama → awesome-mcp), with local gates pre-verified. |
| [ROADMAP](./ROADMAP.md) | Post-launch plan — energy history (local EM/EMData + optional logger) and demand-driven candidates. |

## Reference

| Doc | What's inside |
|---|---|
| [API-CATALOG](./API-CATALOG.md) | The complete Shelly API surface (Gen1 REST + Gen2+ RPC) — ~45 components, 150+ methods, all 8 sections. The authoritative backbone the tools are built against. |

---

*This server is an **unofficial community project** — not affiliated with, endorsed by, or sponsored
by Allterco Robotics / Shelly. Released under the MIT licence.*
