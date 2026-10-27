#!/usr/bin/env python3
"""Answer "may the Lead dispatch this Assignment now?" (dispatch.md steps 1-2a).

Usage:
  dispatch-precheck.py --team-dir <abs> --role <name> --assignment <id> --attempt <n>
                       --kind source|tester|reader|knowledge
                       [--scope <abs path or dir/**> ...] [--output <abs path or dir/**> ...]
                       [--rework] [--repo <code repo name> ...]

--repo (tester only) names the repositories the tester tests; it is required
when the team has more than one code repository. A commit made before 4.3.0
has no post-commit baseline: the gate then compares with that Assignment's
dispatch baseline minus the committed files, or, with no baseline at all,
passes that repository with a warning (the 4.2.0 rule).

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


def check_shared(team, args, role_name, refuse, unknown, warnings):
    if team.team.get("checkout_mode") != "shared":
        return
    active = [a for a in team.assignments() if g.is_dispatched(a) and a.get("id") != args.assignment]
    if args.kind == "source":
        for item in active:
            # A record from before 4.3.0 has no kind: the template's tester role names say "-tester-".
            legacy_tester = item.get("kind") is None and "-tester-" in str(item.get("assignee"))
            if item.get("kind") == "tester" or legacy_tester:
                refuse.append(f"tester window open ({item.get('id')}); no source work until it settles")
        return
    if args.kind != "tester":
        return
    log = team.state.get("commit_log") or []
    names = list(args.repo)
    if not names:
        if len(team.code_repos()) == 1:
            names = [team.code_repos()[0]["name"]]
        else:
            unknown.append("name the repositories this tester tests with --repo (the team has "
                           f"{len(team.code_repos())} code repositories)")
            return
    db = load_sibling("dirty-baseline.py")
    for name in names:
        repo = team.repo(name)
        if repo is None:
            refuse.append(f"--repo {name} is not in team.yaml code_repos")
            continue
        legacy_writers = repo_writers(team, repo, role_name)
        for item in active:
            # A record from before 4.3.0 has no kind: a writer's Assignment counts as source work.
            if item.get("kind") == "source" or (item.get("kind") is None and item.get("assignee") in legacy_writers):
                refuse.append(f"source Assignment {item.get('id')} is still {item.get('assignment_status')}")
        head = g.git(repo["path"], "rev-parse", "HEAD")
        entries = [c for c in log if c.get("repository") == name]
        if not entries:
            refuse.append(f"{name}: HEAD {head[:12]} has no commit_log entry; tester gate needs one")
            continue
        last = entries[-1]
        if last.get("sha") != head:
            refuse.append(f"{name}: HEAD {head[:12]} is not the last accepted commit {str(last.get('sha'))[:12]}")
            continue
        source = team.assignment(last.get("assignment_id")) or archived_assignment(team, last.get("assignment_id"))
        writers = [source.get("assignee")] if source and source.get("assignee") else repo_writers(team, repo, role_name)
        for writer in writers:
            state = g.agent_state(g.agent_info(writer))
            if state not in ("idle", "done"):
                refuse.append(f"implementor {writer} is {state}; tester gate needs it idle")
        if source and source.get("post_commit_baseline"):
            baseline = [e for e in db.read_entries(source["post_commit_baseline"]) if e.get("repo") == name]
        elif source and source.get("dirty_baseline"):
            # Committed before 4.3.0: no post-commit baseline. Expect the source's
            # dispatch baseline minus the files that commit took.
            committed = {str(f) for f in last.get("files") or []}
            baseline = [e for e in db.read_entries(source["dirty_baseline"])
                        if e.get("repo") == name and e.get("path") not in committed]
        else:
            # Committed before 4.3.0 with no baseline at all (for example a
            # commit-only Assignment, or one no longer on record): the 4.2.0
            # rule applies, so only the tester's own dispatch capture and
            # tester-pre compare protect this test. Say so.
            warnings.append(f"{name}: legacy commit {str(last.get('sha'))[:12]} from "
                            f"{last.get('assignment_id')} has no recorded baseline; drift since that commit "
                            "is not checked (4.2.0 rule); tester-pre still checks the tester's own baseline")
            continue
        current = db.scan_repo(repo)
        diffs = db.baseline_drift(baseline, current, repo["path"], [])
        refuse.extend(f"{name}: {d}" for d in diffs)


def repo_writers(team, repo, exclude):
    """Writer roles whose ceiling reaches into a code repository."""
    root = g.realpath(repo["path"])
    out = []
    for role in team.team.get("roles") or []:
        if role.get("name") == exclude or role.get("access") != "writer":
            continue
        for grant in role.get("write_ceiling") or []:
            if not os.path.isabs(os.path.expanduser(str(grant))):
                continue
            prefix, _ = g.split_glob(g.normalize_glob(grant))
            if g.under(prefix, root) or g.under(root, prefix):
                out.append(role["name"])
                break
    return out


def archived_assignment(team, assignment_id):
    """The newest archived record of an Assignment (archive-state.py format), or None."""
    path = team.dir / "state-archive.yaml"
    if not assignment_id or not path.exists():
        return None
    found = None
    import yaml
    for doc in yaml.load_all(path.read_text(encoding="utf-8"), Loader=g.StringLoader):
        if doc and doc.get("kind") == "assignment" and (doc.get("record") or {}).get("id") == assignment_id:
            found = doc["record"]
    return found


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
    parser.add_argument("--repo", action="append", default=[],
                        help="tester only: a code repository this tester tests (repeat)")
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
        warnings = []
        check_shared(team, args, args.role, refuse, unknown, warnings)
        code = g.REFUSE if refuse else (g.CANNOT_TELL if unknown else g.PASS)
        return g.emit(SCRIPT, code, refuse + unknown, warnings=warnings, role=args.role, assignment=args.assignment,
                      attempt=args.attempt, kind=args.kind, live_state=state)

    return g.run_gate(SCRIPT, body)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
