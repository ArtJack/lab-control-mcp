# lab-control-mcp

An **MCP server that operates the home AI lab** — health checks, model management,
free local inference, and a *gated* remote shell across the **Mac mini (M4)** and the
**Alienware (GTX 1070)**. Point any MCP client at it (Claude Code/Desktop, or a native
iPad/MacBook client over Tailscale) and direct the lab from anywhere.

```bash
uv sync
cp .env.example .env          # set LITELLM_MASTER_KEY for gpu_generate
uv run labctl-mcp             # stdio; or LABCTL_MCP_TRANSPORT=http … for the network
```

## Tools

| Tool | Kind | What it does |
|---|---|---|
| `lab_status` | read | Health of gateway (LAN + Tailscale), Ollama (M4 + GTX), Qdrant, Postgres exposure. |
| `list_models` | read | Ollama models on each host. |
| `gpu_generate` | read | Inference via the LiteLLM gateway (`chat`/`code`/`embed` are free local; `claude` is paid). |
| `pull_model` | write | `ollama pull` a model onto `m4` or `gtx`. |
| `restart_stack` | **danger** | Re-apply the Alienware stack (LiteLLM/Qdrant/Postgres) via its deploy script. |
| `run_smoke_tests` | write | Run `local-agent-lab`'s smoke tests on the mini. |
| `run_command` | **danger** | Run an **allow-listed** command on `mini` (local) or `alienware` (SSH). |

## The interesting decision: a *gated* shell, not a raw one

`run_command` is the "operate my machines while away" capability — so it's deliberately
constrained, defense-in-depth:

1. **No shell.** Local commands run via `shlex.split` + `subprocess` argv (no `shell=True`),
   so there's no local injection surface.
2. **No metacharacters.** `;` `|` `&` `<` `>` `` ` `` `$` `\` and newlines are rejected, so a
   command can't chain, redirect, or substitute — which also keeps the remote (SSH) path
   safe, since the Alienware's shell only ever receives one simple command.
3. **Allowlist, not denylist.** The command must match a curated prefix list
   (`config.py`), extendable per-deployment via `LABCTL_ALLOWED_COMMANDS`. Unknown
   commands return a **structured error**, not an exception — so an agent can recover.
4. **Timeouts + truncated, captured output** on every call.

Powerful operations (restart the stack, pull a model) are exposed as their own
named tools with validated arguments, rather than as free-form shell.

## Architecture

```
MCP client ──stdio/HTTP──▶ lab-control ──┬─ httpx ─▶ LiteLLM gateway  (inference, health)
                                         ├─ httpx ─▶ Ollama M4 / GTX  (models, health)
                                         ├─ socket ▶ Qdrant / Postgres (health)
                                         └─ subprocess ─▶ local (mini) / ssh alienware
```

Everything flows through the **LiteLLM gateway** for inference, so it inherits the lab's
free-local-first routing and budget cap — no model is called any other way.

## Transports & security

- **stdio** (default) — auto-loaded by Claude Code from `.mcp.json`.
- **Streamable HTTP** — token-protected (pure-ASGI bearer gate) with a DNS-rebinding host
  allow-list; meant to sit on the Tailscale IP. `deploy/` ships a launchd plist + installer
  for 24/7 operation on the mini. See [docs/MCP.md](docs/MCP.md).

Secrets (`LITELLM_MASTER_KEY`, `QDRANT_API_KEY`, `LABCTL_MCP_TOKEN`) live only in the
git-ignored `.env`.

## Config

See `.env.example`. Key vars: `LITELLM_BASE_URL(_TS)`, `LITELLM_MASTER_KEY`, `OLLAMA_M4`,
`OLLAMA_GTX`, `QDRANT_URL`/`QDRANT_API_KEY`, `LABCTL_ALIENWARE_SSH` (ssh alias),
`LABCTL_LAB_DIR`, `LABCTL_ALLOWED_COMMANDS`, and the `LABCTL_MCP_*` transport vars.

## Tests

```bash
uv run pytest        # offline; covers the command-gating safety logic
```
