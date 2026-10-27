#!/usr/bin/env python3
"""Team monitor: one long-running script per team, a durable wake queue, and a
doorbell for the Lead. Used when team.yaml has `monitor: team`
(monitoring.md "Team monitor"). It needs no host background task and no
agent-specific hook: only Herdr commands.

Usage:
  team-monitor.py run      --team-dir <abs> [--ticks N]
  team-monitor.py start    --team-dir <abs>
  team-monitor.py stop     --team-dir <abs>
  team-monitor.py status   --team-dir <abs>
  team-monitor.py drain    --team-dir <abs>
  team-monitor.py ack      --team-dir <abs> (--through <seq> | --handled <seq,seq,...>)
  team-monitor.py compact  --team-dir <abs> [--keep N]
  team-monitor.py hold     --team-dir <abs> --assignment <id> --attempt <n> --reason <text>
  team-monitor.py unhold   --team-dir <abs> --assignment <id> --attempt <n>
  team-monitor.py dispatch-prompt --team-dir <abs> --role <r> --assignment <id> --attempt <n>
                                  (--text <prompt> | --text-file <path>) [--resend-after-check]

run is the monitor itself. It runs in its own Herdr tab (start creates it).
Each loop it re-reads the team files (read-only), lists Herdr agents once,
and turns what the Lead must act on into <team_dir>/wake-queue/NNNNNN.wake.
It nudges a role once when a dispatched Assignment settled without a
report, rings inbox roles, and rings the Lead's doorbell when wakes wait and
the Lead has been idle for a while. Before every prompt it checks the
target's recorded identity; a mismatch becomes an identity_fault wake and
the target is quarantined until Resume re-verifies it. It never accepts
work, never writes team.yaml, team-state.yaml or assignment.md, and never
kills anything. The only completion signal is still report.md.

Wake files are the source of truth; monitor/seen.json is a cache rebuilt at
startup. drain is a read-only snapshot: the Lead first reconciles the User's
message and pending_user, then handles wakes in order, then acks a
contiguous prefix of handled, deferred, or stale wakes (ack --handled
computes that prefix).

`hold` writes a Lead-owned marker monitor/hold/<id>-<attempt>.json that
silences the monitor for that Assignment during a cancel/redirect
handshake; the Assignment's state, attempt and lease stay unchanged until
the stop proof. hold, unhold, every monitor prompt about an Assignment, and
dispatch-prompt share monitor/.prompt.lock and recheck the Assignment and
the marker under it, so once hold returns no prompt for that Assignment can
start and none is still in flight.

dispatch-prompt sends a dispatch, rework, Resume or Rotate prompt and waits
only for the first lifecycle change (--until working --until blocked). It
first reserves monitor/dispatch/<id>-<attempt>-<n>.json as `sending` with the
handoff baseline, then records landed, landed_blocked, rejected_blocked,
stalled, or uncertain. A `sending` record older than 60s (the sender died)
becomes prompt_uncertain. After sending or uncertain, another dispatch-prompt
for that attempt needs --resend-after-check, given only after `agent read`
showed the prompt did not land.

start serializes on monitor/.start.lock, passes a fresh launch token to run,
and writes monitor/binding.json (token, pane, tab) only when the live
heartbeat carries that token. stop interrupts only the bound pane, and only
while its token matches the live heartbeat.

Exit: 0 pass, 1 refuse, 2 usage or another monitor holds the lock, 3 cannot tell.
Environment: HAT_HERDR_BIN, HAT_MONITOR_LOOP_S (5), HAT_MONITOR_BLOCKED_HOLD_S (20),
HAT_MONITOR_UNKNOWN_HOLD_S (60), HAT_MONITOR_SETTLE_S (30), HAT_LEAD_IDLE_HOLD_S (30),
HAT_LEAD_RING_GRACE_S (120), HAT_MONITOR_CLOCK (a file holding epoch seconds, tests only),
HAT_MONITOR_CRASH_AT (after_temp | after_rename | before_cache, tests only),
HAT_MONITOR_START_WAIT_S (15).
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True

import gate_lib as g  # noqa: E402

SCRIPT = "team-monitor"
ASSETS = Path(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = "hat-wake.v1"
DEFAULT_DEADLINE_S = 2700
SENDING_STALE_S = 60


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ASSETS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inbox = _load("hat_inbox", "inbox.py")


def env_f(name, default):
    return float(os.environ.get(name, default))


def clock():
    path = os.environ.get("HAT_MONITOR_CLOCK")
    if path:
        return float(Path(path).read_text().strip())
    return time.time()


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text):
    if not text:
        return None
    try:
        return datetime.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def crash_point(name):
    if os.environ.get("HAT_MONITOR_CRASH_AT") == name:
        os._exit(9)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    g.atomic_write(path, json.dumps(data, indent=1, sort_keys=True) + "\n")


class Paths:
    def __init__(self, team_dir):
        self.team_dir = Path(os.path.realpath(team_dir))
        self.mon = self.team_dir / "monitor"
        self.queue = self.team_dir / "wake-queue"
        self.done = self.queue / "done"
        self.lock = self.mon / ".lock"
        self.heartbeat = self.mon / "heartbeat.json"
        self.seen = self.mon / "seen.json"
        self.observe = self.mon / "observe.json"
        self.intents = self.mon / "intents.json"
        self.lead_ring = self.mon / "lead-ring.json"
        self.dispatch = self.mon / "dispatch"
        self.hold = self.mon / "hold"
        self.acked = self.queue / "acked"
        self.seq_lock = self.queue / ".seq.lock"
        self.prompt_lock = self.mon / ".prompt.lock"
        self.start_lock = self.mon / ".start.lock"
        self.binding = self.mon / "binding.json"

    def ensure(self):
        for d in (self.mon, self.queue, self.done, self.dispatch, self.hold):
            d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- the queue

def wake_files(paths):
    out = []
    for d in (paths.queue, paths.done):
        if d.is_dir():
            for p in d.iterdir():
                stem = p.name.split(".", 1)[0]
                if p.name.endswith(".wake") and stem.isdigit():
                    out.append((int(stem), p))
    return sorted(out)


def read_wake(path):
    return read_json(path, None)


def rebuild_seen(paths):
    keys, high = set(), 0
    for seq, path in wake_files(paths):
        rec = read_wake(path)
        if rec and rec.get("key"):
            keys.add(rec["key"])
        high = max(high, seq)
    write_json(paths.seen, {"high": high, "keys": sorted(keys)})
    return keys, high


def acked(paths):
    try:
        return int(paths.acked.read_text().strip() or 0)
    except (FileNotFoundError, ValueError):
        return 0


def enqueue(paths, key, record):
    """Publish one wake unless its key is already queued. Returns the seq or None."""
    paths.ensure()
    with open(paths.seq_lock, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cache = read_json(paths.seen, {"high": 0, "keys": []})
        keys, high = set(cache.get("keys") or []), int(cache.get("high") or 0)
        files = wake_files(paths)
        for seq, path in files:
            if seq > high:
                rec = read_wake(path)
                if rec and rec.get("key"):
                    keys.add(rec["key"])
        if key in keys:
            return None
        seq = (files[-1][0] if files else 0) + 1
        rec = {"schema": SCHEMA, "seq": seq, "at": iso(clock()), "key": key}
        rec.update(record)
        name = f"{seq:06d}.wake"
        tmp = paths.queue / f".{name}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(rec, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        crash_point("after_temp")
        os.replace(tmp, paths.queue / name)
        crash_point("after_rename")
        keys.add(key)
        crash_point("before_cache")
        write_json(paths.seen, {"high": seq, "keys": sorted(keys)})
        return seq


def ack_prefix(start, pending_seqs, handled):
    """Largest N such that every pending seq in (start, N] is in handled."""
    through = start
    for seq in sorted(pending_seqs):
        if seq <= start:
            continue
        if seq not in handled:
            break
        through = seq
    return through


# ---------------------------------------------------------------- observations

def report_ready(path, attempt):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return False
    return re.search(rf"(?m)^(\*\*)?Attempt:(\*\*)? *{attempt}([^0-9]|$)", text) is not None


def handoff_identity(ws, attempt):
    """(sha8 of a current-attempt handoff.md or '', HANDOFF READY marker count)."""
    sha = ""
    handoff = Path(ws) / "handoff.md"
    if handoff.is_file():
        text = handoff.read_text(encoding="utf-8", errors="replace")
        if re.search(rf"(?m)^\*\*Attempt:\*\* *{attempt}([^0-9]|$)", text):
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    count = 0
    log = Path(ws) / "log.md"
    if log.is_file():
        count = log.read_text(encoding="utf-8", errors="replace").count(f"HANDOFF READY attempt={attempt}")
    return sha, count


def dispatch_records(paths, aid, attempt):
    recs = []
    if paths.dispatch.is_dir():
        for p in paths.dispatch.glob(f"{aid}-{attempt}-*.json"):
            rec = read_json(p, None)
            if rec:
                recs.append(rec)
    return sorted(recs, key=lambda r: int(r.get("n") or 0))


def agents_by_name():
    code, data = g.herdr("agent", "list")
    if code != 0 or data.get("error"):
        raise g.CannotTell(f"herdr agent list failed: {data.get('error') or code}")
    agents = ((data.get("result") or {}).get("agents")) or []
    return {a.get("name"): a for a in agents if a.get("name")}


def session_of(info):
    return ((info or {}).get("agent_session") or {}).get("value")


class Flock:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a")
        fcntl.flock(self.handle, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()


def fingerprint(rec):
    """The recorded identity plus its verification time (a role's
    launch_verification.verified_at, the Lead's identity_verified_at), so a
    Resume that re-verifies even the same process changes it."""
    rec = rec or {}
    verified = rec.get("identity_verified_at") or (rec.get("launch_verification") or {}).get("verified_at")
    return json.dumps([rec.get("pane_id"), rec.get("kind"), rec.get("cwd"),
                       (rec.get("process_identity") or {}).get("agent_session_id"), verified])


def hold_path(paths, aid, attempt):
    return paths.hold / f"{aid}-{attempt}.json"


def current_item(paths, aid, attempt, role):
    """Under the prompt lock: the Assignment if it may still be prompted, else None."""
    try:
        team = g.Team(paths.team_dir)
    except g.CannotTell:
        return None, None
    item = team.assignment(aid)
    if item is None or not g.is_dispatched(item) or str(item.get("attempt")) != str(attempt) \
            or item.get("assignee") != role or hold_path(paths, aid, attempt).exists():
        return team, None
    return team, item


def role_held(paths, team, role):
    return any(item.get("assignee") == role and g.is_dispatched(item)
               and hold_path(paths, item.get("id"), item.get("attempt")).exists()
               for item in team.assignments())


class Monitor:
    def __init__(self, team_dir):
        self.paths = Paths(team_dir)
        self.paths.ensure()
        self.obs = read_json(self.paths.observe, {})
        for key in ("since", "episode", "prev", "seen_working", "nudged", "quarantine"):
            self.obs.setdefault(key, {})
        self.errors = []
        self.now = clock()
        self.launch_token = None

    def save(self):
        write_json(self.paths.observe, self.obs)

    def wake(self, key, **record):
        return enqueue(self.paths, key, record)

    # ------------------------------------------------ identity and prompts

    def verified(self, name, rec, info):
        """True when it is safe to prompt this target; otherwise queue one fault.

        A quarantined target is released only when its recorded identity
        changed (Resume re-verified and updated team-state) and the live
        agent matches the new record.
        """
        mismatch, missing = g.identity_mismatch(name, rec, info)
        quarantined = self.obs["quarantine"].get(name)
        if quarantined is not None:
            if fingerprint(rec) != quarantined.get("record") and not mismatch and not missing:
                self.obs["quarantine"].pop(name, None)
                return True
            return False
        if not mismatch and not missing:
            return True
        session = session_of(info) or "none"
        self.obs["quarantine"][name] = {"session": session, "reasons": mismatch + missing,
                                        "record": fingerprint(rec)}
        self.wake(f"identity:{name}:{session}", kind="identity", outcome="identity_fault",
                  assignee=name, detail={"reasons": mismatch + missing})
        return False

    def prompt(self, name, text, intent_key, typed_work):
        """Type text into a verified target, with an intent record for crash recovery."""
        intents = read_json(self.paths.intents, {})
        intents[intent_key] = {"state": "sending", "at": iso(self.now), "target": name,
                               "typed_work": typed_work}
        write_json(self.paths.intents, intents)
        try:
            g.herdr("agent", "prompt", name, text, parse=False)
            result = "sent"
        except g.CannotTell as exc:
            result = "failed"
            self.errors.append(str(exc))
        intents = read_json(self.paths.intents, {})
        intents[intent_key] = {"state": result, "at": iso(self.now), "target": name,
                               "typed_work": typed_work}
        write_json(self.paths.intents, intents)
        return result == "sent"

    def recover_intents(self):
        """A typed work prompt left in `sending` is never resent (CR-6)."""
        intents = read_json(self.paths.intents, {})
        changed = False
        for key, rec in intents.items():
            if rec.get("state") == "sending":
                if rec.get("typed_work"):
                    self.wake(f"{key}:uncertain", kind="assignment", outcome="nudge_uncertain",
                              assignee=rec.get("target"), detail={"intent": key})
                rec["state"] = "uncertain"
                changed = True
        if changed:
            write_json(self.paths.intents, intents)

    # ------------------------------------------------ one loop

    def held(self, aid, attempt):
        return hold_path(self.paths, aid, attempt).exists()

    def track(self, role, state, prefix):
        """Hold timers and episode counters for blocked/unknown (CR-3 restart-safe)."""
        prev = self.obs["prev"].get(role)
        if state != prev:
            self.obs["since"][role] = self.now
            if state in ("blocked", "unknown"):
                ep = f"{prefix}:{state}"
                self.obs["episode"][ep] = int(self.obs["episode"].get(ep, 0)) + 1
        self.obs["prev"][role] = state
        return self.now - float(self.obs["since"].get(role, self.now))

    def assignment(self, team, item, agents):
        aid, attempt, role = item.get("id"), item.get("attempt"), item.get("assignee")
        prefix = f"{aid}:{attempt}"
        base = {"kind": "assignment", "assignment": aid, "attempt": attempt, "assignee": role}
        if self.held(aid, attempt):
            return
        ws = team.workspace(aid)
        report_path = item.get("report_path") or str(ws / "report.md")
        if report_ready(report_path, attempt):
            self.wake(f"{prefix}:report", outcome="report", state=None, **base)
            return
        records = dispatch_records(self.paths, aid, attempt)
        latest = records[-1] if records else None
        sha, count = handoff_identity(ws, attempt)
        if sha or count:
            baseline = (latest.get("handoff_sha8", ""), int(latest.get("handoff_count", 0))) if latest else ("", 0)
            if (sha, count) != baseline:
                self.wake(f"{prefix}:handoff:{sha or '-'}:{count}", outcome="handoff", **base,
                          detail={"handoff_sha8": sha, "markers": count})
        if latest and latest.get("result") in ("stalled", "uncertain", "rejected_blocked"):
            outcome = {"stalled": "stalled", "uncertain": "prompt_uncertain",
                       "rejected_blocked": "blocked"}[latest["result"]]
            self.wake(f"{prefix}:{outcome}:{latest.get('n')}", outcome=outcome, **base,
                      detail={"dispatch": latest.get("n")})
        if latest and latest.get("result") == "sending" and \
                self.now - (parse_iso(latest.get("at")) or self.now) >= SENDING_STALE_S:
            self.wake(f"{prefix}:prompt_uncertain:{latest.get('n')}", outcome="prompt_uncertain", **base,
                      detail={"dispatch": latest.get("n"), "reason": "sender never recorded a result"})
        info = agents.get(role)
        if info is None:
            self.wake(f"{prefix}:gone", outcome="gone", state="gone", **base)
            return
        state = info.get("agent_status") or "unknown"
        held_for = self.track(role, state, prefix)
        landed = latest if latest and latest.get("result") in ("landed", "landed_blocked") else None
        landed_at = parse_iso(landed.get("at")) if landed else None
        turn = f"{prefix}:{landed.get('n')}" if landed else None
        if state == "working" and landed_at is not None and self.now >= landed_at:
            self.obs["seen_working"][turn] = True
        if state == "blocked" and held_for >= env_f("HAT_MONITOR_BLOCKED_HOLD_S", 20):
            ep = self.obs["episode"].get(f"{prefix}:blocked", 1)
            self.wake(f"{prefix}:blocked#{ep}", outcome="blocked", state=state, **base)
        if state == "unknown" and held_for >= env_f("HAT_MONITOR_UNKNOWN_HOLD_S", 60):
            ep = self.obs["episode"].get(f"{prefix}:unknown", 1)
            self.wake(f"{prefix}:unknown#{ep}", outcome="unknown", state=state, **base)
        started = parse_iso(item.get("dispatched_at"))
        deadline = float(item.get("deadline_s") or DEFAULT_DEADLINE_S)
        if started is not None and self.now - started >= deadline:
            self.wake(f"{prefix}:timeout", outcome="timeout", state=state, **base)
        if state not in ("idle", "done"):
            return
        # Only a turn that a landed dispatch prompt started counts (dispatch race).
        if landed_at is None:
            return
        settle = env_f("HAT_MONITOR_SETTLE_S", 30)
        if not (self.obs["seen_working"].get(turn) or self.now - landed_at >= settle):
            return
        self.nudge(team, item, info, prefix, base, state)

    def nudge(self, team, item, info, prefix, base, state):
        role, aid, attempt = item.get("assignee"), item.get("id"), item.get("attempt")
        spec = team.role(role) or {}
        ws = team.workspace(aid)
        nudged = self.obs["nudged"].get(prefix)
        text = (f"Write '{ws}/report.md' for attempt {attempt} now, following the six-section "
                "template, then stop.")
        if nudged is None:
            intent = read_json(self.paths.intents, {}).get(f"{prefix}:nudge")
            if intent and intent.get("state") == "sent":
                nudged = {"mode": "prompt", "at": parse_iso(intent.get("at")) or self.now}
                self.obs["nudged"][prefix] = nudged
            elif intent and intent.get("state") in ("sending", "uncertain"):
                return  # delivery unknown; the Lead has nudge_uncertain
        if nudged is None:
            if not self.verified(role, team.role_state(role), info):
                return
            with Flock(self.paths.prompt_lock):
                _, fresh = current_item(self.paths, aid, attempt, role)
                if fresh is None:
                    return  # held, settled, or moved on since this tick read the state
                self.send_nudge(team, spec, role, aid, attempt, prefix, text)
            return
        self.after_nudge(team, nudged, role, prefix, base, state)

    def send_nudge(self, team, spec, role, aid, attempt, prefix, text):
        """Called under the prompt lock after the Assignment was rechecked."""
        if spec.get("steering") != "inbox":
            if self.prompt(role, text, f"{prefix}:nudge", typed_work=True):
                self.obs["nudged"][prefix] = {"mode": "prompt", "at": self.now}
            self.save()
            return
        # The key makes a retry after a crash return the existing message.
        proc = subprocess.run([sys.executable, str(ASSETS / "inbox.py"), "send", "--team-dir",
                               str(team.dir), "--role", role, "--kind", "nudge", "--assignment",
                               str(aid), "--attempt", str(attempt), "--key", f"{prefix}:nudge",
                               "--body", text, "--no-ring"], capture_output=True, text=True)
        try:
            out = json.loads(proc.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            out = {}
        if proc.returncode == 1:
            return  # the attempt is no longer current; the Lead moved on
        if not out.get("msg"):
            self.errors.append(f"inbox nudge for {prefix} failed: {proc.stderr.strip()}")
            return
        self.obs["nudged"][prefix] = {"mode": "inbox", "msg": out["msg"], "at": self.now}
        self.save()

    def after_nudge(self, team, nudged, role, prefix, base, state):
        if nudged.get("mode") == "inbox":
            box = team.dir / "inbox" / role
            if (box / "handled" / nudged["msg"]).exists():
                self.wake(f"{prefix}:no_report", outcome="no_report", state=state, **base)
        elif self.now - float(nudged.get("at", self.now)) >= env_f("HAT_MONITOR_SETTLE_S", 30):
            self.wake(f"{prefix}:no_report", outcome="no_report", state=state, **base)

    def inbox_roles(self, team, agents, busy_roles):
        for spec in team.team.get("roles") or []:
            role = spec.get("name")
            if spec.get("steering") != "inbox" or role in busy_roles:
                continue
            box = inbox.Inbox(team, role)
            if not box.unhandled():
                continue
            info = agents.get(role)
            if info is None or not self.verified(role, team.role_state(role), info):
                continue
            with Flock(self.paths.prompt_lock):
                try:
                    fresh = g.Team(self.paths.team_dir)
                except g.CannotTell:
                    continue
                if role_held(self.paths, fresh, role):
                    continue
                code, outcome, detail = inbox.ring_once(fresh, inbox.Inbox(fresh, role))
            if code == inbox.UNACKED:
                self.wake(f"inbox:{role}:{detail.get('msg')}:unacked", kind="inbox",
                          outcome="inbox_unacked", assignee=role, detail=detail)

    def idle_roles(self, team, agents, active_roles):
        for spec in team.team.get("roles") or []:
            role = spec.get("name")
            if role in active_roles or role in agents:
                continue
            rec = team.role_state(role) or {}
            session = (rec.get("process_identity") or {}).get("agent_session_id") or "none"
            self.wake(f"role:{role}:gone:{session}", kind="role", outcome="role_gone", assignee=role)

    def lead_doorbell(self, team, agents):
        pending = [s for s, _ in wake_files(self.paths) if s > acked(self.paths)]
        lead = team.state.get("lead") or {}
        info = agents.get(lead.get("name"))
        ring = read_json(self.paths.lead_ring, {"last_ring_at": 0, "rings": 0, "for_seq": 0, "acked": 0})
        if ring.get("acked") != acked(self.paths):
            ring.update({"rings": 0, "acked": acked(self.paths)})
        if not pending or info is None:
            write_json(self.paths.lead_ring, ring)
            return
        if not self.verified(lead.get("name"), lead, info):
            return
        state = info.get("agent_status")
        if state != self.obs["prev"].get("__lead__"):
            self.obs["since"]["__lead__"] = self.now
        self.obs["prev"]["__lead__"] = state
        if state not in ("idle", "done"):
            return
        if self.now - float(self.obs["since"].get("__lead__", self.now)) < env_f("HAT_LEAD_IDLE_HOLD_S", 30):
            return
        grace = env_f("HAT_LEAD_RING_GRACE_S", 120)
        rings = int(ring.get("rings", 0))
        if rings >= 3:
            grace = min(grace * (2 ** (rings - 2)), 1800)
        newer = max(pending) > int(ring.get("for_seq", 0))
        if not newer and self.now - float(ring.get("last_ring_at", 0)) < grace:
            return
        text = (f"WAKE: run python3 {ASSETS / 'team-monitor.py'} drain --team-dir {team.dir}")
        if self.prompt(lead["name"], text, "lead:doorbell", typed_work=False):
            ring.update({"last_ring_at": self.now, "rings": rings + 1, "for_seq": max(pending)})
        write_json(self.paths.lead_ring, ring)

    def tick(self):
        self.now = clock()
        self.errors = []
        try:
            team = g.Team(self.paths.team_dir)
        except g.CannotTell as exc:
            digest = hashlib.sha256(str(exc).encode()).hexdigest()[:8]
            self.wake(f"monitor_error:{digest}", kind="monitor", outcome="monitor_error",
                      detail={"error": str(exc)})
            self.heartbeat(error=str(exc))
            return
        try:
            agents = agents_by_name()
        except g.CannotTell as exc:
            self.heartbeat(error=str(exc))
            return
        active = [a for a in team.assignments() if g.is_dispatched(a)]
        for item in active:
            self.assignment(team, item, agents)
        busy = set()  # inbox rings for held Assignments' roles stay silent
        for item in active:
            if self.held(item.get("id"), item.get("attempt")):
                busy.add(item.get("assignee"))
        self.inbox_roles(team, agents, busy)
        self.idle_roles(team, agents, {a.get("assignee") for a in active})
        self.lead_doorbell(team, agents)
        self.save()
        self.heartbeat(error="; ".join(self.errors) or None)

    def heartbeat(self, error=None, stopped=False):
        beat = read_json(self.paths.heartbeat, {})
        beat.update({"pid": os.getpid(), "launch_token": self.launch_token, "beat_at": iso(clock()), "beat_epoch": clock(),
                     "loop_s": env_f("HAT_MONITOR_LOOP_S", 5),
                     "quarantined": sorted(self.obs.get("quarantine", {})),
                     "last_error": error, "stopped": stopped})
        beat.setdefault("started_at", iso(clock()))
        write_json(self.paths.heartbeat, beat)


# ---------------------------------------------------------------- commands

def cmd_run(args):
    paths = Paths(args.team_dir)
    paths.ensure()
    lock = open(paths.lock, "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return g.emit(SCRIPT, g.USAGE, ["another team monitor holds the lock"])
    write_json(paths.heartbeat, {"started_at": iso(clock()), "pid": os.getpid(),
                                 "launch_token": args.launch_token})
    rebuild_seen(paths)
    mon = Monitor(args.team_dir)
    mon.launch_token = args.launch_token
    mon.recover_intents()
    ticks = 0
    try:
        while True:
            try:
                mon.tick()
            except Exception as exc:  # noqa: BLE001 - the monitor keeps running
                mon.heartbeat(error=f"{type(exc).__name__}: {exc}")
            ticks += 1
            if args.ticks and ticks >= args.ticks:
                break
            time.sleep(env_f("HAT_MONITOR_LOOP_S", 5))
    except KeyboardInterrupt:
        mon.heartbeat(stopped=True)
        return g.emit(SCRIPT, g.PASS, ["stopped"], ticks=ticks)
    return g.emit(SCRIPT, g.PASS, [], ticks=ticks)


def lock_free(paths):
    if not paths.lock.exists():
        return True
    with open(paths.lock, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(lock, fcntl.LOCK_UN)
        return True


def health(paths):
    beat = read_json(paths.heartbeat, {})
    loop_s = float(beat.get("loop_s") or env_f("HAT_MONITOR_LOOP_S", 5))
    age = clock() - float(beat.get("beat_epoch") or 0)
    running = not lock_free(paths)
    healthy = running and not beat.get("stopped") and age < 3 * max(loop_s, 1)
    return healthy, {"running": running, "beat_age_s": round(age, 1), "heartbeat": beat}


def cmd_status(args):
    paths = Paths(args.team_dir)
    healthy, detail = health(paths)
    files = wake_files(paths)
    done = acked(paths)
    pending = [s for s, _ in files if s > done]
    binding, ok = bound(paths)
    return g.emit(SCRIPT, g.PASS if healthy else g.REFUSE, [] if healthy else ["monitor not healthy"],
                  healthy=healthy, acked=done, pending=len(pending), high=files[-1][0] if files else 0,
                  binding=binding, bound=ok, **detail)


def cmd_drain(args):
    paths = Paths(args.team_dir)
    done = acked(paths)
    wakes = [read_wake(p) for s, p in wake_files(paths) if s > done]
    wakes = [w for w in wakes if w]
    high = wakes[-1]["seq"] if wakes else done
    healthy, _ = health(paths)
    print(f"WAKE_ACK_REQUIRED={high}")
    return g.emit(SCRIPT, g.PASS, [], acked=done, wakes=wakes, wake_ack_required=high,
                  monitor_healthy=healthy)


def cmd_ack(args):
    paths = Paths(args.team_dir)
    paths.ensure()
    with open(paths.seq_lock, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        done = acked(paths)
        seqs = [s for s, _ in wake_files(paths)]
        high = seqs[-1] if seqs else 0
        if args.handled is not None:
            handled = {int(x) for x in args.handled.split(",") if x.strip()}
            through = ack_prefix(done, seqs, handled)
        else:
            through = args.through
        if through > high:
            return g.emit(SCRIPT, g.REFUSE, [f"seq {through} does not exist (high {high})"])
        if through <= done:
            return g.emit(SCRIPT, g.PASS, ["already acknowledged"], acked=done)
        g.atomic_write(paths.acked, f"{through}\n")
    return g.emit(SCRIPT, g.PASS, [], acked=through, previous=done)


def cmd_compact(args):
    paths = Paths(args.team_dir)
    team = g.Team(paths.team_dir)
    done = acked(paths)
    moved = 0
    old = [(s, p) for s, p in wake_files(paths) if s <= done and p.parent == paths.queue]
    for seq, path in old[:max(0, len(old) - args.keep)]:
        os.replace(path, paths.done / path.name)
        moved += 1
    removed = []
    for marker in paths.hold.glob("*.json") if paths.hold.is_dir() else []:
        aid, _, attempt = marker.stem.rpartition("-")
        item = team.assignment(aid)
        if item is None or not g.is_dispatched(item) or str(item.get("attempt")) != attempt:
            marker.unlink()
            removed.append(marker.name)
    return g.emit(SCRIPT, g.PASS, [], moved=moved, holds_removed=removed)


def find_key(data, key):
    if isinstance(data, dict):
        if data.get(key):
            return data[key]
        for value in data.values():
            found = find_key(value, key)
            if found:
                return found
    elif isinstance(data, list):
        for value in data:
            found = find_key(value, key)
            if found:
                return found
    return None


def bound(paths):
    """The recorded monitor pane, only when it belongs to the live monitor."""
    binding = read_json(paths.binding, {})
    beat = read_json(paths.heartbeat, {})
    ok = bool(binding.get("launch_token")) and binding.get("launch_token") == beat.get("launch_token")
    return binding, ok


def cmd_start(args):
    paths = Paths(args.team_dir)
    paths.ensure()
    with Flock(paths.start_lock):
        healthy, detail = health(paths)
        binding, ok = bound(paths)
        if healthy:
            return g.emit(SCRIPT, g.PASS, ["already running"], pane_id=binding.get("pane_id") if ok else None,
                          tab_id=binding.get("tab_id") if ok else None, bound=ok,
                          pid=detail["heartbeat"].get("pid"))
        if detail["running"]:
            return g.emit(SCRIPT, g.CANNOT_TELL, ["a monitor holds the lock but its heartbeat is stale; "
                                                  "stop it before starting another"])
        team = g.Team(paths.team_dir)
        token = hashlib.sha256(f"{os.getpid()}:{time.time()}:{os.urandom(8).hex()}".encode()).hexdigest()[:16]
        label = f"{team.team.get('team_id') or 'team'}-monitor"
        code, created = g.herdr("tab", "create", "--label", label, "--cwd", str(paths.team_dir), "--no-focus")
        if code != 0 or created.get("error"):
            raise g.CannotTell(f"herdr tab create failed: {created.get('error') or code}")
        tab_id = find_key(created, "tab_id")
        pane_id = find_key(created, "pane_id")
        if not pane_id and tab_id:
            code, panes = g.herdr("pane", "list")
            for pane in find_key(panes, "panes") or []:
                if pane.get("tab_id") == tab_id:
                    pane_id = pane.get("pane_id")
                    break
        if not pane_id:
            raise g.CannotTell(f"no pane found in the new monitor tab {tab_id}")
        g.herdr("pane", "run", pane_id, sys.executable, str(ASSETS / "team-monitor.py"), "run",
                "--team-dir", str(paths.team_dir), "--launch-token", token, parse=False)
        deadline = time.time() + env_f("HAT_MONITOR_START_WAIT_S", 15)
        while time.time() < deadline:
            healthy, detail = health(paths)
            beat = detail["heartbeat"]
            if healthy and beat.get("launch_token") == token:
                write_json(paths.binding, {"launch_token": token, "pane_id": pane_id, "tab_id": tab_id,
                                           "pid": beat.get("pid"), "bound_at": iso(clock())})
                return g.emit(SCRIPT, g.PASS, [], pane_id=pane_id, tab_id=tab_id, pid=beat.get("pid"))
            if healthy:
                return g.emit(SCRIPT, g.CANNOT_TELL, ["another monitor is running; the new tab is a close target"],
                              extra_tab_id=tab_id, extra_pane_id=pane_id)
            time.sleep(0.2)
        return g.emit(SCRIPT, g.CANNOT_TELL, ["monitor started but no heartbeat with its token"],
                      pane_id=pane_id, tab_id=tab_id)


def cmd_stop(args):
    paths = Paths(args.team_dir)
    if lock_free(paths):
        return g.emit(SCRIPT, g.PASS, ["not running"])
    binding, ok = bound(paths)
    if not ok:
        return g.emit(SCRIPT, g.CANNOT_TELL, ["the running monitor's pane is not bound to it; "
                                              "find it with herdr pane list and stop it by hand"])
    pane = binding["pane_id"]
    g.herdr("pane", "send-keys", pane, "ctrl+c", parse=False)
    deadline = time.time() + 10
    while time.time() < deadline:
        if lock_free(paths):
            return g.emit(SCRIPT, g.PASS, [], pane_id=pane, tab_id=binding.get("tab_id"))
        time.sleep(0.2)
    return g.emit(SCRIPT, g.CANNOT_TELL, ["monitor did not stop within 10s"], pane_id=pane)


def cmd_hold(args):
    paths = Paths(args.team_dir)
    paths.ensure()
    with Flock(paths.prompt_lock):
        write_json(hold_path(paths, args.assignment, args.attempt),
                   {"reason": args.reason, "at": iso(clock())})
    return g.emit(SCRIPT, g.PASS, [], hold=str(hold_path(paths, args.assignment, args.attempt)))


def cmd_unhold(args):
    paths = Paths(args.team_dir)
    with Flock(paths.prompt_lock):
        marker = hold_path(paths, args.assignment, args.attempt)
        existed = marker.exists()
        if existed:
            marker.unlink()
    return g.emit(SCRIPT, g.PASS, [] if existed else ["no hold"], removed=existed)


def classify_prompt(code, out):
    text = out or ""
    try:
        data = json.loads(text.strip().splitlines()[-1]) if text.strip() else {}
    except json.JSONDecodeError:
        data = {}
    error = (data.get("error") or {}).get("code") if isinstance(data, dict) else None
    if error == "agent_blocked" or "agent_blocked" in text:
        return "rejected_blocked"
    if error == "agent_prompt_stalled" or "agent_prompt_stalled" in text:
        return "stalled"
    if code != 0 or error:
        return "uncertain"
    matched = find_key(data, "agent_status") or find_key(data, "status") or find_key(data, "state")
    return "landed_blocked" if matched == "blocked" else "landed"


def cmd_dispatch_prompt(args):
    paths = Paths(args.team_dir)
    paths.ensure()
    text = Path(args.text_file).read_text(encoding="utf-8") if args.text_file else args.text
    with Flock(paths.prompt_lock):
        team, item = current_item(paths, args.assignment, args.attempt, args.role)
        if team is None:
            raise g.CannotTell("team files unreadable")
        if item is None:
            return g.emit(SCRIPT, g.REFUSE, [f"{args.assignment} attempt {args.attempt} is not a dispatched "
                                             f"Assignment of {args.role}, or it is on hold; nothing sent"])
        existing = dispatch_records(paths, args.assignment, args.attempt)
        if existing and existing[-1].get("result") in ("sending", "uncertain") and not args.resend_after_check:
            return g.emit(SCRIPT, g.REFUSE, ["the previous prompt's delivery is unknown; agent read first, "
                                             "then pass --resend-after-check only if it did not land"])
        info = g.agent_info(args.role)
        mismatch, missing = g.identity_mismatch(args.role, team.role_state(args.role), info)
        if mismatch or missing:
            return g.emit(SCRIPT, g.REFUSE if mismatch else g.CANNOT_TELL,
                          ["identity check failed; nothing sent"] + mismatch + missing)
        ws = team.workspace(args.assignment)
        sha, count = handoff_identity(ws, args.attempt)
        n = (int(existing[-1]["n"]) + 1) if existing else 1
        record_path = paths.dispatch / f"{args.assignment}-{args.attempt}-{n}.json"
        record = {"n": n, "assignment": args.assignment, "attempt": args.attempt, "role": args.role,
                  "result": "sending", "at": iso(clock()), "handoff_sha8": sha, "handoff_count": count,
                  "session": session_of(info)}
        write_json(record_path, record)
        try:
            proc = subprocess.run([g.herdr_bin(), "agent", "prompt", args.role, text, "--wait",
                                   "--until", "working", "--until", "blocked", "--timeout", "15000"],
                                  capture_output=True, text=True, timeout=30)
            code, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, out = -1, str(exc)
        result = classify_prompt(code, out)
        record.update({"result": result, "at": iso(clock()), "raw": out[-400:]})
        write_json(record_path, record)
    exit_code = {"landed": g.PASS, "landed_blocked": g.PASS, "rejected_blocked": g.REFUSE,
                 "stalled": g.REFUSE, "uncertain": g.CANNOT_TELL}[result]
    return g.emit(SCRIPT, exit_code, [] if exit_code == g.PASS else [result], result=result, n=n)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "start", "stop", "status", "drain", "ack", "compact", "hold", "unhold",
                 "dispatch-prompt"):
        p = sub.add_parser(name)
        p.add_argument("--team-dir", required=True)
        if name == "run":
            p.add_argument("--ticks", type=int, default=0)
            p.add_argument("--launch-token")
        if name in ("hold", "unhold"):
            p.add_argument("--assignment", required=True)
            p.add_argument("--attempt", required=True, type=int)
            if name == "hold":
                p.add_argument("--reason", required=True)
        if name == "ack":
            group = p.add_mutually_exclusive_group(required=True)
            group.add_argument("--through", type=int)
            group.add_argument("--handled")
        if name == "compact":
            p.add_argument("--keep", type=int, default=200)
        if name == "dispatch-prompt":
            p.add_argument("--role", required=True)
            p.add_argument("--assignment", required=True)
            p.add_argument("--attempt", required=True, type=int)
            body = p.add_mutually_exclusive_group(required=True)
            body.add_argument("--text")
            body.add_argument("--text-file")
            p.add_argument("--resend-after-check", action="store_true")
    args = parser.parse_args(argv)
    handlers = {"run": cmd_run, "start": cmd_start, "stop": cmd_stop, "status": cmd_status,
                "drain": cmd_drain, "ack": cmd_ack, "compact": cmd_compact,
                "hold": cmd_hold, "unhold": cmd_unhold,
                "dispatch-prompt": cmd_dispatch_prompt}
    return g.run_gate(SCRIPT, lambda: handlers[args.command](args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
