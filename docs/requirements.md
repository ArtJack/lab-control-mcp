# lab-control-mcp — Requirements (SDD)

> Spec-driven development artifact: *what* and *why*. See [design.md](design.md), [MCP.md](MCP.md).

## 1. Purpose
An **MCP server that operates a home AI lab** — health checks, model management, free local
inference, and a **safety-gated remote shell** — so any AI agent can run the lab without being
handed an unrestricted shell.

## 2. Users
- AI agents (e.g. Claude) connecting over MCP to operate the lab.
- The owner, via those agents, from any device over Tailscale.

## 3. Functional requirements
- **FR-1** `lab_status` — report health of machines/services.
- **FR-2** `list_models` — enumerate available local models.
- **FR-3** `gpu_generate` — run inference on the GPU box.
- **FR-4** `pull_model` — fetch a new local model.
- **FR-5** `restart_stack` — restart lab services.
- **FR-6** `run_smoke_tests` — verify the lab end-to-end.
- **FR-7** `run_command` — execute operator commands **through a safety gate**.

## 4. Non-functional requirements (the point of the project)
- **NFR-1 Safety gate.** `run_command` enforces a **prefix allowlist**, rejects shell
  metacharacters (no `;`, `|`, `&`, backticks, redirection), and applies timeouts — an agent gets
  *capability*, never an arbitrary shell.
- **NFR-2 Least privilege.** Only the enumerated tools are exposed; everything else is denied by default.
- **NFR-3 Reachable, not public.** stdio + HTTP, token-protected, only over Tailscale; nothing on the public internet.
- **NFR-4 Always-on.** Runs 24/7 under launchd.
- **NFR-5 Free by default.** Local inference; no cloud cost for routine operation.

## 5. Out of scope
- General-purpose remote administration beyond the allowlisted command set.

## 6. Acceptance criteria
- `run_command` rejects any input containing shell metacharacters or outside the allowlist. ✓
- All 7 tools usable by an external MCP client. ✓
- No tool can escalate to an unrestricted shell. ✓
