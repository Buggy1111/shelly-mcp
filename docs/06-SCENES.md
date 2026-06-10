# Shelly MCP — Server-Side Named Scenes (design)

> **Implemented 2026-06-09** (`tools/scenes.py` + `scenes.py`, 23 tests, live-run on real
> hardware). This doc is the design of record; the decisions in §9 are LOCKED. Authored with
> senior-architect guidance. Mantra: *build the smallest thing that really lasts, isolate what
> will change, write it so it can be deleted without fear.*

## 0. The problem (questioned first)

Two scene paradigms exist. Today the server only has one:

| | LLM-driven (have it) | Server-defined named (missing) |
|---|---|---|
| Example | `shelly_evening_scene` prompt | scene `"film"` stored as device actions |
| Who decides the actions | the LLM, per run | fixed at definition time |
| Deterministic | no — varies with model/phrasing | **yes — identical every run** |
| Schedulable without an LLM | no | **yes** |
| Same across clients (Claude/Cursor/Hermes) | depends on the client's prompt | **yes — defined once** |

The missing half is the **#1 differentiator** — no competing Shelly MCP server has deterministic,
named, schedulable, cross-client scenes. This doc designs it.

**Non-goal:** replacing LLM-driven prompts. They stay (flexible, ad-hoc). Scenes are for the
repeated, "always do exactly this" cases ("film", "ráno", "vše pryč", "odchod z domu").

## 1. The key insight (why this is small)

A scene is **a saved, named, ordered batch of the call the server already makes everywhere**:

```
execute_and_audit(device, method, params)
```

That single primitive already gives us, for free:
- **Gen1↔Gen2 normalization** — `backend.call()` maps canonical methods to each generation.
- **Audit logging** — every scene action lands in the same audit trail as a manual action.
- **Method classification** — `methods.classify()` already labels READ / WRITE / DESTRUCTIVE.
- **Device resolution** — the registry already resolves friendly name / alias / location.

So a scene = `name` + a list of `{device, method, params}`. The exact same `{method, params}`
shape that `Schedule.Create`'s `calls` already uses. **Zero new execution path.** The whole
feature is: a place to store the list, validation at save time, and a runner that loops the
existing primitive and reports honestly.

## 2. Data model (a one-way door — it's a public contract)

```yaml
# scenes.yaml
scenes:
  film:
    description: "Movie night — TV off, kitchen LED dim, kitchen plug off"
    actions:
      - { device: televize, method: Switch.Set, params: { id: 0, on: false } }
      - { device: led,      method: Light.Set,  params: { id: 0, brightness: 15 } }
      - { device: mycka,    method: Switch.Set, params: { id: 0, on: false } }
  vse-pryc:
    description: "Leaving home — everything off"
    actions:
      - { device: televize, method: Switch.Set, params: { id: 0, on: false } }
      - { device: led,      method: Switch.Set, params: { id: 0, on: false } }
```

Pydantic:

```
SceneAction:  device: str   method: str   params: dict = {}
Scene:        description: str | None   actions: list[SceneAction]   # ≥1
SceneFile:    scenes: dict[str, Scene]                                # name -> Scene
```

Rules baked into the model / validation:
- `device` is a **friendly name/alias** (the stable handle) — **resolved at run time**, not stored
  as an IP. IPs change; names don't. (Validated to resolve *now* at create time, to catch typos.)
- `method` must be on the **control-method allowlist** (`Switch/Light/RGB/RGBW/CCT/Cover` writes —
  `methods.automation_allowed`). READs are rejected (a READ in a scene does nothing), DESTRUCTIVE is
  rejected (see §4), and so are gate-bypassing WRITEs like `Script.Eval`, `Script.PutCode`,
  `Shelly.SetAuth`, `Webhook.Create` — running those from a saved scene would skip the confirm gates
  their dedicated tools enforce. *(Tightened from "any non-destructive WRITE" by the 2026-06-10
  pre-launch audit; `schedule_create` enforces the same allowlist.)*
- Prefer **absolute** methods (`Switch.Set{on:false}`) over `Switch.Toggle`. Toggle is
  non-idempotent — running the scene twice undoes it. We **warn** on `.Toggle` at create, but allow it.

## 3. Storage (the real architectural decision)

**Decision: a dedicated `scenes.yaml`, separate from `config.yaml`, server-managed and human-editable.**

