"""Lab operations — pure functions the MCP tools wrap.

Safety model for ``run_command``:
  * No shell is used (``shlex.split`` + ``subprocess`` argv) for local execution,
    so there is no shell-injection surface locally.
  * Shell metacharacters are rejected outright, so a command can neither chain
    (``;`` ``&&`` ``|``) nor redirect (``>`` ``<``) nor substitute (`` ` `` ``$()``)
    — this also keeps remote (ssh) execution safe, since the remote shell only
    ever receives a single simple command.
  * The command must match an explicit allowlist of prefixes (see config).
  * Every execution has a timeout and captured, truncated output.
"""
from __future__ import annotations

import shlex
import socket
import subprocess
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from .config import cfg

_FORBIDDEN_CHARS = set(";|&<>`$\\\n\r")
_OUT_LIMIT = 8000
_ERR_LIMIT = 4000
_MODEL_NAME_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-/")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# ------------------------------------------------------------------ diagnostics

def _http_ok(url: str) -> bool:
    try:
        r = httpx.get(url, timeout=cfg.http_timeout)
        return r.status_code < 500
    except Exception:
        return False


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=cfg.http_timeout):
            return True
    except OSError:
        return False


def ollama_models(base_url: str) -> list[str]:
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=cfg.http_timeout)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def lab_status() -> dict:
    """Health of every lab service, mirroring `ailab status`."""
    gtx_host = urlparse(cfg.ollama_gtx).hostname or "192.168.1.159"
    return {
        "checked_at": _now(),
        "gateway": {
            "lan": _http_ok(f"{cfg.gateway_url}/health/liveliness"),
            "tailscale": _http_ok(f"{cfg.gateway_url_ts}/health/liveliness"),
        },
        "ollama": {
            "m4": _http_ok(f"{cfg.ollama_m4}/api/tags"),
            "gtx": _http_ok(f"{cfg.ollama_gtx}/api/tags"),
        },
        "qdrant": _http_ok(f"{cfg.qdrant_url}/"),
        # On LAN, reachable Postgres means the lockdown is NOT deployed (a warning).
        "postgres_exposed_on_lan": _port_open(gtx_host, 5432),
    }


def list_models() -> dict:
    return {"m4": ollama_models(cfg.ollama_m4), "gtx": ollama_models(cfg.ollama_gtx)}


def gateway_generate(prompt: str, model: str = "chat", max_tokens: int = 512) -> dict:
    """Run inference through the LiteLLM gateway (free local models by default)."""
    if not cfg.master_key:
        return {"error": "LITELLM_MASTER_KEY not set", "hint": "add it to .env (from /opt/ai-lab/.env on the Alienware)"}
    try:
        r = httpx.post(
            f"{cfg.gateway_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {cfg.master_key}"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
            timeout=120,
        )
        r.raise_for_status()
        return {"model": model, "text": r.json()["choices"][0]["message"]["content"]}
    except httpx.HTTPStatusError as exc:
        return {"error": f"gateway returned {exc.response.status_code}", "details": exc.response.text[:500]}
    except Exception as exc:
        return {"error": str(exc)}


# --------------------------------------------------------------- command gating

def validate_command(command: str, allowed: list[str]) -> tuple[bool, str]:
    cmd = command.strip()
    if not cmd:
        return False, "empty command"
    if any(c in _FORBIDDEN_CHARS for c in cmd):
        return False, "shell metacharacters are not allowed (no ; | & < > ` $ \\ or newlines)"
    if not any(cmd == p or cmd.startswith(p + " ") for p in allowed):
        return False, "command is not in the allowlist; extend LABCTL_ALLOWED_COMMANDS to permit it"
    return True, "ok"


def _result(host: str, command: str, proc: subprocess.CompletedProcess) -> dict:
    return {
        "host": host,
        "command": command,
        "allowed": True,
        "exit_code": proc.returncode,
        "timed_out": False,
        "stdout": (proc.stdout or "")[:_OUT_LIMIT],
        "stderr": (proc.stderr or "")[:_ERR_LIMIT],
    }


def run_local(command: str, timeout: int) -> dict:
    try:
        proc = subprocess.run(shlex.split(command), capture_output=True, text=True, timeout=timeout)
        return _result("mini", command, proc)
    except subprocess.TimeoutExpired:
        return {"host": "mini", "command": command, "allowed": True, "timed_out": True, "exit_code": None, "stdout": "", "stderr": f"timed out after {timeout}s"}
    except FileNotFoundError as exc:
        return {"host": "mini", "command": command, "allowed": True, "timed_out": False, "exit_code": 127, "stdout": "", "stderr": str(exc)}


def run_remote(command: str, timeout: int) -> dict:
    try:
        proc = subprocess.run(["ssh", cfg.alienware_ssh, command], capture_output=True, text=True, timeout=timeout)
        return _result("alienware", command, proc)
    except subprocess.TimeoutExpired:
        return {"host": "alienware", "command": command, "allowed": True, "timed_out": True, "exit_code": None, "stdout": "", "stderr": f"timed out after {timeout}s"}


def run_command(host: str, command: str, timeout: int | None = None) -> dict:
    """Run an allow-listed command on 'mini' (local) or 'alienware' (ssh)."""
    if host not in ("mini", "alienware"):
        return {"allowed": False, "host": host, "command": command, "error": "host must be 'mini' or 'alienware'"}
    ok, reason = validate_command(command, cfg.allowed_commands)
    if not ok:
        return {"allowed": False, "host": host, "command": command, "error": reason}
    t = timeout or cfg.cmd_timeout
    return run_local(command, t) if host == "mini" else run_remote(command, t)


# ----------------------------------------------------------------- curated ops

def _valid_model_name(name: str) -> bool:
    return bool(name) and all(c in _MODEL_NAME_OK for c in name)


def pull_model(host: str, name: str, timeout: int = 600) -> dict:
    """Pull an Ollama model on 'm4' (local) or 'gtx' (Alienware)."""
    if host not in ("m4", "gtx"):
        return {"ok": False, "error": "host must be 'm4' or 'gtx'"}
    if not _valid_model_name(name):
        return {"ok": False, "error": "invalid model name"}
    command = f"ollama pull {name}"
    res = run_local(command, timeout) if host == "m4" else run_remote(command, timeout)
    res["ok"] = res.get("exit_code") == 0
    return res


def restart_stack(timeout: int = 180) -> dict:
    """Re-apply the Alienware stack (LiteLLM/Qdrant/Postgres) via its deploy script."""
    command = "wsl -d Ubuntu-24.04 -u root bash /mnt/e/ai-lab-setup/deploy-stack.sh"
    res = run_remote(command, timeout)
    res["ok"] = res.get("exit_code") == 0
    return res


def run_smoke_tests(timeout: int = 180) -> dict:
    """Run local-agent-lab's smoke tests on the Mac mini."""
    try:
        proc = subprocess.run(
            ["uv", "run", "python", "agent_smoke_test.py"],
            cwd=cfg.lab_dir, capture_output=True, text=True, timeout=timeout,
        )
        out = _result("mini", "uv run python agent_smoke_test.py", proc)
        out["ok"] = proc.returncode == 0
        return out
    except subprocess.TimeoutExpired:
        return {"ok": False, "timed_out": True, "stderr": f"timed out after {timeout}s"}
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc), "hint": f"is {cfg.lab_dir} present?"}
