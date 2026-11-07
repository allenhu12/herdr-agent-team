#!/usr/bin/env python3
"""Move one Sub-Agent's live pane into its own Herdr tab.

Usage: move-to-tab.py --team-dir <abs> --role <name> [--dry-run]

For a team that moves from layout chain to layout tabs (adjust.md "Move a
live team to tabs"). The agent keeps running: pane id, terminal and session
stay the same, so its launch verification stays valid.

Before any Herdr change: the role must be in team.yaml with a recorded state
record; the live agent must match that record (pane, kind, cwd, session; see
gate_lib.identity_mismatch); and its state must be idle or done (working or
blocked refuse; unknown is cannot tell). The state is read again just before
the move.
If the pane is already alone in its tab, the tab is renamed to the role name
and its tab_id is recorded. Otherwise: turn zoom off in the source tab, then
`herdr pane move <pane> --new-tab --label <role> --no-focus` (one call: the
Lead keeps focus). A zoomed tab returns `changed: false` with exit 0, so
`changed: true` is required. After the move the agent must still match its
record and sit in the new tab; only then is roles.<name>.tab_id written.
--dry-run reports what it would do and changes nothing.

Exit: 0 moved or already alone, 1 refuse, 2 usage, 3 cannot tell.
The last stdout line is JSON. On exit 3 after a move, the reasons name the
new tab so the Lead can check it by hand.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True

import gate_lib as g  # noqa: E402

SCRIPT = "move-to-tab"
SETTLED = ("idle", "done")


def call(*args):
    code, data = g.herdr(*args)
    if code != 0 or data.get("error"):
        raise g.CannotTell(f"herdr {' '.join(args)}: {data.get('error') or code}")
    return (data or {}).get("result") or {}


def checked_agent(role, rec):
    """The live agent, verified against the record and settled; else exit early."""
    info = g.agent_info(role)
    if info is None:
        return None, g.emit(SCRIPT, g.REFUSE, [f"{role} is gone; use Resume first"])
    mismatches, missing = g.identity_mismatch(role, rec, info)
    if mismatches:
        return None, g.emit(SCRIPT, g.REFUSE, mismatches)
    if missing:
        raise g.CannotTell("; ".join(missing))
    state = g.agent_state(info)
    if state in ("working", "blocked"):
        return None, g.emit(SCRIPT, g.REFUSE, [f"{role} is {state}; move it when it is idle"])
    if state not in SETTLED:
        raise g.CannotTell(f"{role} state is {state}; not proven settled")
    if not info.get("tab_id"):
        raise g.CannotTell(f"herdr agent get {role} gave no tab_id")
    return info, None


def record(team, role, tab_id):
    team.state["roles"][role]["tab_id"] = tab_id
    team.save_state()


def body(args):
    team = g.Team(args.team_dir)
    if team.role(args.role) is None:
        return g.emit(SCRIPT, g.USAGE, [f"{args.role} is not a role in team.yaml"])
    rec = team.role_state(args.role)
    if not rec:
        return g.emit(SCRIPT, g.REFUSE, [f"{args.role} has no record in team-state.yaml; assemble or resume it first"])
    info, early = checked_agent(args.role, rec)
    if early is not None:
        return early
    pane, tab = info["pane_id"], info["tab_id"]
    current = call("tab", "get", tab).get("tab") or {}
    if current.get("pane_count") == 1:
        if args.dry_run:
            return g.emit(SCRIPT, g.PASS, ["already alone in its tab"], pane_id=pane, tab_id=tab, dry_run=True)
        if current.get("label") != args.role:
            call("tab", "rename", tab, args.role)
        record(team, args.role, tab)
        return g.emit(SCRIPT, g.PASS, ["already alone in its tab"], pane_id=pane, tab_id=tab)
    if args.dry_run:
        return g.emit(SCRIPT, g.PASS, [], dry_run=True, pane_id=pane, from_tab=tab)
    info, early = checked_agent(args.role, rec)   # read again just before the change
    if early is not None:
        return early
    call("pane", "zoom", "--pane", pane, "--off")
    outcome = call("pane", "move", pane, "--new-tab", "--label", args.role, "--no-focus").get("move_result") or {}
    if outcome.get("changed") is not True:
        raise g.CannotTell(f"herdr pane move did not move {pane}: reason {outcome.get('reason')!r}")
    new_tab = (outcome.get("created_tab") or {}).get("tab_id") or (outcome.get("pane") or {}).get("tab_id")
    if not new_tab:
        raise g.CannotTell(f"herdr pane move gave no new tab id; find {pane} by hand")
    after = g.agent_info(args.role)
    mismatches, missing = g.identity_mismatch(args.role, rec, after)
    if mismatches or missing or (after or {}).get("tab_id") != new_tab:
        raise g.CannotTell(f"{args.role} moved to tab {new_tab} but does not match its record there: "
                           + "; ".join(mismatches + missing or ["tab differs"]))
    record(team, args.role, new_tab)
    return g.emit(SCRIPT, g.PASS, [], pane_id=pane, from_tab=tab, tab_id=new_tab)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--team-dir", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--dry-run", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return g.emit(SCRIPT, g.USAGE, ["bad arguments"])
    return g.run_gate(SCRIPT, lambda: body(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