Default path `~/.config/shelly-mcp/scenes.yaml` (sibling of config, discoverable for hand-editing),
overridable via `$SHELLY_MCP_SCENES`. Written **atomically** (temp file + `os.replace`).

Options considered and rejected:

- **In `config.yaml`** — config is *hand-authored, secret-bearing (`chmod 600`), read-only at runtime*.
  Letting `scene_create` rewrite it means a tool programmatically editing a file that also holds
  device passwords + the cloud key — risking clobbered secrets, comments, and the 0600 safety logic.
  Mixing user-authored secrets with machine-written data in one file is a smell. **Rejected.**
- **Device KVS (Gen2 key-value store)** — KVS is *per-device*; a scene spans *multiple* devices. You'd
  have to nominate one device as the "scene host" → odd coupling + single point of failure (that device
  offline ⇒ all scenes gone) + KVS size limits. Cross-device data in one device's KVS is an
  anti-pattern. **Rejected.**
- **Shelly Cloud scenes** — violates local-first (ADR-001/004); cloud is the *degraded fallback*, never
  the source of truth. **Rejected as primary.**

Why a separate file wins: scenes are **machine-writable data with no secrets** → safe to rewrite
atomically, no 0600 entanglement, and still plain YAML a human can read, diff, back up, or
version-control. **Single source of truth** (no config-vs-state merge ambiguity over name collisions).

> Trade-off: scenes are not in the one file the user already knows. Mitigated by placing it right next
> to `config.yaml` and documenting it. If we ever want declarative, version-controlled scenes seeded
> from `config.yaml`, that's an *additive* read-only seed later — but YAGNI now (one source avoids
> "which wins on a name clash?").

