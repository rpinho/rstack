"""Exercise the public inbox CLI, hook boundary and isolated installation."""
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tempfile

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "harness/tools/conductor-inbox"


@pytest.fixture
def inbox_env(tmp_path):
    home = tmp_path / "home with spaces"
    home.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(
        ("CONDUCTOR_", "EVENT_WATCH_", "XDG_"))}
    env.update(HOME=str(home), CONDUCTOR_INBOX_DIR=str(home / "custom state/inbox"),
               CONDUCTOR_NAME="coordinator", CLAUDE_SESSION_NAME="worker")
    return env


def run(script, *args, env, payload=None):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], env=env,
                          input=payload, text=True, capture_output=True, timeout=10, check=True)


def gate(env, target, tool="SendMessage"):
    result = run("conductor-inbox-gate.py", env=env,
                 payload=json.dumps({"tool_name": tool, "tool_input": {"to": target}}))
    return json.loads(result.stdout) if result.stdout else None


@pytest.mark.parametrize("style", ["name", "decorated-name", "address", "raw-address", "annotated-address"])
def test_gate_denies_conductor_name_and_socket(inbox_env, style):
    root = Path(inbox_env["CONDUCTOR_INBOX_DIR"])
    root.mkdir(parents=True)
    address = root / "session.sock"
    (root / "conductor.addr").write_text(f"uds:{address}\n")
    target = {"name": "coordinator", "decorated-name": " coordinator [active] ",
              "address": f"uds:{address}", "raw-address": str(address),
              "annotated-address": f"worker [uds:{address}]"}[style]
    result = gate(inbox_env, target)["hookSpecificOutput"]
    assert result["hookEventName"] == "PreToolUse"
    assert result["permissionDecision"] == "deny"
    assert "tell-conductor" in result["permissionDecisionReason"]


@pytest.mark.parametrize("target", ["worker", "", "coordinator-helper", "uds:/tmp/other.sock"])
def test_gate_allows_other_targets_without_an_address_file(inbox_env, target):
    assert gate(inbox_env, target) is None


def test_gate_allows_other_targets_and_tools_with_an_address_file(inbox_env):
    root = Path(inbox_env["CONDUCTOR_INBOX_DIR"])
    root.mkdir(parents=True)
    (root / "conductor.addr").write_text("uds:/tmp/synthetic.sock\n")
    assert gate(inbox_env, "uds:/tmp/synthetic.sock-other") is None
    assert gate(inbox_env, "worker") is None
    assert gate(inbox_env, "coordinator", tool="Bash") is None


def test_gate_keeps_name_blocked_before_install(inbox_env):
    assert gate(inbox_env, "coordinator")["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("kind,wake", [("fyi", False), ("decision", True), ("human", True),
                                       ("break", True), ("operator-request", True)])
