"""Offline tests for the safety-critical command gating."""
from __future__ import annotations

from labcontrol import ops
from labcontrol.config import cfg


def test_allowed_simple_command():
    ok, _ = ops.validate_command("ls -la /tmp", cfg.allowed_commands)
    assert ok


def test_disallowed_binary_blocked():
    ok, reason = ops.validate_command("rm -rf /", cfg.allowed_commands)
    assert not ok
    assert "allowlist" in reason


def test_metacharacters_are_blocked():
    for bad in [
        "ls; rm -rf /",
        "cat /etc/passwd | sh",
        "echo $(whoami)",
        "echo `id`",
        "ls > /etc/hosts",
        "ls < /dev/null",
        "true && rm x",
        "true || rm x",
        "echo $HOME",
        "ls \\\n rm",
    ]:
        ok, _ = ops.validate_command(bad, cfg.allowed_commands)
        assert not ok, f"should have blocked: {bad!r}"


def test_prefix_match_is_not_substring():
    # 'catalog' must NOT be accepted just because 'cat' is allowed
    ok, _ = ops.validate_command("catalog --list", cfg.allowed_commands)
    assert not ok


def test_empty_command_blocked():
    ok, _ = ops.validate_command("   ", cfg.allowed_commands)
    assert not ok


def test_run_command_rejects_without_executing(monkeypatch):
    calls = {"local": 0, "remote": 0}
    monkeypatch.setattr(ops, "run_local", lambda *a, **k: calls.__setitem__("local", calls["local"] + 1) or {})
    monkeypatch.setattr(ops, "run_remote", lambda *a, **k: calls.__setitem__("remote", calls["remote"] + 1) or {})
    out = ops.run_command("mini", "rm -rf /")
    assert out["allowed"] is False
    assert calls == {"local": 0, "remote": 0}


def test_run_command_bad_host():
    out = ops.run_command("hal9000", "ls")
    assert out["allowed"] is False
    assert "host" in out["error"]


def test_run_command_dispatches_allowed(monkeypatch):
    seen = {}
    monkeypatch.setattr(ops, "run_local", lambda cmd, t: seen.update(where="local", cmd=cmd) or {"allowed": True})
    monkeypatch.setattr(ops, "run_remote", lambda cmd, t: seen.update(where="remote", cmd=cmd) or {"allowed": True})
    ops.run_command("mini", "df -h")
    assert seen["where"] == "local"
    ops.run_command("alienware", "nvidia-smi")
    assert seen["where"] == "remote"


def test_pull_model_validates_name():
    assert ops.pull_model("m4", "bad name; rm").get("ok") is False
    assert ops.pull_model("nope", "llama3.1:8b").get("ok") is False


def test_extra_allowlist_via_env(monkeypatch):
    monkeypatch.setenv("LABCTL_ALLOWED_COMMANDS", "kubectl get,helm status")
    from importlib import reload

    from labcontrol import config as config_mod
    reload(config_mod)
    ok, _ = ops.validate_command("kubectl get pods", config_mod.cfg.allowed_commands)
    assert ok
    # restore the module-level singleton for other tests
    reload(config_mod)
