#!/usr/bin/env python3
"""Per-role steering inbox: durable messages plus a constant doorbell.

Usage:
  inbox.py send     --team-dir <abs> --role <r> --kind <k> [--assignment <id> --attempt <n>]
                    [--window <tester-id> --window-state open|closed]
                    (--body <text> | --body-file <path>) [--no-ring] [--handshake] [--key <k>]
  inbox.py status   --team-dir <abs> [--role <r>]
  inbox.py ring     --team-dir <abs> --role <r>
  inbox.py wait-ack --team-dir <abs> --role <r> [--deadline-s <s>]
  inbox.py retire   --team-dir <abs> --role <r> --reason <text>
                    (--assignment <id> [--before-attempt <n> | --all] | --window <tester-id> | --all)
  inbox.py doorbell --team-dir <abs> --role <r>

Only roles with `steering: inbox` in team.yaml use this; `send --handshake
--kind note` is the one exception, used by Adjust to test a role before its
steering changes. Layout:
  <team_dir>/inbox/<role>/NNNN.msg   Lead-written, atomic rename
  <team_dir>/inbox/<role>/handled/   the role's move here is the acknowledgement
  <team_dir>/inbox/<role>/retired/   stale records, each with NNNN.reason
  <team_dir>/inbox/<role>/.seq.lock, .ring-state

A message naming an Assignment is valid only while that Assignment is
dispatched at the same attempt; a tester-window `open` message only while
its tester Assignment is dispatched. send refuses an invalid message; ring
retires one. Both re-read team-state.yaml at that moment, so a late send
after a state transition cannot publish a stale instruction.

send --key makes a send idempotent: when a record with that key exists in
the inbox, handled/, or retired/, it is returned (duplicate: true) and no new
message is written. The team monitor uses <assignment>:<attempt>:nudge.

ring: idle/done role with unhandled messages -> ring at once if never rung,
again after HAT_INBOX_GRACE_S (default 60); after HAT_INBOX_RING_MAX rings
(default 3) without acknowledgement exit 4. A working or blocked role is
never rung. wait-ack is the durable delivery owner: run it in the host's
background facility after send; it exits once with outcome inbox_acked (0),
inbox_unacked (4), gone (1), or timeout/unknown (3).

Exit: 0 pass, 1 refuse, 2 usage, 3 cannot tell, 4 unacknowledged.
"""
import argparse
import fcntl
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True

import gate_lib as g  # noqa: E402

SCRIPT = "inbox"
UNACKED = 4
KINDS = ("nudge", "handoff-request", "tester-window", "answer", "note")
SCHEMA = "hat-inbox.v1"


def grace():
    return float(os.environ.get("HAT_INBOX_GRACE_S", "60"))


def ring_max():
    return int(os.environ.get("HAT_INBOX_RING_MAX", "3"))


def poll():
    return float(os.environ.get("HAT_INBOX_POLL_S", "5"))


class Inbox:
    def __init__(self, team, role):
        self.team, self.role = team, role
        self.dir = team.dir / "inbox" / role
        self.handled = self.dir / "handled"
        self.retired = self.dir / "retired"
        self.ring_state = self.dir / ".ring-state"

    def ensure(self):
        for d in (self.dir, self.handled, self.retired):
            d.mkdir(parents=True, exist_ok=True)

    def unhandled(self):
        if not self.dir.is_dir():
            return []
        return sorted(p for p in self.dir.iterdir() if p.is_file() and p.name.endswith(".msg")
                      and not p.name.startswith("."))

    def next_seq(self):
        seen = [0]
        for d in (self.dir, self.handled, self.retired):
            if d.is_dir():
                for p in d.iterdir():
                    stem = p.name.split(".", 1)[0]
                    if p.name.endswith(".msg") and stem.isdigit():
                        seen.append(int(stem))
        return max(seen) + 1

    def find_key(self, key):
        """The record (pending, handled, or retired) that carries this send key."""
        for d in (self.dir, self.handled, self.retired):
            if not d.is_dir():
                continue
            for p in sorted(d.iterdir()):
                if p.name.endswith(".msg") and not p.name.startswith(".") and parse(p).get("key") == key:
                    return p
        return None

    def doorbell(self):
        return (f"INBOX: read every *.msg file in '{self.dir}' in number order, act on each, "
                f"then move it into '{self.handled}/'. If none are left, do nothing.")

    def read_ring_state(self):
        try:
            name, count, last = self.ring_state.read_text().strip().split("\t")
            return name, int(count), float(last)
        except (FileNotFoundError, ValueError):
            return None, 0, 0.0

    def write_ring_state(self, name, count, last):
        g.atomic_write(self.ring_state, f"{name}\t{count}\t{last}\n")

    def clear_ring_state(self):
        if self.ring_state.exists():
            self.ring_state.unlink()

    def retire(self, path, reason):
        self.ensure()
        os.replace(path, self.retired / path.name)
        g.atomic_write(self.retired / (path.name[:-4] + ".reason"), f"{g.now()} {reason}\n")


