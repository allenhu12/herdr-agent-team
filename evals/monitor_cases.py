"""Offline cases for assets/team-monitor.py. Called by check_package.py.

Each case drives the monitor one loop at a time (`run --ticks N`) with a
fake Herdr and a fake clock (HAT_MONITOR_CLOCK). Every tick is a new
process, so each case also exercises restart from the files on disk.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from gate_cases import ASSETS, Fixture, git

LEAD = "t-lead-opus"


def mfix(tmp, steering="prompt"):
    f = Fixture(tmp)
    f.team["monitor"] = "team"
    f.team["roles"][0]["steering"] = steering
    f.state["lead"] = {"name": LEAD, "pane_id": "w1:p1", "kind": "claude", "cwd": str(f.tmp),
                       "process_identity": {"agent_session_id": "sess-lead"}}
    f.agents[LEAD] = {"agent": {"agent": "claude", "agent_status": "working", "pane_id": "w1:p1",
                                "cwd": str(f.tmp), "agent_session": {"value": "sess-lead"}}}
    f.clock = f.tmp / "clock"
    f.clock.write_text("1000000")
    f.save()
    return f


def env(f, **extra):
    e = f.env()
    e.update({"HAT_MONITOR_CLOCK": str(f.clock), "HAT_MONITOR_LOOP_S": "0",
              "HAT_INBOX_GRACE_S": "0", "HAT_INBOX_RING_MAX": "2", "HAT_INBOX_POLL_S": "0"})
    e.update(extra)
    return e


def mon(f, *args, **extra):
    proc = subprocess.run([sys.executable, str(ASSETS / "team-monitor.py"), *args, "--team-dir", str(f.team_dir)],
                          capture_output=True, text=True, env=env(f, **extra), timeout=60)
    lines = proc.stdout.strip().splitlines()
    try:
        out = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        out = {"raw": proc.stdout, "stderr": proc.stderr}
    out["_rc"], out["_stdout"] = proc.returncode, proc.stdout
    return out


def tick(f, n=1, **extra):
    return mon(f, "run", "--ticks", str(n), **extra)


def at(f, t):
    f.clock.write_text(str(1000000 + t))


def wakes(f):
    return mon(f, "drain").get("wakes", [])


def outcomes(f):
    return [w["outcome"] for w in wakes(f)]


def log(f):
    return json.loads(f.herdr_state.read_text()).get("log", [])


def set_agent(f, name, **fields):
    data = json.loads(f.herdr_state.read_text())
    data["agents"][name]["agent"].update(fields)
    data["agents"][name].pop("statuses", None)
    f.herdr_state.write_text(json.dumps(data))
    f.agents[name]["agent"].update(fields)


def statuses(f, name, seq):
    data = json.loads(f.herdr_state.read_text())
    data["agents"][name]["statuses"] = seq
    f.herdr_state.write_text(json.dumps(data))


def dispatch(f, aid="a1", attempt=1, role="t-impl-sol", *extra):
    return mon(f, "dispatch-prompt", "--role", role, "--assignment", aid, "--attempt", str(attempt),
               "--text", "Read assignment.md", *extra)


def report(f, aid="a1", attempt=1):
    ws = f.team_dir / "assignments" / aid
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "report.md").write_text(f"# Report: {aid}\n**Attempt:** {attempt}\n")


def queue_and_report_cases(check):
    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        set_agent(f, "t-impl-sol", agent_status="working")
        report(f)
        tick(f, 2)
        tick(f)
        check("monitor queues exactly one report wake across loops and restarts",
              outcomes(f) == ["report"], wakes(f))
        out = mon(f, "drain")
        check("drain prints WAKE_ACK_REQUIRED and a JSON last line",
              "WAKE_ACK_REQUIRED=1" in out["_stdout"] and out.get("wake_ack_required") == 1, out)
        (f.team_dir / "monitor" / "seen.json").unlink()
        tick(f)
        check("a lost seen.json cache is rebuilt from wake files: no duplicate", len(wakes(f)) == 1, wakes(f))
        check("ack refuses a seq that does not exist", mon(f, "ack", "--through", "9")["_rc"] == 1)
        check("ack advances", mon(f, "ack", "--through", "1").get("acked") == 1 and wakes(f) == [])
        out = mon(f, "ack", "--through", "0")
        check("ack never moves back", out["_rc"] == 0 and out.get("acked") == 1, out)

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        f.add_assignment("a2", assignee="t-test-luna", status="running", paths=[f"{f.repo}/docs/**"])
        report(f, "a1")
        report(f, "a2")
        set_agent(f, "t-impl-sol", agent_status="working")
        set_agent(f, "t-test-luna", agent_status="working")
        tick(f)
        f.add_assignment("a3", assignee="t-impl-sol", status="pending", paths=[f"{f.repo}/x/**"])
        report(f, "a3")
        tick(f)
        out = mon(f, "ack", "--handled", "1,3")
        check("ack --handled stops at the first unhandled wake (contiguous prefix)",
              out.get("acked") == 1 and [w["seq"] for w in wakes(f)] == [2, 3], out)

    for point in ("after_temp", "after_rename", "before_cache"):
        with tempfile.TemporaryDirectory() as tmp:
            f = mfix(tmp)
            f.add_assignment("a1", status="running")
            set_agent(f, "t-impl-sol", agent_status="working")
            report(f)
            crashed = tick(f, HAT_MONITOR_CRASH_AT=point)
            tick(f)
            check(f"a crash {point.replace('_', ' ')} still leaves exactly one wake",
                  crashed["_rc"] == 9 and outcomes(f) == ["report"], (crashed["_rc"], wakes(f)))


def lifecycle_cases(check):
    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="pending")
        statuses(f, "t-impl-sol", ["working", "idle"])
        tick(f, 3)
        at(f, 100)
        tick(f)
        check("work seen before the dispatch prompt landed never triggers a nudge (dispatch race)",
              not any(e[0] == "prompt" and e[1] == "t-impl-sol" for e in log(f)) and outcomes(f) == [],
              (log(f), wakes(f)))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        set_agent(f, "t-impl-sol", agent_status="idle")
        dispatch(f)
        f.herdr_state.write_text(json.dumps({**json.loads(f.herdr_state.read_text()), "log": []}))
        tick(f)
        check("an idle role right after a landed dispatch is not nudged before the settle time",
              not any(e[0] == "prompt" and e[1] == "t-impl-sol" for e in log(f)), log(f))
        statuses(f, "t-impl-sol", ["working", "idle"])
        tick(f)
        tick(f)
        nudges = [e for e in log(f) if e[0] == "prompt" and e[1] == "t-impl-sol"]
        check("after working then idle the role gets exactly one typed nudge",
              len(nudges) == 1 and "report.md" in nudges[0][2], log(f))
        tick(f)
        check("no second nudge on the next loop",
              len([e for e in log(f) if e[0] == "prompt" and e[1] == "t-impl-sol"]) == 1)
        at(f, 200)
        tick(f)
        check("still no report after the settle time gives no_report", outcomes(f) == ["no_report"], wakes(f))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        set_agent(f, "t-impl-sol", agent_status="blocked")
        tick(f)
        at(f, 19)
        tick(f)
        check("blocked under 20s is not queued", outcomes(f) == [])
        at(f, 20)
        tick(f)
        check("blocked for 20s is queued once", outcomes(f) == ["blocked"])
        set_agent(f, "t-impl-sol", agent_status="working")
        at(f, 21)
        tick(f)
        set_agent(f, "t-impl-sol", agent_status="blocked")
        at(f, 22)
        tick(f)
        at(f, 42)
        tick(f)
        keys = [w["key"] for w in wakes(f)]
        check("a second blocked episode gets its own wake", keys == ["a1:1:blocked#1", "a1:1:blocked#2"], keys)
        set_agent(f, "t-impl-sol", agent_status="unknown")
        at(f, 50)
        tick(f)
        at(f, 110)
        tick(f)
        check("unknown for 60s is queued", "unknown" in outcomes(f), outcomes(f))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        data = json.loads(f.herdr_state.read_text())
        data["agents"].pop("t-impl-sol")
        data["agents"].pop("t-test-luna")
        f.herdr_state.write_text(json.dumps(data))
        tick(f)
        check("a vanished working role gives gone; a vanished idle role gives role_gone",
              sorted(outcomes(f)) == ["gone", "role_gone"], wakes(f))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        item = f.add_assignment("a1", status="running")
        item["dispatched_at"] = "1970-01-12T13:46:30Z"  # epoch 1000000 - 10
        item["deadline_s"] = 5
        f.save()
        set_agent(f, "t-impl-sol", agent_status="working")
        tick(f)
        check("the deadline gives one timeout wake", outcomes(f) == ["timeout"], wakes(f))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running", attempt=2)
        set_agent(f, "t-impl-sol", agent_status="working")
        report(f, "a1", attempt=1)
        tick(f)
        check("a report for a past attempt gives no wake", outcomes(f) == [])


def inbox_cases(check):
    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp, steering="inbox")
        f.add_assignment("a1", status="running")
        dispatch(f)
        statuses(f, "t-impl-sol", ["working", "idle"])
        tick(f, 4)
        box = f.team_dir / "inbox" / "t-impl-sol"
        msgs = sorted(p.name for p in box.glob("*.msg"))
        check("inbox nudge is one keyed message, rung through the inbox",
              msgs == ["0001.msg"] and "key=a1:1:nudge" in (box / "0001.msg").read_text()
              and any("INBOX:" in e[2] for e in log(f) if e[0] == "prompt"), (msgs, log(f)))
        check("unacknowledged inbox nudge gives inbox_unacked", "inbox_unacked" in outcomes(f), wakes(f))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp, steering="inbox")
        box = f.team_dir / "inbox" / "t-impl-sol"
        f.agents["t-impl-sol"]["on_prompt"] = {"move_inbox": str(box)}
        f.add_assignment("a1", status="running")
        dispatch(f)
        statuses(f, "t-impl-sol", ["working", "idle"])
        data = json.loads(f.herdr_state.read_text())
        data["agents"]["t-impl-sol"]["on_prompt"] = {"move_inbox": str(box)}
        f.herdr_state.write_text(json.dumps(data))
        tick(f, 3)
        check("an acknowledged inbox nudge with no report gives no_report",
              outcomes(f) == ["no_report"], wakes(f))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp, steering="inbox")
        args = ["send", "--team-dir", str(f.team_dir), "--role", "t-impl-sol", "--kind", "note",
                "--body", "x", "--no-ring", "--key", "k1"]
        first = subprocess.run([sys.executable, str(ASSETS / "inbox.py"), *args], capture_output=True,
                               text=True, env=env(f))
        second = subprocess.run([sys.executable, str(ASSETS / "inbox.py"), *args], capture_output=True,
                                text=True, env=env(f))
        a = json.loads(first.stdout.strip().splitlines()[-1])
        b = json.loads(second.stdout.strip().splitlines()[-1])
        check("inbox send --key is idempotent", a["msg"] == b["msg"] and b.get("duplicate") is True, (a, b))
        set_agent(f, "t-impl-sol", agent_status="idle")
        tick(f, 3)
        check("an idle role with no Assignment still gets its inbox rung and escalated",
              outcomes(f) == ["inbox_unacked"] and wakes(f)[0]["kind"] == "inbox", wakes(f))


def lead_cases(check):
    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        set_agent(f, "t-impl-sol", agent_status="working")
        report(f)
        tick(f)
        lead_prompts = lambda: [e for e in log(f) if e[0] == "prompt" and e[1] == LEAD]
        check("no doorbell while the Lead is working", not lead_prompts())
        set_agent(f, LEAD, agent_status="idle")
        at(f, 10)
        tick(f)
        at(f, 39)
        tick(f)
        check("no doorbell before the Lead has been idle for the hold time", not lead_prompts())
        at(f, 40)
        tick(f)
        check("doorbell once the Lead has been idle for the hold time",
              len(lead_prompts()) == 1 and lead_prompts()[0][2].startswith("WAKE: run"), log(f))
        at(f, 41)
        tick(f)
        check("no repeat doorbell inside the grace period", len(lead_prompts()) == 1)
        f.add_assignment("a2", assignee="t-test-luna", status="running", paths=[f"{f.repo}/docs/**"])
        report(f, "a2")  # add_assignment re-saves the fake Herdr state, which clears its log
        set_agent(f, "t-test-luna", agent_status="working")
        at(f, 42)
        tick(f)
        check("a newer wake rings again", len(lead_prompts()) == 1, log(f))
        set_agent(f, LEAD, pane_id="w5:p9")
        at(f, 400)
        tick(f)
        check("a Lead with another pane is not rung and gives identity_fault",
              len(lead_prompts()) == 1 and "identity_fault" in outcomes(f), (outcomes(f), log(f)))
        data = json.loads(f.herdr_state.read_text())
        data["agents"].pop(LEAD)
        f.herdr_state.write_text(json.dumps(data))
        at(f, 900)
        tick(f)
        check("an absent Lead is not rung; wakes stay queued", len(lead_prompts()) == 1 and len(wakes(f)) == 3,
              (log(f), wakes(f)))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        dispatch(f)
        statuses(f, "t-impl-sol", ["working", "idle"])
        data = json.loads(f.herdr_state.read_text())
        data["agents"]["t-impl-sol"]["agent"]["agent_session"]["value"] = "sess-new"
        data["log"] = []
        f.herdr_state.write_text(json.dumps(data))
        tick(f, 3)
        role_prompts = lambda: [e for e in log(f) if e[0] == "prompt" and e[1] == "t-impl-sol"]
        check("a new process under the same name and pane gets no nudge, one identity_fault",
              not role_prompts() and outcomes(f) == ["identity_fault"], (log(f), wakes(f)))
        f.reload()
        f.state["roles"]["t-impl-sol"]["process_identity"]["agent_session_id"] = "sess-new"
        (f.team_dir / "team-state.yaml").write_text(__import__("yaml").safe_dump(f.state, sort_keys=False))
        tick(f)
        check("after Resume records the verified new process, the quarantine lifts and the nudge goes out",
              len(role_prompts()) == 1, log(f))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        dispatch(f)
        statuses(f, "t-impl-sol", ["working", "idle"])
        data = json.loads(f.herdr_state.read_text())
        cwd = data["agents"]["t-impl-sol"]["agent"].pop("cwd")
        data["log"] = []
        f.herdr_state.write_text(json.dumps(data))
        tick(f, 2)
        role_prompts = lambda: [e for e in log(f) if e[0] == "prompt" and e[1] == "t-impl-sol"]
        check("missing live evidence quarantines the role", not role_prompts() and outcomes(f) == ["identity_fault"])
        data = json.loads(f.herdr_state.read_text())
        data["agents"]["t-impl-sol"]["agent"]["cwd"] = cwd
        f.herdr_state.write_text(json.dumps(data))
        tick(f)
        check("the same process stays quarantined until Resume records a new verification", not role_prompts())
        f.reload()
        f.state["roles"]["t-impl-sol"]["launch_verification"]["verified_at"] = "2026-10-27T12:00:00Z"
        (f.team_dir / "team-state.yaml").write_text(__import__("yaml").safe_dump(f.state, sort_keys=False))
        tick(f)
        check("re-verifying the same process lifts the quarantine", len(role_prompts()) == 1, log(f))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        set_agent(f, "t-impl-sol", agent_status="working")
        report(f)
        set_agent(f, LEAD, agent_status="idle", agent_session={"value": "sess-lead-2"})
        tick(f)
        at(f, 100)
        tick(f)
        lead_prompts = lambda: [e for e in log(f) if e[0] == "prompt" and e[1] == LEAD]
        check("a replaced Lead process is quarantined", not lead_prompts() and "identity_fault" in outcomes(f))
        f.reload()
        f.state["lead"]["process_identity"]["agent_session_id"] = "sess-lead-2"
        (f.team_dir / "team-state.yaml").write_text(__import__("yaml").safe_dump(f.state, sort_keys=False))
        at(f, 200)
        tick(f)
        at(f, 300)
        tick(f)
        check("after the Lead record is updated the doorbell resumes", len(lead_prompts()) == 1, log(f))


def dispatch_cases(check):
    def dp(f):
        return mon(f, "dispatch-prompt", "--role", "t-impl-sol", "--assignment", "a1", "--attempt", "1",
                   "--text", "Read assignment.md")

    for result, rc, recorded, wake in (("landed", 0, "landed", None), ("blocked", 0, "landed_blocked", None),
                                       ("rejected", 1, "rejected_blocked", "blocked"),
                                       ("stalled", 1, "stalled", "stalled"),
                                       ("timeout", 3, "uncertain", "prompt_uncertain")):
        with tempfile.TemporaryDirectory() as tmp:
            f = mfix(tmp)
            f.add_assignment("a1", status="running")
            data = json.loads(f.herdr_state.read_text())
            data["agents"]["t-impl-sol"]["prompt_result"] = result
            data["agents"]["t-impl-sol"]["agent"]["agent_status"] = "working"
            f.herdr_state.write_text(json.dumps(data))
            out = dp(f)
            sent = [e for e in log(f) if e[0] == "prompt"]
            tick(f)
            check(f"dispatch-prompt {result}: exit {rc}, recorded {recorded}"
                  + (f", wake {wake}" if wake else ", no wake"),
                  out["_rc"] == rc and out.get("result") == recorded
                  and sent and "--until" in sent[0] and "working" in sent[0]
                  and outcomes(f) == ([wake] if wake else []), (out, sent, wakes(f)))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        set_agent(f, "t-impl-sol", agent_status="working")
        rec = f.team_dir / "monitor" / "dispatch" / "a1-1-1.json"
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text(json.dumps({"n": 1, "result": "sending", "at": "1970-01-12T13:46:40Z"}))
        tick(f)
        check("a fresh sending record is not yet uncertain", outcomes(f) == [])
        at(f, 60)
        tick(f)
        check("a sending record the sender never finished becomes prompt_uncertain",
              outcomes(f) == ["prompt_uncertain"], wakes(f))
        out = dp(f)
        check("dispatch-prompt refuses to resend after an unknown delivery without the flag",
              out["_rc"] == 1 and not [e for e in log(f) if e[0] == "prompt"], out)
        out = mon(f, "dispatch-prompt", "--role", "t-impl-sol", "--assignment", "a1", "--attempt", "1",
                  "--text", "Read assignment.md", "--resend-after-check")
        check("dispatch-prompt resends with --resend-after-check as record 2",
              out["_rc"] == 0 and out.get("n") == 2, out)
        mon(f, "hold", "--assignment", "a1", "--attempt", "1", "--reason", "cancel")
        out = mon(f, "dispatch-prompt", "--role", "t-impl-sol", "--assignment", "a1", "--attempt", "1",
                  "--text", "x", "--resend-after-check")
        check("dispatch-prompt refuses under a hold", out["_rc"] == 1 and "hold" in " ".join(out["reasons"]), out)
        out = mon(f, "dispatch-prompt", "--role", "t-impl-sol", "--assignment", "a9",
                  "--attempt", "1", "--text", "x")
        check("dispatch-prompt refuses an Assignment that is not dispatched", out["_rc"] == 1, out)

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        set_agent(f, "t-impl-sol", agent_session={"value": "sess-other"})
        out = dp(f)
        check("dispatch-prompt sends nothing to an unverified process",
              out["_rc"] == 1 and not log(f), out)

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        set_agent(f, "t-impl-sol", agent_status="idle")
        ws = f.team_dir / "assignments" / "a1"
        ws.mkdir(parents=True)
        dp(f)
        (ws / "handoff.md").write_text("# Handoff\n**Attempt:** 1\nfirst\n")
        (ws / "log.md").write_text("HANDOFF READY attempt=1\n")
        tick(f)
        dp(f)  # Rotate continuation records the current handoff as the new baseline
        tick(f)
        (ws / "handoff.md").write_text("# Handoff\n**Attempt:** 1\nsecond\n")
        (ws / "log.md").write_text("HANDOFF READY attempt=1\nHANDOFF READY attempt=1\n")
        tick(f)
        check("two handoffs in one attempt each wake once",
              outcomes(f) == ["handoff", "handoff"], [w["key"] for w in wakes(f)])


def safety_cases(check):
    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        dispatch(f)
        mon(f, "hold", "--assignment", "a1", "--attempt", "1", "--reason", "cancel")
        data = json.loads(f.herdr_state.read_text())
        data["log"] = []
        f.herdr_state.write_text(json.dumps(data))
        statuses(f, "t-impl-sol", ["working", "idle"])
        tick(f, 3)
        at(f, 500)
        tick(f)
        check("a hold marker silences nudges and wakes for that Assignment",
              not any(e[0] == "prompt" and e[1] == "t-impl-sol" for e in log(f)) and outcomes(f) == [],
              (log(f), wakes(f)))
        rc, out = f.precheck(role="t-test-luna", scope=[f"{f.repo}/src/**"], assignment="a2")
        check("during the hold the old lease still blocks an overlapping dispatch",
              rc == 1 and any("overlaps" in r for r in out["reasons"]), out)

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        f.add_assignment("a1", status="running")
        dispatch(f)
        (f.team_dir / "monitor").mkdir(parents=True, exist_ok=True)
        (f.team_dir / "monitor" / "intents.json").write_text(json.dumps(
            {"a1:1:nudge": {"state": "sending", "target": "t-impl-sol", "typed_work": True}}))
        data = json.loads(f.herdr_state.read_text())
        data["log"] = []
        f.herdr_state.write_text(json.dumps(data))
        statuses(f, "t-impl-sol", ["working", "idle"])
        tick(f, 3)
        at(f, 500)
        tick(f, 2)
        check("a typed nudge interrupted mid-send is never resent; it becomes nudge_uncertain",
              "nudge_uncertain" in outcomes(f)
              and not [e for e in log(f) if e[0] == "prompt" and e[1] == "t-impl-sol"], (wakes(f), log(f)))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        (f.team_dir / "team-state.yaml").write_text("roles: [broken\n")
        out = tick(f, 2)
        check("a broken team-state.yaml gives one monitor_error and the monitor keeps running",
              out["_rc"] == 0 and outcomes(f) == ["monitor_error"], (out, wakes(f)))

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        e = env(f, HAT_MONITOR_LOOP_S="0.2")
        first = subprocess.Popen([sys.executable, str(ASSETS / "team-monitor.py"), "run", "--team-dir",
                                  str(f.team_dir), "--ticks", "100"], env=e,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.0)
        second = mon(f, "run", "--ticks", "1")
        status = mon(f, "status")
        first.terminate()
        first.wait(timeout=10)
        check("a second monitor cannot take the lock (exit 2)", second["_rc"] == 2, second)
        check("status reports a live monitor healthy", status.get("healthy") is True, status)
        check("status reports a stopped monitor unhealthy", mon(f, "status")["_rc"] == 1)

    with tempfile.TemporaryDirectory() as tmp:
        f = mfix(tmp)
        extra = {"HAT_MONITOR_LOOP_S": "0.2", "HAT_FAKE_PANE_EXEC": "1"}
        procs = [subprocess.Popen([sys.executable, str(ASSETS / "team-monitor.py"), "start", "--team-dir",
                                   str(f.team_dir)], stdout=subprocess.PIPE, text=True, env=env(f, **extra))
                 for _ in range(2)]
        outs = [json.loads(p.communicate(timeout=60)[0].strip().splitlines()[-1]) for p in procs]
        tabs = [e for e in log(f) if e[:2] == ["tab", "create"]]
        binding = json.loads((f.team_dir / "monitor" / "binding.json").read_text())
        check("two concurrent starts create one monitor tab and one binding",
              len(tabs) == 1 and sorted(o["result"] for o in outs) == ["pass", "pass"]
              and binding.get("pane_id") == "w9:p1", (outs, tabs, binding))
        status = mon(f, "status", **extra)
        check("status shows the running monitor bound to its pane",
              status.get("healthy") is True and status.get("bound") is True, status)
        stop = mon(f, "stop", **extra)
        check("stop interrupts the bound pane and the lock is released",
              stop["_rc"] == 0 and mon(f, "status")["_rc"] == 1, stop)


def run(check):
    queue_and_report_cases(check)
    lifecycle_cases(check)
    inbox_cases(check)
    lead_cases(check)
    dispatch_cases(check)
    safety_cases(check)
