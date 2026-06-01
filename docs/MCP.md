# lab-control over MCP — connect & operate

Operate the lab from any MCP client. Inference and health checks flow through the
LiteLLM gateway and Ollama; ops run locally on the mini or over SSH to the Alienware.

## 1. Mac mini — Claude Code (stdio)

Ships a project-scoped `.mcp.json`; just run Claude Code in the repo:

```bash
cd ~/Projects/AI/projects/lab-control-mcp
claude        # the "lab-control" server is auto-loaded
```

Try: *"lab_status"*, *"list_models"*, *"run nvidia-smi -L on alienware"*,
*"pull qwen-coder onto gtx"*.

## 2. iPad / MacBook — over SSH or HTTP

- **SSH (stdio):** `ssh` into the mini over Tailscale and run the two lines above.
- **HTTP:** run the 24/7 service (below) and point a native MCP client at
  `http://100.81.78.74:8849/mcp` with `Authorization: Bearer <LABCTL_MCP_TOKEN>`.

## 3. Claude Desktop — stdio

```json
{
  "mcpServers": {
    "lab-control": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/artjack/Projects/AI/projects/lab-control-mcp", "labctl-mcp"]
    }
  }
}
```

## 4. Run it 24/7 on the Mac mini (launchd)

```bash
./deploy/install-mcp-service.sh      # generates a token into .env, binds to the Tailscale IP :8849
```

Manage it:

```bash
launchctl list | grep labcontrol
tail -f ~/Library/Logs/labcontrol-mcp.log
launchctl unload ~/Library/LaunchAgents/com.labcontrol.mcp.plist     # stop
```

> Runs alongside the `second-brain` MCP service (port 8848) — different label and port,
> so both can be on at once.

## Env knobs

| Env | Default | Meaning |
|---|---|---|
| `LABCTL_MCP_TRANSPORT` | `stdio` | `stdio` or `http`. |
| `LABCTL_MCP_HOST` / `LABCTL_MCP_PORT` | `127.0.0.1` / `8849` | HTTP bind. Use the Tailscale IP to share. |
| `LABCTL_MCP_TOKEN` | _(unset)_ | Bearer token required for HTTP. |
| `LABCTL_MCP_ALLOWED_HOSTS` | _(bind host + localhost)_ | Extra `Host` headers to accept (e.g. a MagicDNS name). |
| `LABCTL_ALLOWED_COMMANDS` | _(curated defaults)_ | Extra `run_command` prefixes to permit. |

## Verify

```bash
uv run pytest                                   # gating logic
# HTTP: expect 401 without the token, 200 with it
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8849/mcp -d '{}'
```