def parse(path):
    text = Path(path).read_text(encoding="utf-8")
    head, _, body = text.partition("\n--\n")
    meta = {}
    for line in head.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            meta[key] = value
    meta["body"] = body
    return meta


def invalid_reason(team, meta):
    """Why a message is stale against the published team-state, or None."""
    assignment = meta.get("assignment", "-")
    if assignment and assignment != "-":
        item = team.assignment(assignment)
        if item is None or not g.is_dispatched(item):
            return f"Assignment {assignment} is not active"
        if str(item.get("attempt")) != str(meta.get("attempt")):
            return f"Assignment {assignment} is at attempt {item.get('attempt')}, message is for {meta.get('attempt')}"
    if meta.get("kind") == "tester-window":
        window = meta.get("window", "-")
        if not window or window == "-":
            return "tester-window message names no window"
        if meta.get("state") == "open":
            item = team.assignment(window)
            if item is None or not g.is_dispatched(item):
                return f"tester window {window} is already closed"
    return None


def require_inbox_role(team, role):
    spec = team.role(role)
    if spec is None:
        return f"no role named {role} in team.yaml"
    if spec.get("steering", "prompt") != "inbox":
        return f"{role} uses steering: {spec.get('steering', 'prompt')}; send with agent prompt instead"
    return None


def ring_once(team, box):
    """One ring decision. Returns (code, outcome, detail)."""
    for path in box.unhandled():
        reason = invalid_reason(team, parse(path))
        if reason:
            box.retire(path, reason)
    pending = box.unhandled()
    if not pending:
        box.clear_ring_state()
        return g.PASS, "empty", {}
    state = g.agent_state(g.agent_info(box.role))
    if state == "gone":
        return g.REFUSE, "gone", {"pending": len(pending)}
    if state in ("working", "blocked"):
        return g.PASS, "deferred", {"state": state, "pending": len(pending)}
    if state not in ("idle", "done"):
        return g.CANNOT_TELL, "unknown", {"state": state}
    oldest = pending[0].name
    name, count, last = box.read_ring_state()
    if name != oldest:
        count, last = 0, 0.0
    now = time.time()
    if count and now - last < grace():
        return g.PASS, "waiting", {"rings": count, "msg": oldest}
    if count >= ring_max():
        return UNACKED, "inbox_unacked", {"rings": count, "msg": oldest}
    g.herdr("agent", "prompt", box.role, box.doorbell(), parse=False)
    box.write_ring_state(oldest, count + 1, now)
    return g.PASS, "rung", {"rings": count + 1, "msg": oldest}


def cmd_send(args, team):
    refusal = require_inbox_role(team, args.role)
    if args.handshake:
        if args.kind != "note":
            return g.emit(SCRIPT, g.USAGE, ["--handshake sends only --kind note"])
        refusal = None if team.role(args.role) else refusal
    if refusal:
        return g.emit(SCRIPT, g.REFUSE, [refusal])
    if args.kind == "tester-window" and not (args.window and args.window_state):
        return g.emit(SCRIPT, g.USAGE, ["tester-window needs --window and --window-state"])
    if bool(args.assignment) != (args.attempt is not None):
        return g.emit(SCRIPT, g.USAGE, ["--assignment and --attempt go together"])
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else args.body
    meta = {"kind": args.kind, "assignment": args.assignment or "-",
            "attempt": str(args.attempt) if args.attempt is not None else "-",
            "window": args.window or "-", "state": args.window_state or "-"}
    reason = invalid_reason(team, meta)
    if reason:
        return g.emit(SCRIPT, g.REFUSE, [f"stale message not sent: {reason}"], role=args.role)
    box = Inbox(team, args.role)
    box.ensure()
    with open(box.dir / ".seq.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.key:
            existing = box.find_key(args.key)
            if existing is not None:
                return g.emit(SCRIPT, g.PASS, [], role=args.role, msg=existing.name, duplicate=True,
                              where=existing.parent.name if existing.parent != box.dir else "inbox",
                              path=str(existing))
        seq = box.next_seq()
        name = f"{seq:04d}.msg"
        lead = (team.state.get("lead") or {}).get("name") or "lead"
        text = (f"schema={SCHEMA}\nseq={seq:04d}\nat={g.now()}\nfrom={lead}\nrole={args.role}\n"
                f"assignment={meta['assignment']}\nattempt={meta['attempt']}\nkind={args.kind}\n"
                f"window={meta['window']}\nstate={meta['state']}\n"
                + (f"key={args.key}\n" if args.key else "") + f"--\n{body.rstrip()}\n")
        tmp = box.dir / f".{name}.tmp"
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, box.dir / name)
    rung = None
    if not args.no_ring:
        _, rung, _ = ring_once(team, box)
    return g.emit(SCRIPT, g.PASS, [], role=args.role, msg=name, seq=seq, ring=rung,
                  path=str(box.dir / name))


