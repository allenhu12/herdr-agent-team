#!/usr/bin/env python3
"""Have a role's current session read its context_roots, and record the proof.

Usage: context-read.py send --team-dir <abs> --role <name> [--timeout <seconds>]

Run it after the role's verified live identity is saved in team-state.yaml
and the role is idle. It sends the bounded read prompt, waits for a settled
role and the exact reply line, then writes roles.<name>.context_read:
{at, session, roots, reply}. dispatch-precheck.py refuses a dispatch to a role
with context_roots unless this record belongs to its live session.

The prompt does not hold the expected reply as one word, so a screen that
only echoes the prompt cannot pass. This proves that the read prompt was
answered. It does not prove what the role understood.

Exit: 0 recorded (or the role has no roots), 1 refuse, 2 usage, 3 cannot tell.
The last stdout line is JSON.
"""
import argparse
import os
import re
import secrets
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True

import gate_lib as g  # noqa: E402

SCRIPT = "context-read"
BODY = ("Context read, not a task. Change nothing. For each root below: read its README.md "
        "first if present, or a small top-level index. Then find the sections relevant to your "
        "role. Use rg --files and rg -n to navigate, and read only relevant sections of large "
        "files. If an index exceeds 8 KB, read its headings and the relevant section first. Do "
        "not load a whole repository tree, secret files, credentials, or login transcripts.")


def prompt_text(roots, code):
    listed = "; ".join(str(r) for r in roots)
    return (f"{BODY} Roots: {listed}. When you finish, reply with one line only: the word "
            f"CONTEXT-OK, then a hyphen with no spaces around it, then this code: {code}")


def answered(screen, code):
    """One whole line is the reply. A model may add spaces around the hyphen (seen on a real run)."""
    reply = re.compile(rf"CONTEXT-OK\s*-\s*{code}")
    return any(reply.fullmatch(line.strip().lstrip("•").strip()) for line in screen.splitlines())


def send(args):
    team = g.Team(args.team_dir)
    role = team.role(args.role)
    if role is None:
        return g.emit(SCRIPT, g.REFUSE, [f"no role named {args.role} in team.yaml"])
    roots = role.get("context_roots") or []
    if not roots:
        return g.emit(SCRIPT, g.PASS, [], role=args.role, note="no context_roots")
    missing = [r for r in roots if not os.path.isdir(os.path.expanduser(str(r)))]
    if missing:
        return g.emit(SCRIPT, g.REFUSE, [f"context root missing: {r}" for r in missing])
    info = g.agent_info(args.role)
    state = g.agent_state(info)
    if state not in ("idle", "done"):
        return g.emit(SCRIPT, g.REFUSE, [f"{args.role} is {state}; a read needs an idle role"])
    session = (info.get("agent_session") or {}).get("value")
    rec = team.role_state(args.role)
    if not rec:
        return g.emit(SCRIPT, g.REFUSE, [f"{args.role}: save its verified identity in team-state.yaml first"])
    recorded = (rec.get("process_identity") or {}).get("agent_session_id")
    if not session or not recorded:
        return g.emit(SCRIPT, g.CANNOT_TELL, [f"{args.role}: no session id to tie a read to (live={session!r}, "
                                              f"recorded={recorded!r}); no prompt sent; ask the User"])
    if session != recorded:
        return g.emit(SCRIPT, g.REFUSE, [f"{args.role}: live session {session} differs from recorded "
                                         f"{recorded}; save the verified identity first"])
    code = secrets.token_hex(4)
    expected = f"CONTEXT-OK-{code}"
    rc, data = g.herdr("agent", "prompt", args.role, prompt_text(roots, code))
    if rc != 0 or data.get("error"):
        return g.emit(SCRIPT, g.CANNOT_TELL, [f"prompt not delivered: {data.get('error') or rc}"])
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        now_state = g.agent_state(g.agent_info(args.role))
        if now_state in ("gone", "blocked"):
            return g.emit(SCRIPT, g.REFUSE, [f"{args.role} is {now_state}; no read recorded"])
        if now_state in ("idle", "done"):
            screen = g.herdr("agent", "read", args.role, "--lines", "60", parse=False)
            if answered(screen, code):
                live = (g.agent_info(args.role).get("agent_session") or {}).get("value")
                if live != session:
                    return g.emit(SCRIPT, g.REFUSE, [f"{args.role}: session changed during the read"])
                # Load the state again: a copy from before the prompt would undo later writes.
                latest = g.Team(args.team_dir)
                record = latest.role_state(args.role)
                if not record or (record.get("process_identity") or {}).get("agent_session_id") != session:
                    return g.emit(SCRIPT, g.REFUSE, [f"{args.role}: role record changed during the read"])
                record["context_read"] = {"at": g.now(), "session": session,
                                          "roots": [str(r) for r in roots], "reply": expected}
                latest.save_state()
                return g.emit(SCRIPT, g.PASS, [], role=args.role, session=session)
        time.sleep(args.poll)
    return g.emit(SCRIPT, g.CANNOT_TELL, [f"{args.role}: no {expected} line in {args.timeout} s; no read recorded. "
                                         "Check the pane: a scrolled view hides the reply"])


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("send")
    s.add_argument("--team-dir", required=True)
    s.add_argument("--role", required=True)
    s.add_argument("--timeout", type=float, default=1800)
    s.add_argument("--poll", type=float, default=5)
    args = parser.parse_args(argv)
    return g.run_gate(SCRIPT, lambda: send(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
