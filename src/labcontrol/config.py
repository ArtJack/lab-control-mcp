"""Central configuration for lab-control, loaded from .env.

No secrets are hard-coded; keys come from the environment. Defaults match the
home lab (see README-MAC-MINI-ACCESS.md) and can be overridden via env.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Curated, read-mostly command prefixes that `run_command` permits by default.
# Powerful/destructive actions are intentionally excluded — extend per-deployment
# via LABCTL_ALLOWED_COMMANDS, or use the dedicated tools (restart_stack, pull_model).
DEFAULT_ALLOWED_COMMANDS = [
    "ls", "pwd", "cat", "head", "tail", "wc", "stat", "file",
    "df", "du", "free", "uptime", "whoami", "hostname", "date", "uname", "sw_vers", "id", "sysctl",
    "ps", "pgrep", "vm_stat",
    "grep", "echo",
    "nvidia-smi",
    "ollama list", "ollama ps", "ollama show", "ollama pull",
    "docker ps", "docker logs", "docker stats", "docker images", "docker inspect", "docker compose ls",
    "systemctl status", "systemctl is-active", "journalctl",
    "curl -s", "ping -c", "ip", "ifconfig", "ss", "netstat",
    "git status", "git log", "git pull", "git fetch", "git branch", "git rev-parse",
    "python --version", "python3 --version", "pip list",
    "wsl --status", "wsl -l",
]
# NOTE: interpreters / exec-wrappers are deliberately NOT in the defaults
# ("uv run", bare "python"/"python3 -c", "ssh", "bash"/"sh", "docker exec"/"docker run",
# "wsl -d/-e ...") — each would let a caller smuggle arbitrary code past the gate.
# Keep them out; extend with care via LABCTL_ALLOWED_COMMANDS for safe, specific ops.


class Config:
    def __init__(self) -> None:
        self.gateway_url = os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000")
        self.gateway_url_ts = os.getenv("LITELLM_BASE_URL_TS", "http://127.0.0.1:4000")
        self.master_key = os.getenv("LITELLM_MASTER_KEY") or None

        self.ollama_m4 = os.getenv("OLLAMA_M4", "http://127.0.0.1:11434")
        self.ollama_gtx = os.getenv("OLLAMA_GTX", "http://127.0.0.1:11434")

        self.qdrant_url = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
        self.qdrant_api_key = os.getenv("QDRANT_API_KEY") or None

        self.alienware_ssh = os.getenv("LABCTL_ALIENWARE_SSH", "alienware")
        self.lab_dir = os.path.expanduser(
            os.getenv("LABCTL_LAB_DIR", "~/Projects/AI/projects/local-agent-lab")
        )
        self.http_timeout = float(os.getenv("LABCTL_HTTP_TIMEOUT", "5"))
        self.cmd_timeout = int(os.getenv("LABCTL_CMD_TIMEOUT", "30"))

        self.allowed_commands = self._allowed_commands()

    def _allowed_commands(self) -> list[str]:
        allowed = list(DEFAULT_ALLOWED_COMMANDS)
        for extra in os.getenv("LABCTL_ALLOWED_COMMANDS", "").split(","):
            extra = extra.strip()
            if extra:
                allowed.append(extra)
        return allowed


cfg = Config()
