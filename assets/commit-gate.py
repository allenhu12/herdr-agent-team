#!/usr/bin/env python3
"""Shared-mode commit gate checks (acceptance.md "Commit gate").

Usage:
  commit-gate.py precheck --team-dir <abs> --assignment <id>
  commit-gate.py verify   --team-dir <abs> --assignment <id> [--record]

precheck runs before the Lead asks the implementor to commit. It needs the
User's approval (commit.status approved, approved_by user) or the User's
auto switch with no dirty_at_dispatch file in the list; a non-empty
commit.confirmed_files inside the accept snapshot; HEAD == input_sha on the
base branch; the accept snapshot digest equal to commit.accept_digest; every
confirmed file still holding the content the User approved; and no staged
entry outside the confirmed files.

verify runs after the commit: HEAD descends from input_sha on the base
branch, the paths that differ between input_sha and HEAD equal the
confirmed files, and their blobs equal the accept snapshot. The number of
commits is not limited, so a merge commit, which also brings the merged
branch's history, passes when its result is what the User approved. Only
the final tree counts: a change made and undone in between is not seen.
--record then writes repositories[].result_sha, appends one commit_log entry
per repository for the accepted HEAD, sets commit.status to
committed, and records post_commit_baseline for the tester gate. It never
marks the Assignment succeeded; the Lead does that.

confirmed_files forms: {repo: [paths]}, [{repo, path}], or [paths] when the
Assignment touches one repository. Paths are repository-relative.

Exit: 0 pass, 1 refuse, 2 usage, 3 cannot tell. Nothing is written on 1 or 3.
"""
import argparse
import hashlib
import importlib.util
import subprocess
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True

import gate_lib as g  # noqa: E402

SCRIPT = "commit-gate"

_spec = importlib.util.spec_from_file_location(
    "dirty_baseline", os.path.join(os.path.dirname(os.path.abspath(__file__)), "dirty-baseline.py"))
db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db)


def confirmed(item, repos):
    raw = (item.get("commit") or {}).get("confirmed_files")
    out = {r["name"]: set() for r in repos}
    if isinstance(raw, dict):
        for name, paths in raw.items():
            out.setdefault(name, set()).update(paths or [])
    elif isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict):
                out.setdefault(entry.get("repo"), set()).add(entry.get("path"))
            elif isinstance(entry, str):
                if len(repos) != 1:
                    raise g.CannotTell("bare confirmed_files paths need exactly one repository")
                out[repos[0]["name"]].add(entry)
    return {k: v for k, v in out.items() if v}


