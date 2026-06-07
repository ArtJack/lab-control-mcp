# lab-control-mcp — Design (SDD)

> How the system meets [requirements.md](requirements.md). See also [MCP.md](MCP.md).

## 1. Architecture
```
 AI agent ──MCP (stdio/HTTP, token, Tailscale)──▶ lab-control server
                                                      │
        ┌──────────────┬──────────────┬──────────────┼───────────────┐
        ▼              ▼              ▼              ▼               ▼
   lab_status     list_models     gpu_generate   restart_stack   run_command
   (health)       (inventory)     (inference)    (lifecycle)     (GATED)
                                                                   │
                                          prefix allowlist + no shell metacharacters + timeout
```

## 2. Key design decisions
1. **Capability, not a shell.** The whole design exists to give an agent useful operations
   *without* an arbitrary shell. `run_command` is the riskiest tool, so it carries the strictest gate.
2. **Defense in depth on `run_command`.** (a) prefix allowlist — only known-safe command roots;
   (b) reject shell metacharacters so nothing can chain/escape; (c) hard timeouts.
3. **Deny by default.** Only the seven enumerated tools exist; no generic passthrough.
4. **Private transport.** Token-protected MCP over Tailscale only — never exposed publicly.
5. **Operational durability.** launchd keeps it always-on; `run_smoke_tests` proves the lab works.

## 3. Components
- **MCP layer** — registers the 7 tools over stdio + HTTP.
- **Safety gate** — validates/normalizes `run_command` input before execution.
- **Lab adapters** — talk to Ollama / the gateway / system services for status, models, inference, restart.

## 4. Testing
- Unit tests on the safety gate: metacharacter rejection, allowlist enforcement, timeout behavior.
- Smoke tests exercise the full lab path end-to-end.