def test_cli_files_message_and_only_escalations_create_wakes(inbox_env, kind, wake):
    inbox_env["CONDUCTOR_HUMAN_KIND"] = "operator-request"
    run("tell-conductor", "--from", "../unsafe/sender", kind, "Synthetic", "message ☃", env=inbox_env)
    root = Path(inbox_env["CONDUCTOR_INBOX_DIR"])
    rows = [json.loads(line) for line in (root / "inbox.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0] == {"utc": rows[0]["utc"], "from": "../unsafe/sender",
                       "kind": kind, "text": "Synthetic message ☃"}
    assert rows[0]["utc"].endswith("Z")
    markers = list((root / "wake").glob("*"))
    assert len(markers) == int(wake)
    if wake:
        assert markers[0].read_text() == rows[0]["text"]
        assert "sender" not in markers[0].name
    else:
        assert not (root / "wake").exists()


def test_cli_alias_and_defaults_append_without_losing_rows(inbox_env):
    for key in ("CONDUCTOR_INBOX_DIR", "CONDUCTOR_NAME"):
        inbox_env.pop(key)
    for script in ("tell-general", "tell-conductor"):
        run(script, "fyi", "Synthetic message", env=inbox_env)
    root = Path(inbox_env["HOME"]) / ".local/state/conductor-inbox"
    rows = [json.loads(line) for line in (root / "inbox.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert all(row["from"] == "worker" for row in rows)
    assert not (root / "wake").exists()
    assert gate(inbox_env, "conductor")["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_cli_and_gate_agree_on_xdg_default(inbox_env):
    inbox_env.pop("CONDUCTOR_INBOX_DIR")
    inbox_env["XDG_STATE_HOME"] = str(Path(inbox_env["HOME"]) / "xdg state")
    run("tell-conductor", "human", "Synthetic request", env=inbox_env)
    root = Path(inbox_env["XDG_STATE_HOME"]) / "conductor-inbox"
    assert len(list((root / "wake").iterdir())) == 1
    (root / "conductor.addr").write_text("uds:/tmp/synthetic.sock\n")
    assert gate(inbox_env, "/tmp/synthetic.sock")["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("args", [[], ["--from"], ["unknown", "message"], ["fyi"]])
def test_cli_rejects_bad_arguments_before_filing(inbox_env, args):
    with pytest.raises(subprocess.CalledProcessError):
        run("tell-conductor", *args, env=inbox_env)
    assert not Path(inbox_env["CONDUCTOR_INBOX_DIR"]).exists()


def install(env, *args):
    return subprocess.run([str(SCRIPTS / "install-conductor-inbox.sh"), *args], env=env,
                          text=True, capture_output=True, timeout=10)


@pytest.mark.parametrize("custom", [False, True])
def test_installer_is_idempotent_and_rebinds_after_restart(inbox_env, custom):
    env = inbox_env
    home = Path(env["HOME"])
    (home / ".claude").mkdir()
    unrelated = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo synthetic"}]}
    settings_path = home / ".claude/settings.json"
    settings_path.write_text(json.dumps({"otherSetting": True, "hooks": {"PreToolUse": [unrelated]}}))
    if custom:
        env["EVENT_WATCH_CONF"] = str(home / "watch config")
        env["EVENT_WATCH_STATE"] = str(home / "watch state")
    else:
        env.pop("CONDUCTOR_INBOX_DIR")
        env.pop("CONDUCTOR_NAME")
    # Unix socket paths have a short OS limit, independent of pytest's root.
    with tempfile.TemporaryDirectory(prefix="inbox-sock-", dir="/tmp") as socket_dir:
        env["CONDUCTOR_SOCKET_DIR"] = socket_dir
        with socket.socket(socket.AF_UNIX) as first, socket.socket(socket.AF_UNIX) as second:
            first.bind(str(Path(socket_dir) / f"{os.getpid()}.sock"))
            second.bind(str(Path(socket_dir) / f"{os.getpid() + 1}.sock"))
            # No PID argument discovers this pytest parent via the ancestor walk.
            installed = install(env)
            assert installed.returncode == 0, installed.stderr
            root = Path(env.get("CONDUCTOR_INBOX_DIR", home / ".local/state/conductor-inbox"))
            config = Path(env.get("EVENT_WATCH_CONF", home / ".config/event-watch"))
            before = [p.read_bytes() for p in (settings_path, root / "conductor.addr", config / "conductor-inbox.conf")]
            installed = install(env, str(os.getpid()))
            assert installed.returncode == 0, installed.stderr
            assert before == [p.read_bytes() for p in (settings_path, root / "conductor.addr", config / "conductor-inbox.conf")]
            settings = json.loads(settings_path.read_text())
            assert settings["otherSetting"] is True
            assert settings["hooks"]["PreToolUse"][0] == unrelated
            assert len(settings["hooks"]["PreToolUse"]) == 2
            for name, source in (("tell-conductor", "tell-conductor"), ("tell-general", "tell-conductor")):
                assert (home / ".local/bin" / name).resolve() == SCRIPTS / source
            # The installed hook retains config even in shells without overrides.
            hook = settings["hooks"]["PreToolUse"][1]["hooks"][0]["command"]
            stripped = {k: v for k, v in env.items() if not k.startswith("CONDUCTOR_")}
            checked = subprocess.run(shlex.split(hook), env=stripped, input=json.dumps({
                "tool_name": "SendMessage", "tool_input": {"to": env.get("CONDUCTOR_NAME", "conductor")}}),
                text=True, capture_output=True, timeout=10, check=True)
            assert json.loads(checked.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
            run("tell-conductor", "fyi", "Synthetic status", env=env)
            assert not list((root / "wake").iterdir())
            run("tell-conductor", "decision", "Synthetic choice", env=env)
            watcher_env = dict(env, EVENT_WATCH_CONF=str(config), EVENT_WATCH_STATE=env.get(
                "EVENT_WATCH_STATE", str(home / ".local/state/event-watch")))
            watched = subprocess.run([sys.executable, str(REPO / "tools/event-watch"), "wait", "conductor-inbox", "--max-hours", "0"],
                                     env=watcher_env, capture_output=True, text=True, timeout=10, check=True)
            assert json.loads(watched.stdout)["kind"] == "new"
            inbox_before = (root / "inbox.jsonl").read_bytes()
            restarted = install(env, str(os.getpid() + 1))
            assert restarted.returncode == 0, restarted.stderr
            assert (root / "conductor.addr").read_text().strip() == f"uds:{Path(socket_dir).resolve()}/{os.getpid() + 1}.sock"
            assert (root / "inbox.jsonl").read_bytes() == inbox_before
            assert len(json.loads(settings_path.read_text())["hooks"]["PreToolUse"]) == 2


def test_installer_refuses_a_missing_socket_before_installing(inbox_env):
    inbox_env["CONDUCTOR_SOCKET_DIR"] = str(Path(inbox_env["HOME"]) / "no sockets")
    result = install(inbox_env, str(os.getpid()))
    assert result.returncode != 0 and "no conductor socket" in result.stderr
    home = Path(inbox_env["HOME"])
    assert not (home / ".claude").exists()
    assert not (home / ".local/bin").exists()
    assert not (home / ".config/event-watch").exists()
    assert not Path(inbox_env["CONDUCTOR_INBOX_DIR"]).exists()


# Placeholder vocabulary only; real quarantine lists never enter this repository.
TERM = "projectcodename"


def rows_of(env):
    root = Path(env["CONDUCTOR_INBOX_DIR"])
    return [json.loads(line) for line in (root / "inbox.jsonl").read_text().splitlines()]


def test_cli_quarantines_matching_detail_and_never_names_the_terms(inbox_env, tmp_path):
    terms = tmp_path / "terms.txt"
    terms.write_text("# synthetic\n" + TERM + "\n")
    inbox_env["CONDUCTOR_QUARANTINE_TERMS"] = str(terms)
    detail = f"results for {TERM.upper()} are in run-104"
    out = run("tell-conductor", "--summary", "run finished; needs a choice", "break", detail,
              env=inbox_env).stdout
    row = rows_of(inbox_env)[-1]
    assert TERM not in json.dumps(row).lower() and TERM not in out.lower()
    assert row["quarantine_match_count"] == 1 and row["kind"] == "break"
    assert row["text"].startswith("run finished; needs a choice")
    held = Path(row["quarantined"])
    assert held.read_text() == detail and (held.stat().st_mode & 0o777) == 0o600
    wake = list((Path(inbox_env["CONDUCTOR_INBOX_DIR"]) / "wake").iterdir())
    assert len(wake) == 1 and TERM not in wake[0].read_text().lower()   # the kind still wakes

    # a summary that matches is withheld too; a clean message passes through untouched
    run("tell-conductor", "--summary", "about " + TERM, "fyi", TERM + " detail", env=inbox_env)
    assert TERM not in json.dumps(rows_of(inbox_env)[-1]) and "withheld too" in rows_of(inbox_env)[-1]["text"]
    run("tell-conductor", "fyi", "a plain status line", env=inbox_env)
    assert rows_of(inbox_env)[-1]["text"] == "a plain status line"
    assert "quarantined" not in rows_of(inbox_env)[-1]


def test_cli_with_an_unreadable_terms_file_quarantines_everything(inbox_env, tmp_path):
    inbox_env["CONDUCTOR_QUARANTINE_TERMS"] = str(tmp_path / "missing.txt")
    result = run("tell-conductor", "fyi", "anything at all", env=inbox_env)
    assert "cannot be read" in result.stderr
    row = rows_of(inbox_env)[-1]
    assert "anything at all" not in row["text"] and Path(row["quarantined"]).exists()


def test_cli_forwards_to_the_conductor_host_and_never_files_locally(inbox_env, tmp_path):
    log = tmp_path / "ssh.log"
    ssh = tmp_path / "fake-ssh"
    # Stands in for ssh: skips -o options, records host and command, runs the command here.
    ssh.write_text("#!/bin/sh\nwhile [ \"$1\" = \"-o\" ]; do shift 2; done\n"
                   f"printf 'host=%s\\n' \"$1\" >> {shlex.quote(str(log))}\nshift\nexec sh -c \"$*\"\n")
    ssh.chmod(0o755)
    remote_root = tmp_path / "remote inbox"
    inbox_env.update(CONDUCTOR_HOST="control-box", CONDUCTOR_SSH=str(ssh),
                     CONDUCTOR_REMOTE_COMMAND=(f"CONDUCTOR_INBOX_DIR={shlex.quote(str(remote_root))} "
                                               f"{shlex.quote(sys.executable)} "
                                               f"{shlex.quote(str(SCRIPTS / 'tell-conductor'))}"))
    out = run("tell-conductor", "--summary", "one line", "decision", "it's ready; see notes",
              env=inbox_env).stdout
    assert "(via control-box)" in out and "host=control-box" in log.read_text()
    assert not Path(inbox_env["CONDUCTOR_INBOX_DIR"]).exists()
    row = json.loads((remote_root / "inbox.jsonl").read_text())
    assert row["text"] == "it's ready; see notes" and row["from"] == "worker" and row["kind"] == "decision"

    inbox_env["CONDUCTOR_HOST"] = "-oProxyCommand=x"
    with pytest.raises(subprocess.CalledProcessError):
        run("tell-conductor", "fyi", "x", env=inbox_env)
