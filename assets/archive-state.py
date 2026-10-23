#!/usr/bin/env python3
"""Keep team-state.yaml small by moving settled history to state-archive.yaml.

Usage:
  archive-state.py archive <team_dir> [--keep N] [--remove-role NAME] [--dry-run]
  archive-state.py find <team_dir> <assignment-id>

archive moves every settled Assignment (succeeded/failed/cancelled, with
finished_at, no monitor, no open commit gate) and its commit_log lines out
of team-state.yaml, plus each answered pending_user question that no
deferred report still waits on. It also trims lead_history and each role's
role_history and rotations to the newest N entries (default 3).
--remove-role moves one role record out (Adjust "Remove a role").

state-archive.yaml is append-only: one YAML document per archived record.
The archive is written first and team-state.yaml is replaced last, by
temp file and rename. A rerun after a crash skips records that are
already in the archive. YAML comments in team-state.yaml are not kept.

find prints every record of one Assignment, live or archived, so the Lead
never has to read the whole archive. Exit 2 on a refused archive run.
"""
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

TERMINAL = {"succeeded", "failed", "cancelled"}
OPEN_COMMIT = {"awaiting_user", "approved"}
ACTIVE = {"running", "blocked"}
ARCHIVE_NAME = "state-archive.yaml"


class StringLoader(yaml.SafeLoader):
    """SafeLoader that keeps timestamps as the strings the Lead wrote."""


