#!/usr/bin/env python3
"""Fake herdr CLI for offline gate and inbox tests.

State lives in the JSON file named by HAT_FAKE_HERDR_STATE:
  {"agents": {"<name>": {"agent": {...herdr agent record...},
                         "statuses": ["working", "idle"],   # optional, consumed per `agent get`
                         "screen": "footer text"}},
   "log": []}
Every `agent prompt`, `agent send-keys`, `tab create`, `pane run`, and
`pane send-keys` call is appended to "log". `agent list` advances each
agent's "statuses" by one, like `agent get` does for one agent.
"prompt_result" per agent scripts `agent prompt --wait`: landed (default),
blocked, stalled, rejected, timeout.
With HAT_FAKE_PANE_EXEC=1, `pane run` really starts its command (detached)
and `pane send-keys <pane> ctrl+c` sends it SIGINT; `tab create` hands out
a new pane id each time.
An "on_prompt" hook per agent can apply a change when a prompt arrives:
  {"move_inbox": "<abs inbox dir>"}  moves every *.msg into handled/
  {"write": {"path": "...", "text": "..."}}  writes a file
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


def load():
    path = os.environ["HAT_FAKE_HERDR_STATE"]
    return path, json.loads(Path(path).read_text())


def save(path, data):
    tmp = path + ".tmp"
    Path(tmp).write_text(json.dumps(data))
    os.replace(tmp, path)


def agent_record(data, name, consume=True):
    entry = data["agents"].get(name)
    if entry is None:
        return None
    record = dict(entry["agent"])
    statuses = entry.get("statuses") or []
    if statuses:
        record["agent_status"] = statuses[0]
        if consume and len(statuses) > 1:
            entry["statuses"] = statuses[1:]
    return record


def apply_hook(entry):
    hook = entry.get("on_prompt") or {}
    inbox = hook.get("move_inbox")
    if inbox and os.path.isdir(inbox):
        handled = os.path.join(inbox, "handled")
        os.makedirs(handled, exist_ok=True)
        for name in sorted(os.listdir(inbox)):
            if name.endswith(".msg"):
                shutil.move(os.path.join(inbox, name), os.path.join(handled, name))
    write = hook.get("write")
    if write:
        Path(write["path"]).write_text(write["text"])


def main(argv):
    path, data = load()
    if argv[:2] == ["agent", "get"]:
        record = agent_record(data, argv[2])
        save(path, data)
        if record is None:
            print(json.dumps({"error": {"code": "agent_not_found", "message": "not found"},
                              "id": "cli:agent:get"}))
            return 1
        print(json.dumps({"id": "cli:agent:get", "result": {"agent": record, "type": "agent"}}))
        return 0
    if argv[:2] == ["agent", "list"]:
        agents = []
        for name in list(data["agents"]):
            record = agent_record(data, name)
            record["name"] = name
            agents.append(record)
        save(path, data)
        print(json.dumps({"id": "cli:agent:list", "result": {"agents": agents, "type": "agent_list"}}))
        return 0
    if argv[:2] == ["tab", "create"]:
        data.setdefault("log", []).append(argv)
        n = data["tabs_created"] = data.get("tabs_created", 0) + 1
        save(path, data)
        print(json.dumps({"id": "cli:tab:create", "result": {"tab": {"tab_id": f"w9:t{n}"},
                                                             "pane": {"pane_id": f"w9:p{n}"}}}))
        return 0
    if argv[:2] in (["pane", "run"], ["pane", "send-keys"]):
        data.setdefault("log", []).append(argv)
        if os.environ.get("HAT_FAKE_PANE_EXEC") == "1":
            panes = data.setdefault("panes", {})
            if argv[1] == "run":
                proc = subprocess.Popen(argv[3:], start_new_session=True, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)
                panes[argv[2]] = proc.pid
            elif "ctrl+c" in argv[3:] and argv[2] in panes:
                try:
                    os.kill(panes[argv[2]], signal.SIGINT)
                except ProcessLookupError:
                    pass
        save(path, data)
        return 0
    if argv[:2] == ["agent", "read"]:
        entry = data["agents"].get(argv[2])
        if entry is None:
            print("agent not found", file=sys.stderr)
            return 1
        print(entry.get("screen", ""))
        return 0
    if argv[:2] in (["agent", "prompt"], ["agent", "send-keys"]):
        data.setdefault("log", []).append(argv[1:])
        entry = data["agents"].get(argv[2])
        result = (entry or {}).get("prompt_result", "landed")
        if entry is not None and argv[1] == "prompt" and result in ("rejected", "stalled", "timeout"):
            code = {"rejected": "agent_blocked", "stalled": "agent_prompt_stalled", "timeout": "timeout"}[result]
            save(path, data)
            print(json.dumps({"error": {"code": code, "message": code}, "id": "cli:agent:prompt"}))
            return 1
        if entry is not None:
            apply_hook(entry)
        save(path, data)
        if entry is not None and "--wait" in argv:
            state = "blocked" if result == "blocked" else "working"
            print(json.dumps({"id": "cli:agent:prompt", "result": {"agent": {"agent_status": state}}}))
        return 0 if entry is not None else 1
    if argv[:2] == ["agent", "wait"]:
        time.sleep(0.05)
        return 0
    print(f"fake-herdr: unsupported {argv}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
