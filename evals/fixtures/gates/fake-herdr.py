#!/usr/bin/env python3
"""Fake herdr CLI for offline gate and inbox tests.

State lives in the JSON file named by HAT_FAKE_HERDR_STATE:
  {"agents": {"<name>": {"agent": {...herdr agent record...},
                         "statuses": ["working", "idle"],   # optional, consumed per `agent get`
                         "screen": "footer text"}},
   "log": []}
Every `agent prompt` and `agent send-keys` call is appended to "log".
An "on_prompt" hook per agent can apply a change when a prompt arrives:
  {"move_inbox": "<abs inbox dir>"}  moves every *.msg into handled/
  {"write": {"path": "...", "text": "..."}}  writes a file
"""
import json
import os
import shutil
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
        if entry is not None:
            apply_hook(entry)
        save(path, data)
        return 0 if entry is not None else 1
    if argv[:2] == ["agent", "wait"]:
        time.sleep(0.05)
        return 0
    print(f"fake-herdr: unsupported {argv}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