Fail-soft on read: a missing or corrupt `scenes.yaml` ⇒ empty scene list + a logged warning, never a
crash (mirrors discovery's passive-and-cached posture).

## 4. Execution semantics (the 3 a.m. questions)

Physical smart-home actions are **not transactional** — you cannot reliably roll back a relay, and the
rollback itself can fail. Any "scene" that pretends to be atomic is lying. So:

1. **Best-effort, sequential, per-action result.** Run each action in order via `execute_and_audit`.
   Never abort the whole scene on one failure — a dead TV must not stop the kitchen lights. Return a
   structured per-action result and an overall status:

   ```
   { scene: "film", status: "partial",            # ok | partial | failed
     results: [
       { device: televize, method: Switch.Set, ok: true },
       { device: led,      method: Light.Set,  ok: false, error: "unreachable on LAN" },
       { device: mycka,    method: Switch.Set, ok: true } ] }
   ```
   `status`: `ok` (all succeeded), `partial` (some failed), `failed` (all failed). This honours
   `[[feedback_thorough_verify]]` — never report "done" when half of it didn't happen.

2. **Sequential, not parallel.** Deterministic, ordering preserved (some scenes need order: "amp on,
   then switch input"), easy to reason about, clear failure reporting. For ~4–10 devices the latency is
   fine. A `parallel: true` flag is a trivial *later* addition if a big fleet ever needs it — YAGNI now.

3. **Idempotent by construction.** Because actions use absolute `Set` states, re-running converges to
   the same physical state. So a `partial` run can simply be **re-run** later to finish — no special
   recovery logic needed. (This is *why* we steer scenes away from `Toggle`.)

4. **Anything outside the control allowlist is rejected at create time** (not merely confirm-gated at
   run). A named scene is meant to run unattended / scheduled; embedding `FactoryReset` — or
   `Script.Eval`, which reaches arbitrary device code — in a schedulable, LLM-runnable scene is exactly
   the hijack threat the security model guards (`docs/03-SECURITY` §5.3, LLM06/ASI02). Keeping scenes
   plain-control-only means `scene_run` needs **no confirm gate** → it stays clean to schedule.

## 5. Tool surface (mirrors `schedule_*` for consistency)

| Tool | Hint | Behaviour |
|---|---|---|
| `shelly_scene_list` | `readOnlyHint` | names + descriptions + action counts |
| `shelly_scene_get(name)` | `readOnlyHint` | full definition (inspect before run/edit) |
| `shelly_scene_run(name)` | (mutating, audited) | execute; returns per-action results + status |
| `shelly_scene_create(name, actions, description?, overwrite=false)` | `idempotentHint` | validate + save; fails on existing name unless `overwrite=true` |
| `shelly_scene_delete(name, confirm=false)` | `destructiveHint` | remove; requires `confirm:true` |

`create` with `overwrite` covers update too → 5 tools, not 6. Validation in `create`:
every `device` resolves, every `method` is on the control allowlist, `.Toggle` ⇒ warning in the
response (not an error). `scene_run` itself needs no confirm gate (plain control by construction).

## 6. Scheduling & cross-network (how scenes pay off — and what we deliberately defer)

This is where named scenes beat ad-hoc prompts, and where the layering matters.

- **Single-device scene** ⇒ can be pushed into that device's **native `Schedule.Create`** (the device
  runs it autonomously — no server, no LLM, survives reboot, works cross-network). A future
  `shelly_scene_to_schedule(name, timespec)` nicety can do this automatically. *Defer to v1.1.*
- **Any scene, on demand** ⇒ any MCP client's own scheduler calls `shelly_scene_run`. Hermes already
  has cron; Claude Code has `CronCreate`. **This already delivers "deterministic + schedulable +
  cross-client" with zero new server machinery.**

**Deliberate non-decision: do NOT build a server-side scheduler daemon yet** (roadmap item #3). The
server is **stdio, request/response** (ADR-004/006) — it intentionally avoids daemon/background-loop
machinery. A long-running scheduler inside an stdio MCP is an architectural wart and a process-lifecycle
problem (who keeps it alive? what fires it when no client is connected?). Existing crons (Hermes / Claude
Code) cover the cross-network scheduled case today. Only build a server-side scheduler if a concrete need
appears that crons genuinely can't serve — and if so, as a **separate** long-lived process, not bolted
into the stdio server.

## 7. What this is NOT (scope discipline)

- ❌ No transactions / rollback (physical actions aren't transactional — best-effort + honest report).
- ❌ No KVS / cloud storage (cross-device coupling / not local-first).
- ❌ No parallel execution v1 (sequential is correct at this scale).
- ❌ No destructive methods in scenes (security; fail-closed).
- ❌ No server-side scheduler daemon (stdio server stays request/response; crons suffice).
- ❌ No dual config/state source of truth (one file, no merge ambiguity).

Estimated footprint: one `tools/scenes.py` vertical slice + a small `scenes.py` store (load/save/atomic)
+ Pydantic models + tests. ~150–200 LOC. Boring and correct.

## 8. ADR-007 (recorded in 01-ARCHITECTURE.md)

Storage = dedicated `scenes.yaml`; model = reuse `{device, method, params}` + `execute_and_audit`;
execution = best-effort sequential with per-action results (no transactions); security = control-method
allowlist only; scheduling = lean on device-native `Schedule` + client crons, **no scheduler daemon yet**.

## 9. Decisions — LOCKED (2026-06-09, confirmed by Michal)

1. **Scene file location** — `~/.config/shelly-mcp/scenes.yaml` (sibling of config, hand-editable),
   env override `$SHELLY_MCP_SCENES`. ✅ **Locked.**
2. **v1 scope** — the **5 tools only** (`list / get / run / create / delete`). The
   `scene_to_schedule` bridge is deferred to v1.1. ✅ **Locked.**
3. **Seed scenes from `config.yaml`** — **no**, single source of truth (`scenes.yaml` only). Revisit
   only if version-controlled declarative scenes are wanted later. ✅ **Locked.**

## 10. Build plan (next session — `finish-the-job` + tests)

Definition of Done: 5 tools live, registered, mypy `--strict` + ruff clean, full unit coverage
(scene CRUD round-trip, atomic write, corrupt-file fail-soft, validation: unknown device / READ method
rejected / DESTRUCTIVE rejected / `.Toggle` warning, run with `ok|partial|failed` paths against fakes),
`config.example.yaml` + `scenes.example.yaml` + README updated, all green before declaring done.

1. `models.py` (or `scenes.py`): `SceneAction`, `Scene`, `SceneFile` Pydantic models.
2. `scenes_store.py`: load (fail-soft), atomic save (`os.replace`), path resolution
   (`$SHELLY_MCP_SCENES` → `~/.config/shelly-mcp/scenes.yaml`).
3. `tools/scenes.py`: the 5 tools, validation reusing `methods.classify()`, runner reusing
   `execute_and_audit` (best-effort sequential, per-action results).
4. Register in `tools/__init__.py`; extend FastMCP `instructions` with a one-line scene hint.
5. Tests in `tests/unit/`; ship `scenes.example.yaml`.