def cmd_status(args, team):
    roles = [args.role] if args.role else [r.get("name") for r in team.team.get("roles") or []
                                           if r.get("steering") == "inbox"]
    out = {}
    now = time.time()
    for role in roles:
        box = Inbox(team, role)
        name, count, _ = box.read_ring_state()
        pending = []
        for path in box.unhandled():
            meta = parse(path)
            pending.append({"msg": path.name, "kind": meta.get("kind"),
                            "assignment": meta.get("assignment"), "attempt": meta.get("attempt"),
                            "age_s": int(now - path.stat().st_mtime),
                            "rings": count if path.name == name else 0})
        monitored = any(m.get("kind") == "inbox" and m.get("assignee") == role
                        for m in team.state.get("monitors") or [])
        out[role] = {"pending": pending, "wait_ack_registered": monitored,
                     "handled": len(list(box.handled.glob("*.msg"))) if box.handled.is_dir() else 0,
                     "retired": len(list(box.retired.glob("*.msg"))) if box.retired.is_dir() else 0}
    return g.emit(SCRIPT, g.PASS, [], roles=out)


def cmd_ring(args, team):
    refusal = require_inbox_role(team, args.role)
    if refusal:
        return g.emit(SCRIPT, g.REFUSE, [refusal])
    code, outcome, detail = ring_once(team, Inbox(team, args.role))
    return g.emit(SCRIPT, code, [] if code == g.PASS else [outcome], role=args.role,
                  outcome=outcome, **detail)


def cmd_wait_ack(args, team_dir):
    start = time.time()
    while True:
        team = g.Team(team_dir)
        box = Inbox(team, args.role)
        code, outcome, detail = ring_once(team, box)
        if outcome == "empty":
            return g.emit(SCRIPT, g.PASS, [], role=args.role, outcome="inbox_acked")
        if code == UNACKED:
            return g.emit(SCRIPT, UNACKED, ["inbox_unacked"], role=args.role, outcome="inbox_unacked", **detail)
        if outcome == "gone":
            return g.emit(SCRIPT, g.REFUSE, ["gone"], role=args.role, outcome="gone")
        if code == g.CANNOT_TELL:
            return g.emit(SCRIPT, g.CANNOT_TELL, ["unknown"], role=args.role, outcome="unknown", **detail)
        if time.time() - start >= args.deadline_s:
            return g.emit(SCRIPT, g.CANNOT_TELL, ["timeout"], role=args.role, outcome="timeout", **detail)
        time.sleep(poll())


def cmd_retire(args, team):
    box = Inbox(team, args.role)
    retired = []
    for path in box.unhandled():
        meta = parse(path)
        hit = False
        if args.all and not args.assignment:
            hit = True
        elif args.window:
            hit = meta.get("window") == args.window
        elif args.assignment:
            if meta.get("assignment") == args.assignment:
                hit = args.all or (args.before_attempt is not None and meta.get("attempt", "-").isdigit()
                                   and int(meta["attempt"]) < args.before_attempt)
        if hit:
            box.retire(path, args.reason)
            retired.append(path.name)
    if not box.unhandled():
        box.clear_ring_state()
    return g.emit(SCRIPT, g.PASS, [], role=args.role, retired=retired)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("send", "status", "ring", "wait-ack", "retire", "doorbell"):
        p = sub.add_parser(name)
        p.add_argument("--team-dir", required=True)
        p.add_argument("--role", required=name not in ("status",))
        if name == "send":
            p.add_argument("--kind", required=True, choices=KINDS)
            p.add_argument("--assignment")
            p.add_argument("--attempt", type=int)
            p.add_argument("--window")
            p.add_argument("--window-state", choices=("open", "closed"))
            body = p.add_mutually_exclusive_group(required=True)
            body.add_argument("--body")
            body.add_argument("--body-file")
            p.add_argument("--no-ring", action="store_true")
            p.add_argument("--handshake", action="store_true")
            p.add_argument("--key")
        if name == "wait-ack":
            p.add_argument("--deadline-s", type=float, default=2700)
        if name == "retire":
            p.add_argument("--reason", required=True)
            p.add_argument("--assignment")
            p.add_argument("--before-attempt", type=int)
            p.add_argument("--window")
            p.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "retire" and not (args.all or args.window or
                                         (args.assignment and args.before_attempt is not None)):
        parser.error("retire needs --assignment with --before-attempt or --all, --window, or --all")

    def body():
        if args.command == "wait-ack":
            return cmd_wait_ack(args, args.team_dir)
        team = g.Team(args.team_dir)
        if args.command == "doorbell":
            print(Inbox(team, args.role).doorbell())
            return g.PASS
        return {"send": cmd_send, "status": cmd_status, "ring": cmd_ring,
                "retire": cmd_retire}[args.command](args, team)

    return g.run_gate(SCRIPT, body)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
