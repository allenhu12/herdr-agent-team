#!/usr/bin/env python3
"""Record and compare a shared-mode checkout's dirty state.

Usage:
  dirty-baseline.py capture --team-dir <abs> --assignment <id> --attempt <n> [--record]
  dirty-baseline.py compare --team-dir <abs> --assignment <id> --attempt <n>
                            --mode accept|tester-pre|tester-post [--record]

capture (dispatch.md step 2a) reads the Assignment record's `lease` and
`repositories` (or the code_repos its lease reaches) and writes
  <workspace>/artifacts/attempt-<n>/dirty-baseline.jsonl
  <workspace>/artifacts/attempt-<n>/snapshots/<repo>/<path>
--record also sets the record's repositories[].input_sha, dirty_baseline
and dirty_at_dispatch. An existing baseline for the same attempt is never
overwritten; an identical rerun passes.

compare --mode accept (acceptance.md, shared mode) checks HEAD == input_sha,
every changed path is inside the lease, and nothing outside it moved. On a
pass it writes accept-snapshot.json and prints its digest; --record stores
commit.accept_snapshot and commit.accept_digest for the commit gate.
--mode tester-pre / tester-post check HEAD == the last accepted commit and
the dirty state equals the baseline, apart from the lease's declared outputs.

Baseline format: one JSON object per line. Paths are kept as base64 of
their raw bytes (`path_b64`) so any file name survives; `path` is display
only. Each entry has repo, xy, path_b64, path, orig_path_b64, worktree
{type: file|symlink|dir|absent, blob|target} and index {mode, blob} or null.

Legacy baselines: an Assignment dispatched before 4.3.0 recorded
dirty-baseline.tsv (repo, path, status, worktree hash or `deleted` or a
word such as `nested-repo`, index blob or `none`). read_entries reads it
into the same entry shape marked `legacy: true`; comparisons against a
legacy entry use the index blob only (the TSV has no mode) and treat a
non-hash worktree word as a directory. dirty_at_dispatch records without
path_b64 are matched by path. An Assignment accepted by hand before 4.3.0
runs `compare --mode accept --record` once to get its accept snapshot
before the commit gate.

Exit: 0 pass, 1 refuse, 2 usage, 3 cannot tell.
"""
import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True

import gate_lib as g  # noqa: E402

SCRIPT = "dirty-baseline"


# ---------------------------------------------------------------- scanning

def b64(raw):
    return base64.b64encode(raw).decode("ascii")


def unb64(text):
    return base64.b64decode(text.encode("ascii"))


def parse_porcelain(raw):
    """Parse `git status --porcelain=v1 -z` into (xy, path bytes, orig bytes|None)."""
    fields = raw.split(b"\0")
    out, i = [], 0
    while i < len(fields):
        item = fields[i]
        i += 1
        if not item:
            continue
        xy, path = item[:2].decode("ascii"), item[3:]
        orig = None
        if "R" in xy or "C" in xy:
            orig = fields[i]
            i += 1
        out.append((xy, path, orig))
    return out


def worktree_record(repo_path, rel):
    full = os.path.join(repo_path, os.fsdecode(rel))
    if not os.path.lexists(full):
        return {"type": "absent"}
    if os.path.islink(full):
        return {"type": "symlink", "target_b64": b64(os.fsencode(os.readlink(full)))}
    if os.path.isdir(full):
        return {"type": "dir"}
    blob = g.git(repo_path, "--literal-pathspecs", "hash-object", "--", os.fsdecode(rel))
    return {"type": "file", "blob": blob}


def index_record(repo_path, rel):
    raw = g.git(repo_path, "--literal-pathspecs", "ls-files", "-s", "-z", "--", os.fsdecode(rel), binary=True)
    entry = raw.split(b"\0", 1)[0]
    if not entry:
        return None
    meta = entry.split(b"\t", 1)[0].decode("ascii").split()
    return {"mode": meta[0], "blob": meta[1]}