def load(args):
    team = g.Team(args.team_dir)
    item = team.assignment(args.assignment)
    if item is None:
        raise g.CannotTell(f"Assignment {args.assignment} is not in team-state.yaml")
    repos = db.touched_repos(team, item)
    if not repos:
        raise g.CannotTell(f"Assignment {args.assignment} touches no code repository")
    commit = item.get("commit") or {}
    snap_path = commit.get("accept_snapshot")
    if not snap_path:
        raise g.CannotTell("no commit.accept_snapshot; run dirty-baseline.py compare --mode accept --record")
    try:
        text = Path(snap_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise g.CannotTell(f"missing accept snapshot {snap_path}")
    return team, item, repos, commit, text, json.loads(text)


def input_sha(item, name):
    for repo in item.get("repositories") or []:
        if repo.get("name") == name and repo.get("input_sha"):
            return repo["input_sha"]
    raise g.CannotTell(f"{name}: no input_sha recorded")


def branch_ok(repo, refuse):
    branch = g.git(repo["path"], "rev-parse", "--abbrev-ref", "HEAD")
    want = repo.get("base_branch")
    if want and branch != want:
        refuse.append(f"{repo['name']}: on branch {branch}, not base_branch {want}")


def snapshot_paths(snapshot, name):
    return {p["path"]: p for p in (snapshot.get("repos") or {}).get(name, {}).get("paths", [])}


def blob_of_symlink(repo, target_b64):
    raw = db.unb64(target_b64)
    import subprocess
    proc = subprocess.run(["git", "-C", repo["path"], "hash-object", "--stdin"], input=raw, capture_output=True)
    if proc.returncode != 0:
        raise g.CannotTell("git hash-object --stdin failed")
    return proc.stdout.decode().strip()


def precheck(args):
    team, item, repos, commit, text, snapshot = load(args)
    refuse = []
    files = confirmed(item, repos)
    if not files:
        refuse.append("commit.confirmed_files is empty")
    dirty_paths = {(d.get("repo"), d.get("path")) for d in item.get("dirty_at_dispatch") or []}
    has_dirty = any((name, p) in dirty_paths for name, ps in files.items() for p in ps)
    approval = team.state.get("commit_approval") or {}
    user_ok = commit.get("status") == "approved" and commit.get("approved_by") == "user"
    auto_ok = approval.get("mode") == "auto" and approval.get("granted_by_words") and not has_dirty
    if not (user_ok or auto_ok):
        reason = "the list holds a dirty_at_dispatch file, which always needs the User" \
            if approval.get("mode") == "auto" and has_dirty else "no User approval recorded"
        refuse.append(f"commit not approved: {reason}")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != commit.get("accept_digest"):
        refuse.append("accept snapshot changed after approval (digest mismatch)")
    for repo in repos:
        name = repo["name"]
        branch_ok(repo, refuse)
        head = g.git(repo["path"], "rev-parse", "HEAD")
        if head != input_sha(item, name):
            refuse.append(f"{name}: HEAD {head[:12]} is not input_sha")
        snap = snapshot_paths(snapshot, name)
        for path in sorted(files.get(name, ())):
            if path not in snap:
                refuse.append(f"{name}: confirmed file {path} is not in the accept snapshot")
                continue
            now = db.worktree_record(repo["path"], db.unb64(snap[path]["path_b64"]))
            if now != snap[path]["worktree"]:
                refuse.append(f"{name}: {path} changed after the User approved it")
        staged = g.git(repo["path"], "diff", "--cached", "--name-only", "-z", binary=True)
        for raw in filter(None, staged.split(b"\0")):
            path = raw.decode("utf-8", "replace")
            if path not in files.get(name, ()):
                refuse.append(f"{name}: staged entry {path} is not a confirmed file")
    code = g.REFUSE if refuse else g.PASS
    return g.emit(SCRIPT, code, refuse, step="precheck",
                  files={k: sorted(v) for k, v in files.items()})


def diff_paths(repo, base):
    raw = g.git(repo["path"], "diff", "--name-status", "-z", "--no-renames", f"{base}..HEAD", binary=True)
    fields = [f for f in raw.split(b"\0") if f]
    return {fields[i + 1].decode("utf-8", "replace") for i in range(0, len(fields) - 1, 2)}


def tree_entry(repo, path):
    raw = g.git(repo["path"], "--literal-pathspecs", "ls-tree", "-z", "HEAD", "--", path, binary=True)
    entry = raw.split(b"\0", 1)[0]
    if not entry:
        return None
    meta = entry.split(b"\t", 1)[0].decode("ascii").split()
    return {"mode": meta[0], "blob": meta[2]}


def verify(args):
    team, item, repos, commit, text, snapshot = load(args)
    refuse, warnings, results = [], [], {}
    files = confirmed(item, repos)
    for repo in repos:
        name = repo["name"]
        base = input_sha(item, name)
        branch_ok(repo, refuse)
        head = g.git(repo["path"], "rev-parse", "HEAD")
        if head == base:
            if files.get(name):
                refuse.append(f"{name}: no new commit")
            continue
        ancestry = subprocess.run(["git", "-C", str(repo["path"]), "merge-base", "--is-ancestor", base, "HEAD"],
                                  capture_output=True)
        if ancestry.returncode == 1:
            refuse.append(f"{name}: HEAD {head[:12]} does not descend from input_sha {base[:12]}")
            continue
        if ancestry.returncode != 0:
            raise g.CannotTell(f"{name}: git merge-base failed: "
                               f"{ancestry.stderr.decode('utf-8', 'replace').strip()}")
        changed = diff_paths(repo, base)
        want = files.get(name, set())
        for extra in sorted(changed - want):
            refuse.append(f"{name}: commit changes unconfirmed {extra}")
        for missing in sorted(want - changed):
            refuse.append(f"{name}: confirmed {missing} is not in the commit")
        snap = snapshot_paths(snapshot, name)
        for path in sorted(want & changed):
            approved = (snap.get(path) or {}).get("worktree") or {}
            entry = tree_entry(repo, path)
            kind = approved.get("type")
            if kind == "absent":
                ok = entry is None
            elif kind == "file":
                ok = entry is not None and entry["blob"] == approved.get("blob")
            elif kind == "symlink":
                ok = entry is not None and entry["mode"] == "120000" and \
                    entry["blob"] == blob_of_symlink(repo, approved["target_b64"])
            else:
                ok = False
            if not ok:
                refuse.append(f"{name}: committed {path} differs from the approved content")
        for entry in db.scan_repo(repo):
            if entry["path"] in want:
                refuse.append(f"{name}: confirmed {entry['path']} is still dirty after the commit")
            elif db.in_lease(team, item, db.abs_path(repo["path"], entry)):
                warnings.append(f"{name}: {entry['path']} stays uncommitted in the lease")
        results[name] = {"sha": head, "files": sorted(want)}
    if refuse:
        return g.emit(SCRIPT, g.REFUSE, refuse, step="verify")
    baseline = None
    if args.record:
        entries = [e for repo in repos for e in db.scan_repo(repo)]
        out_dir = team.workspace(item["id"]) / "artifacts" / f"attempt-{item.get('attempt')}"
        baseline = out_dir / "post-commit-baseline.jsonl"
        db.write_entries(baseline, entries)
        approved_by = "user" if commit.get("approved_by") == "user" else "auto"
        for repo_rec in item.get("repositories") or []:
            if repo_rec.get("name") in results:
                repo_rec["result_sha"] = results[repo_rec["name"]]["sha"]
        log = team.state.setdefault("commit_log", [])
        for name, res in results.items():
            log.append({"assignment_id": item["id"], "repository": name, "sha": res["sha"],
                        "files": res["files"], "approved_by": approved_by, "at": g.now()})
        item["commit"]["status"] = "committed"
        item["post_commit_baseline"] = str(baseline)
        team.save_state()
    return g.emit(SCRIPT, g.PASS, warnings, step="verify", commits=results,
                  post_commit_baseline=str(baseline) if baseline else None, recorded=args.record)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("precheck", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--team-dir", required=True)
        p.add_argument("--assignment", required=True)
        if name == "verify":
            p.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)
    return g.run_gate(SCRIPT, lambda: precheck(args) if args.command == "precheck" else verify(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