StringLoader.yaml_implicit_resolvers = {
    key: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load(text):
    return yaml.load(text, Loader=StringLoader)


def dump(data):
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(kind, record):
    raw = json.dumps([kind, record], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_archive(path):
    if not path.exists():
        return []
    return [doc for doc in yaml.load_all(path.read_text(encoding="utf-8"), Loader=StringLoader) if doc]


def settled(item, monitored):
    commit = item.get("commit") or {}
    return (item.get("assignment_status") in TERMINAL
            and item.get("finished_at")
            and item.get("id") not in monitored
            and not item.get("deferred")
            and commit.get("status") not in OPEN_COMMIT)


def trim(entries, keep):
    entries = entries or []
    cut = max(len(entries) - keep, 0)
    return entries[:cut], entries[cut:]


def plan(state, archived_ids, keep, remove_role):
    """Return (new_state, docs) without touching any file."""
    errors = []
    monitored = {m.get("assignment_id") for m in state.get("monitors") or []}
    docs = []

    kept, moved = [], []
    for item in state.get("assignments") or []:
        (moved if settled(item, monitored) else kept).append(item)
    moved_ids = {item.get("id") for item in moved} | archived_ids
    log_kept, log_moved = [], {}
    for line in state.get("commit_log") or []:
        if line.get("assignment_id") in moved_ids:
            log_moved.setdefault(line.get("assignment_id"), []).append(line)
        else:
            log_kept.append(line)
    for item in moved:
        docs.append(("assignment", dict(item, commit_log=log_moved.pop(item.get("id"), []))))
    for lines in log_moved.values():
        docs.extend(("commit_log", line) for line in lines)

    held = {(item.get("deferred") or {}).get("question") for item in kept}
    questions = []
    for entry in state.get("pending_user") or []:
        if entry.get("status") == "answered" and entry.get("id") not in held:
            docs.append(("pending_user", entry))
        else:
            questions.append(entry)

    old, lead_history = trim(state.get("lead_history"), keep)
    docs.extend(("lead_history", entry) for entry in old)

    roles = dict(state.get("roles") or {})
    for name, role in roles.items():
        role = dict(role or {})
        for field in ("role_history", "rotations"):
            if field not in role:
                continue
            old, role[field] = trim(role[field], keep)
            docs.extend((field, dict(entry, role=name)) for entry in old)
        roles[name] = role

    if remove_role:
        if remove_role not in roles:
            errors.append(f"role {remove_role} is not in team-state.yaml")
        busy = [a.get("id") for a in kept if a.get("assignee") == remove_role
                and (a.get("assignment_status") in ACTIVE or a.get("id") in monitored)]
        if busy:
            errors.append(f"role {remove_role} still holds active work: {', '.join(busy)}")
        if not errors:
            docs.append(("role_removed", dict(roles.pop(remove_role), role=remove_role)))

    new_state = dict(state)
    new_state["assignments"] = kept
    if "commit_log" in state:
        new_state["commit_log"] = log_kept
    if "lead_history" in state:
        new_state["lead_history"] = lead_history
    if "pending_user" in state:
        new_state["pending_user"] = questions
    new_state["roles"] = roles
    return new_state, docs, errors


def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def archive(team_dir, keep, remove_role, dry_run):
    state_path = team_dir / "team-state.yaml"
    archive_path = team_dir / ARCHIVE_NAME
    before = state_path.read_text(encoding="utf-8")
    state = load(before)
    errors = []
    if state.get("schema_version") != 2:
        errors.append(f"schema_version {state.get('schema_version')} is not 2; archive only v2 state")
    if Path(str(state.get("team_dir"))).resolve() != team_dir.resolve():
        errors.append(f"team_dir {state.get('team_dir')} does not match {team_dir}")
    if errors:
        return report_errors(errors)

    existing = read_archive(archive_path)
    archived_ids = {d["record"].get("id") for d in existing if d.get("kind") == "assignment"}
    seen = {d.get("digest") for d in existing}
    new_state, docs, errors = plan(state, archived_ids, keep, remove_role)
    if errors:
        return report_errors(errors)

    stamp = now()
    fresh = []
    for kind, record in docs:
        key = digest(kind, record)
        if key not in seen:
            fresh.append({"kind": kind, "archived_at": stamp, "digest": key, "record": record})
    counts = dict((state.get("archive") or {}).get("counts") or {})
    for doc in fresh:
        counts[doc["kind"]] = counts.get(doc["kind"], 0) + 1
    if docs:
        new_state["updated_at"] = stamp
        new_state["archive"] = {"path": str(archive_path), "last_archived_at": stamp, "counts": counts}
    after = dump(new_state)

    moved = [record.get("id") for kind, record in docs if kind == "assignment"]
    print(f"assignments archived: {', '.join(moved) or 'none'}")
    print(f"other records archived: {len(docs) - len(moved)}")
    print(f"already in archive, skipped: {len(docs) - len(fresh)}")
    print(f"team-state.yaml bytes: {len(before.encode())} -> "
          f"{len(after.encode()) if docs else len(before.encode())}")
    if dry_run or not docs:
        print("dry run: nothing written" if dry_run else "nothing to archive")
        return 0
    if fresh:
        with archive_path.open("a", encoding="utf-8") as handle:
            for doc in fresh:
                handle.write("---\n" + dump(doc))
            handle.flush()
            os.fsync(handle.fileno())
    atomic_write(state_path, after)
    return 0


def find(team_dir, assignment_id):
    state = load((team_dir / "team-state.yaml").read_text(encoding="utf-8"))
    hits = [{"source": "team-state.yaml", "record": item}
            for item in state.get("assignments") or [] if item.get("id") == assignment_id]
    hits += [{"source": ARCHIVE_NAME, "archived_at": doc.get("archived_at"), "record": doc["record"]}
             for doc in read_archive(team_dir / ARCHIVE_NAME)
             if doc.get("kind") == "assignment" and doc["record"].get("id") == assignment_id]
    if not hits:
        print(f"assignment {assignment_id} not found", file=sys.stderr)
        return 1
    sys.stdout.write(dump(hits))
    return 0


def report_errors(errors):
    print("team-state.yaml not archived:", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    return 2


def main(argv):
    args = argv[1:]
    if len(args) >= 2 and args[0] == "find" and len(args) == 3:
        return find(Path(args[1]), args[2])
    if len(args) >= 2 and args[0] == "archive":
        team_dir, rest = Path(args[1]), args[2:]
        keep, remove_role, dry_run = 3, None, False
        while rest:
            flag = rest.pop(0)
            if flag == "--dry-run":
                dry_run = True
            elif flag == "--keep" and rest and rest[0].isdigit():
                keep = int(rest.pop(0))
            elif flag == "--remove-role" and rest:
                remove_role = rest.pop(0)
            else:
                break
        else:
            return archive(team_dir, keep, remove_role, dry_run)
    print(__doc__.strip(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