def scan_repo(repo):
    """Current dirty entries of one code repository."""
    path = repo["path"]
    raw = g.git(path, "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True)
    entries = []
    for xy, rel, orig in parse_porcelain(raw):
        entries.append({
            "repo": repo["name"], "xy": xy, "path_b64": b64(rel),
            "path": rel.decode("utf-8", "replace"),
            "orig_path_b64": b64(orig) if orig is not None else None,
            "worktree": worktree_record(path, rel), "index": index_record(path, rel)})
        if orig is not None:
            # The rename source keeps its own index/worktree state too.
            entries.append({
                "repo": repo["name"], "xy": "R-", "path_b64": b64(orig),
                "path": orig.decode("utf-8", "replace"), "orig_path_b64": None,
                "worktree": worktree_record(path, orig), "index": index_record(path, orig)})
    return entries


def write_entries(path, entries):
    text = "".join(json.dumps(e, sort_keys=True) + "\n" for e in entries)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    g.atomic_write(path, text)
    return text


HEX40 = set("0123456789abcdef")


def legacy_worktree(token):
    if token == "deleted":
        return {"type": "absent"}
    if len(token) in (40, 64) and set(token) <= HEX40:
        return {"type": "file", "blob": token}
    return {"type": "dir"}  # nested-repo and other non-file words from 4.2.0


def read_legacy_tsv(lines, path):
    entries = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != 5:
            raise g.CannotTell(f"unreadable legacy baseline {path}:{number}: expected 5 tab-separated fields")
        repo, rel, xy, work, index = fields
        entries.append({
            "repo": repo, "xy": xy, "path_b64": b64(rel.encode("utf-8")), "path": rel,
            "orig_path_b64": None, "worktree": legacy_worktree(work),
            "index": None if index in ("none", "") else {"mode": None, "blob": index}, "legacy": True})
    return entries


def read_entries(path):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise g.CannotTell(f"missing baseline: {path}")
    if str(path).endswith(".tsv"):
        return read_legacy_tsv(lines, path)
    try:
        return [json.loads(line) for line in lines if line.strip()]
    except json.JSONDecodeError as exc:
        raise g.CannotTell(f"unreadable baseline {path}: {exc}")


def abs_path(repo_path, entry):
    return os.path.join(g.realpath(repo_path), os.fsdecode(unb64(entry["path_b64"])))


def state_key(entry, legacy=False):
    index = entry["index"]
    if legacy and index is not None:
        index = {"blob": index.get("blob")}  # the 4.2.0 TSV recorded no mode
    return (entry["xy"].strip() if legacy else entry["xy"], json.dumps(entry["worktree"], sort_keys=True),
            json.dumps(index, sort_keys=True))


def changes(baseline, current):
    """Paths whose dirty state differs: new, changed, or no longer dirty."""
    before = {e["path_b64"]: e for e in baseline}
    after = {e["path_b64"]: e for e in current}
    out = []
    for key in sorted(set(before) | set(after)):
        a, b = before.get(key), after.get(key)
        legacy = bool(a and a.get("legacy"))
        if a is None or b is None or state_key(a, legacy) != state_key(b, legacy):
            out.append((key, a, b))
    return out


def baseline_drift(baseline, current, repo_path, allowed_outputs):
    """Reasons the current state differs from a baseline, outputs excepted."""
    reasons = []
    for key, before, after in changes(baseline, current):
        entry = after or before
        full = abs_path(repo_path, entry)
        if any(g.glob_contains(o, full) for o in allowed_outputs):
            continue
        what = "new dirty path" if before is None else ("no longer dirty" if after is None else "changed")
        reasons.append(f"{entry['path']}: {what} since the baseline")
    return reasons


# ---------------------------------------------------------------- records

def touched_repos(team, item):
    names = [r.get("name") for r in item.get("repositories") or []]
    if not names:
        for repo in team.code_repos():
            root = g.realpath(repo["path"])
            for grant in g.lease_paths(item) + g.lease_outputs(item):
                prefix, _ = g.split_glob(g.normalize_glob(grant))
                if g.under(prefix, root) or g.under(root, prefix):
                    names.append(repo["name"])
                    break
    repos = []
    for name in names:
        repo = team.repo(name)
        if repo is None:
            raise g.CannotTell(f"repository {name} is not in team.yaml code_repos")
        repos.append(repo)
    return repos


def in_lease(team, item, full):
    if g.is_name_protected(team, full):
        return False
    return any(g.glob_contains(p, full) for p in g.lease_paths(item))


def in_outputs(item, full):
    return any(g.glob_contains(p, full) for p in g.lease_outputs(item))


def attempt_dir(team, item, attempt):
    return team.workspace(item["id"]) / "artifacts" / f"attempt-{attempt}"


def load_item(team, args):
    item = team.assignment(args.assignment)
    if item is None:
        raise g.CannotTell(f"Assignment {args.assignment} is not in team-state.yaml")
    if int(item.get("attempt") or 0) != args.attempt:
        raise g.CannotTell(f"Assignment {args.assignment} is at attempt {item.get('attempt')}, "
                           f"not {args.attempt}")
    return item


def digest_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- capture

def capture(args):
    team = g.Team(args.team_dir)
    item = load_item(team, args)
    repos = touched_repos(team, item)
    if not repos:
        return g.emit(SCRIPT, g.PASS, ["no code repository in this Assignment's scope"],
                      dirty_baseline=None)
    refuse = []
    heads, entries = {}, []
    recorded = {r.get("name"): r for r in item.get("repositories") or []}
    for repo in repos:
        head = g.git(repo["path"], "rev-parse", "HEAD")
        heads[repo["name"]] = head
        prior = (recorded.get(repo["name"]) or {}).get("input_sha")
        if prior and prior != head:
            refuse.append(f"{repo['name']}: HEAD {head[:12]} moved from input_sha {prior[:12]}; "
                          "run the late-signal procedure")
        entries.extend(scan_repo(repo))
    if refuse:
        return g.emit(SCRIPT, g.REFUSE, refuse)
    out_dir = attempt_dir(team, item, args.attempt)
    baseline_path = out_dir / "dirty-baseline.jsonl"
    text = "".join(json.dumps(e, sort_keys=True) + "\n" for e in entries)
    if baseline_path.exists():
        if baseline_path.read_text(encoding="utf-8") != text:
            return g.emit(SCRIPT, g.REFUSE, [f"{baseline_path} already holds a different baseline; "
                                             "frozen evidence is never overwritten"])
    else:
        write_entries(baseline_path, entries)
    dirty_at_dispatch = []
    for entry in entries:
        repo = team.repo(entry["repo"])
        full = abs_path(repo["path"], entry)
        if not in_lease(team, item, full) or entry["worktree"]["type"] not in ("file", "symlink"):
            continue
        record = {"repo": entry["repo"], "path": entry["path"], "path_b64": entry["path_b64"]}
        if entry["worktree"]["type"] == "file":
            snap = out_dir / "snapshots" / entry["repo"] / os.fsdecode(unb64(entry["path_b64"]))
            if not snap.exists():
                snap.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(full, snap, follow_symlinks=False)
            record["snapshot"] = str(snap)
        else:
            record["symlink_target_b64"] = entry["worktree"]["target_b64"]
        dirty_at_dispatch.append(record)
    if args.record:
        item["repositories"] = [
            {"name": n, "input_sha": h, "result_sha": (recorded.get(n) or {}).get("result_sha")}
            for n, h in heads.items()]
        item["dirty_baseline"] = str(baseline_path)
        item["dirty_at_dispatch"] = dirty_at_dispatch
        team.save_state()
    return g.emit(SCRIPT, g.PASS, [], dirty_baseline=str(baseline_path), input_sha=heads,
                  dirty_at_dispatch=[d["path"] for d in dirty_at_dispatch], recorded=args.record)


# ---------------------------------------------------------------- compare

def last_accepted(team, repo_name):
    entries = [c for c in team.state.get("commit_log") or [] if c.get("repository") == repo_name]
    return entries[-1].get("sha") if entries else None


def compare(args):
    team = g.Team(args.team_dir)
    item = load_item(team, args)
    repos = touched_repos(team, item)
    if not item.get("dirty_baseline"):
        raise g.CannotTell(f"Assignment {item['id']} has no dirty_baseline; run capture first")
    baseline = read_entries(item["dirty_baseline"])
    refuse = []
    recorded = {r.get("name"): r for r in item.get("repositories") or []}
    current_all = []
    for repo in repos:
        head = g.git(repo["path"], "rev-parse", "HEAD")
        if args.mode == "accept":
            want = (recorded.get(repo["name"]) or {}).get("input_sha")
            label = "input_sha"
        else:
            want = last_accepted(team, repo["name"])
            label = "last accepted commit"
        if not want:
            raise g.CannotTell(f"{repo['name']}: no {label} recorded")
        if head != want:
            refuse.append(f"{repo['name']}: HEAD {head[:12]} differs from {label} {want[:12]}")
        current_all.extend(scan_repo(repo))
    if args.mode in ("tester-pre", "tester-post"):
        outputs = g.lease_outputs(item) if args.mode == "tester-post" else []
        for repo in repos:
            base = [e for e in baseline if e["repo"] == repo["name"]]
            cur = [e for e in current_all if e["repo"] == repo["name"]]
            refuse.extend(f"{repo['name']}: {r}" for r in baseline_drift(base, cur, repo["path"], outputs))
        code = g.REFUSE if refuse else g.PASS
        return g.emit(SCRIPT, code, refuse, mode=args.mode)

    snapshot = {"assignment": item["id"], "attempt": args.attempt, "repos": {}}
    changed = {}
    snaps = {(d.get("repo"), d.get("path_b64") or b64(str(d.get("path", "")).encode("utf-8"))): d
             for d in item.get("dirty_at_dispatch") or []}
    for repo in repos:
        base = [e for e in baseline if e["repo"] == repo["name"]]
        cur = [e for e in current_all if e["repo"] == repo["name"]]
        paths = []
        for key, before, after in changes(base, cur):
            entry = after or before
            full = abs_path(repo["path"], entry)
            if in_outputs(item, full):
                continue
            if not in_lease(team, item, full):
                refuse.append(f"{repo['name']}: out-of-scope write {entry['path']}; escalate to the User")
                continue
            prior = snaps.get((repo["name"], key))
            paths.append({
                "path": entry["path"], "path_b64": key,
                "worktree": after["worktree"] if after else worktree_record(repo["path"], unb64(key)),
                "diff_base": prior.get("snapshot") if prior else f"{recorded[repo['name']]['input_sha']}",
                "dirty_at_dispatch": bool(prior)})
        snapshot["repos"][repo["name"]] = {"head": (recorded.get(repo["name"]) or {}).get("input_sha"),
                                           "paths": paths}
        changed[repo["name"]] = [p["path"] for p in paths]
    if refuse:
        return g.emit(SCRIPT, g.REFUSE, refuse, mode="accept", changed=changed)
    text = json.dumps(snapshot, sort_keys=True, indent=2) + "\n"
    snap_path = attempt_dir(team, item, args.attempt) / "accept-snapshot.json"
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    g.atomic_write(snap_path, text)
    digest = digest_text(text)
    if args.record:
        commit = item.setdefault("commit", {})
        commit["accept_snapshot"] = str(snap_path)
        commit["accept_digest"] = digest
        team.save_state()
    return g.emit(SCRIPT, g.PASS, [], mode="accept", changed=changed,
                  accept_snapshot=str(snap_path), accept_digest=digest, recorded=args.record)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("capture", "compare"):
        p = sub.add_parser(name)
        p.add_argument("--team-dir", required=True)
        p.add_argument("--assignment", required=True)
        p.add_argument("--attempt", required=True, type=int)
        p.add_argument("--record", action="store_true")
        if name == "compare":
            p.add_argument("--mode", required=True, choices=("accept", "tester-pre", "tester-post"))
    args = parser.parse_args(argv)
    return g.run_gate(SCRIPT, lambda: capture(args) if args.command == "capture" else compare(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
