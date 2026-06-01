"""MCP server to operate the home AI lab.

Exposes diagnostics, model ops, and a *gated* remote shell across the Mac mini and
the Alienware as MCP tools, so an agent (or you, from the iPad) can run and direct
the lab. Free-local inference by default via the LiteLLM gateway.

Transports (env LABCTL_MCP_TRANSPORT): `stdio` (default) or `http` (Streamable HTTP).
HTTP env: LABCTL_MCP_HOST / LABCTL_MCP_PORT / LABCTL_MCP_TOKEN / LABCTL_MCP_ALLOWED_HOSTS.

Run:
    uv run labctl-mcp                                          # stdio
    LABCTL_MCP_TRANSPORT=http LABCTL_MCP_TOKEN=… uv run labctl-mcp
"""
from __future__ import annotations

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from . import ops
from .config import cfg

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("labcontrol.mcp")


def _transport_security() -> TransportSecuritySettings:
    host = os.getenv("LABCTL_MCP_HOST", "127.0.0.1")
    port = os.getenv("LABCTL_MCP_PORT", "8849")
    hosts = {host, f"{host}:{port}", "localhost", f"localhost:{port}", "127.0.0.1", f"127.0.0.1:{port}"}
    for extra in os.getenv("LABCTL_MCP_ALLOWED_HOSTS", "").split(","):
        if extra.strip():
            hosts.add(extra.strip())
    allowed_hosts = sorted(hosts)
    return TransportSecuritySettings(
        allowed_hosts=allowed_hosts,
        allowed_origins=sorted({f"http://{h}" for h in allowed_hosts}),
    )


mcp = FastMCP(
    "lab-control",
    instructions=(
        "Operate the home AI lab (Mac mini M4 + Alienware GTX, LiteLLM gateway, "
        "Qdrant, Ollama). Use `lab_status` and `list_models` to see what's healthy, "
        "`gpu_generate` for free local inference via the gateway, `pull_model` / "
        "`restart_stack` / `run_smoke_tests` for safe ops, and `run_command` to run "
        "an allow-listed command on 'mini' or 'alienware'. run_command rejects shell "
        "metacharacters and anything outside the allowlist — report the structured "
        "error rather than retrying blindly."
    ),
    transport_security=_transport_security(),
)

_RO = ToolAnnotations(readOnlyHint=True)
_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
_DANGER = ToolAnnotations(readOnlyHint=False, destructiveHint=True)


@mcp.tool(annotations=_RO)
def lab_status() -> dict:
    """Health of every lab service: gateway (LAN + Tailscale), Ollama (M4 + GTX), Qdrant, Postgres exposure."""
    return ops.lab_status()


@mcp.tool(annotations=_RO)
def list_models() -> dict:
    """List the Ollama models available on the Mac mini (m4) and the Alienware (gtx)."""
    return ops.list_models()


@mcp.tool(annotations=_RO)
def gpu_generate(prompt: str, model: str = "chat", max_tokens: int = 512) -> dict:
    """Run inference through the LiteLLM gateway.

    Args:
        prompt: The user prompt.
        model: Gateway model alias — `chat`/`code`/`embed` are free local models;
            `claude` is the paid escalation (budget-capped). Defaults to free `chat`.
        max_tokens: Max tokens to generate.
    """
    return ops.gateway_generate(prompt, model=model, max_tokens=max_tokens)


@mcp.tool(annotations=_WRITE)
def pull_model(host: str, name: str) -> dict:
    """Pull an Ollama model onto a host.

    Args:
        host: 'm4' (Mac mini) or 'gtx' (Alienware).
        name: Model name, e.g. 'llama3.1:8b'.
    """
    return ops.pull_model(host, name)


@mcp.tool(annotations=_DANGER)
def restart_stack() -> dict:
    """Re-apply / restart the Alienware stack (LiteLLM, Qdrant, Postgres) via its deploy script."""
    return ops.restart_stack()


@mcp.tool(annotations=_WRITE)
def run_smoke_tests() -> dict:
    """Run local-agent-lab's smoke tests on the Mac mini and return the output."""
    return ops.run_smoke_tests()


@mcp.tool(annotations=_DANGER)
def run_command(host: str, command: str, timeout: int = 0) -> dict:
    """Run an ALLOW-LISTED command on a lab host.

    Safety: shell metacharacters (; | & < > ` $ \\) are rejected, and the command
    must match the configured allowlist. Disallowed commands return a structured
    error (not an exception). Output is captured and truncated.

    Args:
        host: 'mini' (Mac mini, run locally) or 'alienware' (run over SSH).
        command: The command to run (must be allow-listed).
        timeout: Seconds (0 = configured default).
    """
    return ops.run_command(host, command, timeout=timeout or None)


class _BearerAuthASGI:
    """Pure-ASGI bearer-token gate (does not buffer the Streamable-HTTP stream)."""

    def __init__(self, app, token: str):
        self.app = app
        self._expected = f"Bearer {token}"

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            if headers.get(b"authorization", b"").decode() != self._expected:
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
                return
        await self.app(scope, receive, send)


def _run_http() -> None:
    import uvicorn

    host = os.getenv("LABCTL_MCP_HOST", "127.0.0.1")
    port = int(os.getenv("LABCTL_MCP_PORT", "8849"))
    token = os.getenv("LABCTL_MCP_TOKEN")

    app = mcp.streamable_http_app()
    if token:
        app = _BearerAuthASGI(app, token)
        log.info("HTTP transport: bearer-token auth ENABLED")
    else:
        log.warning("HTTP transport: NO token set (LABCTL_MCP_TOKEN) — endpoint is open on %s:%s", host, port)
    log.info("Serving lab-control MCP at http://%s:%s/mcp", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> None:
    transport = os.getenv("LABCTL_MCP_TRANSPORT", "stdio").strip().lower()
    if transport in {"http", "streamable-http", "streamable_http"}:
        _run_http()
    else:
        log.info("Serving lab-control MCP over stdio")
        mcp.run()


if __name__ == "__main__":
    main()
