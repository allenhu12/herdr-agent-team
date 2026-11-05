#!/usr/bin/env python3
"""Compact a Claude Code Lead's context, then tell it to continue.

Usage: nohup python3 lead-compact.py <lead-pane-id> <lead-name> <team-dir> &

Start it detached, then end the Lead's turn: a slash command cannot run
inside a working turn. It waits for 60 s of idle, sends /compact, waits for
idle again, and sends the continue prompt. Use the pane id as the target.
It logs to <team-dir>/lead-compact.log.
"""
import datetime
import json
import os
import subprocess
import sys
import time


def status(pane):
    run = subprocess.run(["herdr", "agent", "get", pane], capture_output=True, text=True)
    try:
        return json.loads(run.stdout)["result"]["agent"]["agent_status"]
    except (ValueError, KeyError, TypeError):
        return "?"


def wait_idle(pane, seconds, limit):
    end = time.time() + limit
    since = None
    while time.time() < end:
        if status(pane) in ("idle", "done"):
            since = since or time.time()
            if time.time() - since >= seconds:
                return True
        else:
            since = None
        time.sleep(3)
    return False


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    pane, lead, team_dir = sys.argv[1], sys.argv[2], os.path.abspath(sys.argv[3])
    handoff = os.path.join(team_dir, "lead-handoff.md")
    prompt = (f"Context was compacted. Continue as {lead}. Read {handoff}, newest block "
              "first. Do not rerun full Resume unless the session was lost. Check that "
              "the watcher of each running Assignment is still armed; re-arm with no "
              "prompt if not. Then continue the next step.")
    with open(os.path.join(team_dir, "lead-compact.log"), "a", encoding="utf-8") as log:
        log.write(f"--- {datetime.datetime.now().isoformat(timespec='seconds')}\n")
        log.flush()
        if not wait_idle(pane, 60, 1800):
            log.write("no idle window\n")
            return 1
        for word, text in (("compact", "/compact"), ("prompt", prompt)):
            run = subprocess.run(["herdr", "agent", "prompt", pane, text],
                                 capture_output=True, text=True)
            log.write(f"{word} {run.returncode} {run.stderr.strip()}\n")
            log.flush()
            if run.returncode:
                return 1
            if word == "compact":
                time.sleep(5)
                wait_idle(pane, 5, 600)
    return 0


if __name__ == "__main__":
    sys.exit(main())
