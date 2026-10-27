#!/usr/bin/env python3
"""Answer "may the Lead dispatch this Assignment now?" (dispatch.md steps 1-2a).

Usage:
  dispatch-precheck.py --team-dir <abs> --role <name> --assignment <id> --attempt <n>
                       --kind source|tester|reader|knowledge
                       [--scope <abs path or dir/**> ...] [--output <abs path or dir/**> ...]
                       [--rework]

Reads: team.yaml, team-state.yaml (roles, assignments, commit_log), live
Herdr state (`herdr agent get`, `herdr agent read --lines 3`) and git
identity of the role's checkout. It does NOT need the new Assignment's own
record: run it before writing that record (dispatch.md "Dispatch order").
It writes nothing and sends no prompt.

Exit: 0 pass, 1 refuse, 2 usage, 3 cannot tell (treat like refuse). The
last stdout line is JSON with every reason found, not only the first.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True

import gate_lib as g  # noqa: E402

SCRIPT = "dispatch-precheck"
KINDS = ("source", "tester", "reader", "knowledge")


def check_identity(team, role_name, info, refuse, unknown):
    """Live identity must equal the recorded one (identity-and-launch.md)."""
    rec = team.role_state(role_name)
    if not rec:
        refuse.append(f"{role_name}: no team-state role record")
        return
    if info is None:
        return
    mismatch, missing = g.identity_mismatch(role_name, rec, info)
    refuse.extend(m + ("; launch_verification is invalid, verify the header first"
                       if "process changed" in m else "") for m in mismatch)
    unknown.extend(missing)
    rec_cwd = rec.get("cwd")
    session = (info.get("agent_session") or {}).get("value")
    lv = rec.get("launch_verification") or {}
    lv_session = (lv.get("process_identity") or {}).get("agent_session_id")
    if not lv:
        refuse.append(f"{role_name}: no launch_verification; verify the header first")
    elif lv_session and session and lv_session != session:
        refuse.append(f"{role_name}: launch_verification belongs to another process")
    ident = rec.get("checkout_identity") or {}
    if ident.get("root") and ident.get("git_dir") and rec_cwd:
        root = g.git(rec_cwd, "rev-parse", "--show-toplevel", check=False)
        git_dir = g.git(rec_cwd, "rev-parse", "--absolute-git-dir", check=False)
        if g.realpath(root or "/nonexistent") != g.realpath(ident["root"]) or \
                g.realpath(git_dir or "/nonexistent") != g.realpath(ident["git_dir"]):
            refuse.append(f"{role_name}: checkout identity changed ({root}, {git_dir})")


def check_model(role_name, rec, refuse, unknown):
    """Only the footer text recorded at verification counts (deviation 1)."""
    footer = ((rec or {}).get("launch_verification") or {}).get("model_footer_text")
    if not footer:
        unknown.append(f"{role_name}: no model_footer_text recorded; check model/effort by hand")
        return
    try:
        screen = g.herdr("agent", "read", role_name, "--lines", "3", parse=False)
    except g.CannotTell as exc:
        unknown.append(str(exc))
        return
    if footer not in screen:
        unknown.append(f"{role_name}: recorded footer {footer!r} not on screen; "
                       "model or effort may have drifted, ask the User")


def check_busy(team, args, role_name, refuse):
    for item in team.assignments():
        if item.get("assignee") != role_name or not g.is_dispatched(item):
            continue
        same = item.get("id") == args.assignment
        if same and args.rework and item.get("assignment_status") == "pending" \
                and not g.lease_paths(item) and not any(
                    m.get("assignment_id") == item.get("id") for m in team.state.get("monitors") or []):
            continue
        refuse.append(f"{role_name}: holds active Assignment {item.get('id')} "
                      f"({item.get('assignment_status')}); reject or queue")


def check_scope(team, args, role, refuse):
    ceiling = role.get("write_ceiling") or []
    grants = list(args.scope) + list(args.output)
    if grants and role.get("access") == "reader":
        refuse.append(f"{role['name']}: reader role gets no write scope")
    for grant in grants:
        if not any(g.glob_contains(c, grant) for c in ceiling):
            refuse.append(f"scope {grant} is outside {role['name']}'s write_ceiling")
        refuse.extend(g.protected_conflicts(team, grant))
    for item in team.assignments():
        if item.get("id") == args.assignment or not g.is_dispatched(item):
            continue
        for other in g.lease_paths(item) + g.lease_outputs(item):
            for grant in grants:
                if g.logical_overlap(grant, other):
                    refuse.append(f"scope {grant} overlaps {item.get('id')}'s lease {other}")
    # Isolated and legacy teams: one writer per checkout. Shared mode gets its
    # single source writer from role ceilings (checked at Assemble/Adjust).
    if grants and team.team.get("checkout_mode") != "shared" and role.get("checkout_dir"):
        mine = g.realpath(role["checkout_dir"])
        for item in team.assignments():
            if item.get("assignee") == role["name"] or not g.is_dispatched(item) \
                    or not g.lease_paths(item):
                continue
            other_role = team.role(item.get("assignee")) or {}
            theirs = item.get("checkout_dir") or other_role.get("checkout_dir")
            if theirs and g.realpath(theirs) == mine:
                refuse.append(f"checkout {mine} already has writer {item.get('assignee')}")


def repo_heads(team):
    heads = {}
    for repo in team.code_repos():
        heads[repo["name"]] = g.git(repo["path"], "rev-parse", "HEAD")
    return heads


def check_shared(team, args, role_name, refuse, unknown):
    if team.team.get("checkout_mode") != "shared":
        return
    active = [a for a in team.assignments() if g.is_dispatched(a) and a.get("id") != args.assignment]
    if args.kind == "source":
        for item in active:
            if item.get("kind") == "tester":
                refuse.append(f"tester window open ({item.get('id')}); no source work until it settles")
        return
    if args.kind != "tester":
        return
    log = team.state.get("commit_log") or []
    for item in active:
        if item.get("kind") == "source":
            refuse.append(f"source Assignment {item.get('id')} is still {item.get('assignment_status')}")
    for name, head in repo_heads(team).items():
        entries = [c for c in log if c.get("repository") == name]
        if not entries:
            refuse.append(f"{name}: HEAD {head[:12]} has no commit_log entry; tester gate needs one")
            continue
        last = entries[-1]
        if last.get("sha") != head:
            refuse.append(f"{name}: HEAD {head[:12]} is not the last accepted commit {str(last.get('sha'))[:12]}")
            continue
        source = team.assignment(last.get("assignment_id"))
        if source is None:
            unknown.append(f"{name}: accepted Assignment {last.get('assignment_id')} not in state (archived?)")
            continue
        implementor = source.get("assignee")
        state = g.agent_state(g.agent_info(implementor)) if implementor else "unknown"
        if state not in ("idle", "done"):
            refuse.append(f"implementor {implementor} is {state}; tester gate needs it idle")
        baseline_path = source.get("post_commit_baseline")
        if not baseline_path:
            unknown.append(f"{name}: accepted Assignment {source.get('id')} has no post_commit_baseline")
            continue
        db = load_sibling("dirty-baseline.py")
        baseline = [e for e in db.read_entries(baseline_path) if e.get("repo") == name]
        current = db.scan_repo(team.repo(name))
        diffs = db.baseline_drift(baseline, current, team.repo(name)["path"], [])
        refuse.extend(f"{name}: {d}" for d in diffs)


def load_sibling(filename):
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    spec = importlib.util.spec_from_file_location(filename.replace("-", "_")[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv):
    parser = argparse.ArgumentParser(add_help=True, description=__doc__.split("\n")[0])
    parser.add_argument("--team-dir", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--assignment", required=True)
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument("--output", action="append", default=[])
    parser.add_argument("--rework", action="store_true")
    args = parser.parse_args(argv)

    def body():
        team = g.Team(args.team_dir)
        refuse, unknown = [], []
        role = team.role(args.role)
        if role is None:
            return g.emit(SCRIPT, g.REFUSE, [f"no role named {args.role} in team.yaml"])
        info = g.agent_info(args.role)
        state = g.agent_state(info)
        if state == "gone":
            refuse.append(f"{args.role} is gone; use Resume's gone branch")
        elif state == "working":
            refuse.append(f"{args.role} is working; reject or queue")
        elif state == "blocked":
            refuse.append(f"{args.role} is blocked; route through monitoring.md's blocked branch first")
        elif state not in ("idle", "done"):
            unknown.append(f"{args.role} state is {state}; agent read before deciding")
        check_identity(team, args.role, info, refuse, unknown)
        if info is not None:
            check_model(args.role, team.role_state(args.role), refuse, unknown)
        check_busy(team, args, args.role, refuse)
        check_scope(team, args, role, refuse)
        check_shared(team, args, args.role, refuse, unknown)
        code = g.REFUSE if refuse else (g.CANNOT_TELL if unknown else g.PASS)
        return g.emit(SCRIPT, code, refuse + unknown, role=args.role, assignment=args.assignment,
                      attempt=args.attempt, kind=args.kind, live_state=state)

    return g.run_gate(SCRIPT, body)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
