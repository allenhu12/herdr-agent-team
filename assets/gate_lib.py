"""Shared helpers for the gate scripts (dispatch-precheck, dirty-baseline,
commit-gate, inbox).

Every gate ends with exactly one JSON line on stdout and one exit code:
  0 pass, 1 refuse, 2 usage error, 3 cannot tell.
The Lead treats 3 like 1. Any unexpected error maps to 3, never to 0.

The rules these helpers enforce are defined in references/writer-rules.md
(paths, protected paths, single writer) and references/state-files.md
(team files). This module only reads and checks; callers decide what to write.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

PASS, REFUSE, USAGE, CANNOT_TELL = 0, 1, 2, 3
UNACKED = 4  # inbox.py only: delivered but never acknowledged
RESULT_WORD = {PASS: "pass", REFUSE: "refuse", USAGE: "usage", CANNOT_TELL: "cannot_tell", UNACKED: "unacked"}
ACTIVE = {"running", "blocked"}


class CannotTell(Exception):
    """Evidence is missing or unreadable; the gate must not pass."""


class StringLoader(yaml.SafeLoader):
    """SafeLoader that keeps timestamps as the strings the Lead wrote."""


StringLoader.yaml_implicit_resolvers = {
    key: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(script, code, reasons=(), **extra):
    """Print the one JSON result line and return the exit code."""
    line = {"script": script, "result": RESULT_WORD[code], "reasons": list(reasons)}
    line.update(extra)
    print(json.dumps(line, sort_keys=False, default=str))
    return code


def run_gate(script, body):
    """Run body() -> exit code; map every unexpected failure to 3."""
    try:
        return body()
    except CannotTell as exc:
        return emit(script, CANNOT_TELL, [str(exc)])
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - a gate never passes on a crash
        return emit(script, CANNOT_TELL, [f"unexpected error: {type(exc).__name__}: {exc}"])


# ---------------------------------------------------------------- team files

def load_yaml(path):
    try:
        data = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=StringLoader)
    except FileNotFoundError:
        raise CannotTell(f"missing file: {path}")
    except yaml.YAMLError as exc:
        raise CannotTell(f"unreadable YAML: {path}: {exc}")
    if not isinstance(data, dict):
        raise CannotTell(f"not a YAML mapping: {path}")
    return data


def dump_yaml(data):
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


def atomic_write(path, text):
    """Temp file in the same directory, then rename (state-files.md)."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class Team:
    """team.yaml + team-state.yaml for one team_dir, checked for agreement."""

    def __init__(self, team_dir):
        self.dir = Path(os.path.realpath(team_dir))
        self.team_path = self.dir / "team.yaml"
        self.state_path = self.dir / "team-state.yaml"
        self.team = load_yaml(self.team_path)
        self.state = load_yaml(self.state_path)
        for label, doc in (("team.yaml", self.team), ("team-state.yaml", self.state)):
            recorded = doc.get("team_dir")
            if not recorded or os.path.realpath(recorded) != str(self.dir):
                raise CannotTell(f"{label} team_dir {recorded!r} does not equal {self.dir}")

    def save_state(self):
        self.state["updated_at"] = now()
        atomic_write(self.state_path, dump_yaml(self.state))

    @property
    def project_root(self):
        return self.team.get("project_root") or self.state.get("project_root")

    def role(self, name):
        for role in self.team.get("roles") or []:
            if role.get("name") == name:
                return role
        return None

    def role_state(self, name):
        return (self.state.get("roles") or {}).get(name)

    def assignments(self):
        return self.state.get("assignments") or []

    def assignment(self, assignment_id):
        for item in self.assignments():
            if item.get("id") == assignment_id:
                return item
        return None

    def code_repos(self):
        return self.team.get("code_repos") or []

    def repo(self, name):
        for repo in self.code_repos():
            if repo.get("name") == name:
                return repo
        return None

    def workspace(self, assignment_id):
        return self.dir / "assignments" / assignment_id


def is_dispatched(item):
    """Active for busy and lease purposes (dispatch.md step 1)."""
    status = item.get("assignment_status")
    if status in ACTIVE:
        return True
    return status == "pending" and bool(item.get("dispatched_at") or lease_paths(item))


def lease_paths(item):
    lease = item.get("lease")
    if isinstance(lease, list):
        return [p for p in lease if isinstance(p, str)]
    if isinstance(lease, dict):
        return [p for p in lease.get("paths") or [] if isinstance(p, str)]
    return []


def lease_outputs(item):
    lease = item.get("lease")
    if isinstance(lease, dict):
        return [p for p in lease.get("outputs") or [] if isinstance(p, str)]
    return []


# ---------------------------------------------------------------- paths

def realpath(path):
    """Resolve .. and symlinks (writer-rules.md "Normalize every granted path")."""
    return os.path.realpath(os.path.expanduser(path))


def split_glob(pattern):
    """Return (literal_prefix, tail). The prefix is resolved; the tail keeps wildcards."""
    parts = pattern.split("/")
    for i, part in enumerate(parts):
        if any(ch in part for ch in "*?["):
            prefix = "/".join(parts[:i]) or "/"
            return realpath(prefix), "/".join(parts[i:])
    return realpath(pattern), ""


def normalize_glob(pattern):
    if not os.path.isabs(os.path.expanduser(pattern)):
        raise CannotTell(f"path is not absolute: {pattern}")
    prefix, tail = split_glob(pattern)
    return prefix if not tail else (prefix.rstrip("/") + "/" + tail)


def _glob_regex(pattern):
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def glob_match(pattern, path):
    """Match an absolute path against an absolute glob (`*`, `?`, `**`)."""
    return bool(_glob_regex(pattern).match(path))


def tree_root(pattern):
    """For `<dir>/**` return dir; for an exact path return None; else CannotTell."""
    prefix, tail = split_glob(pattern)
    if not tail:
        return None
    if tail == "**":
        return prefix
    raise CannotTell(f"unsupported glob form (use an exact path or <dir>/**): {pattern}")


def under(path, root):
    root = root.rstrip("/") or "/"
    return path == root or path.startswith(root + "/") or root == "/"


def glob_contains(outer, inner):
    """True when every path inner can name is also named by outer."""
    outer, inner = normalize_glob(outer), normalize_glob(inner)
    inner_root = tree_root(inner)
    if inner_root is None:
        return glob_match(outer, inner)
    outer_root = tree_root(outer)
    return outer_root is not None and under(inner_root, outer_root)


def globs_overlap(a, b):
    a_root, b_root = tree_root(a), tree_root(b)
    a_path, b_path = normalize_glob(a), normalize_glob(b)
    if a_root is None and b_root is None:
        return a_path == b_path
    if a_root is None:
        return under(a_path, b_root)
    if b_root is None:
        return under(b_path, a_root)
    return under(a_root, b_root) or under(b_root, a_root)


# ---------------------------------------------------------------- git

def git(repo, *args, check=True, binary=False):
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if check and proc.returncode != 0:
        raise CannotTell(f"git {' '.join(args)} failed in {repo}: "
                         f"{proc.stderr.decode('utf-8', 'replace').strip()}")
    if binary:
        return proc.stdout
    return proc.stdout.decode("utf-8", "surrogateescape").strip()


def logical_location(pattern):
    """Map an absolute path or glob to (repository identity, repo-relative form).

    Separate worktrees of one repository share the git common dir, so two
    grants in two worktrees compare by repository-relative path
    (writer-rules.md "Two-tier write authorization").
    """
    norm = normalize_glob(pattern)
    prefix, tail = split_glob(norm)
    probe = Path(prefix)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.is_file():
        probe = probe.parent
    proc = subprocess.run(["git", "-C", str(probe), "rev-parse", "--show-toplevel", "--git-common-dir"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return ("fs", norm)
    top, common = proc.stdout.strip().splitlines()[:2]
    top = realpath(top)
    # --git-common-dir may be printed relative to the directory git ran in.
    common = realpath(common if os.path.isabs(common) else os.path.join(str(probe), common))
    rel = os.path.relpath(prefix, top) if under(prefix, top) else prefix
    rel = "/" if rel == "." else "/" + rel
    rel = rel if not tail else rel.rstrip("/") + "/" + tail
    return (common, rel)


def logical_overlap(a, b):
    repo_a, rel_a = logical_location(a)
    repo_b, rel_b = logical_location(b)
    if repo_a != repo_b:
        return False
    return globs_overlap(rel_a, rel_b)


# ---------------------------------------------------------------- protected paths

def core_protected(team):
    team_dir = str(team.dir)
    root = realpath(team.project_root) if team.project_root else None
    locations = [f"{team_dir}/team.yaml", f"{team_dir}/team-state.yaml",
                 f"{team_dir}/state-archive.yaml", f"{team_dir}/role-tree.md",
                 f"{team_dir}/assignments/*/assignment.md", f"{team_dir}/inbox/**"]
    names = []
    if root:
        locations.append(f"{root}/00-current/**")
        names += [f"{root}/**/progress*.md", f"{root}/**/item-list.json"]
    for extra in team.team.get("protected_paths_extra") or []:
        extra = extra.replace("<team_dir>", team_dir)
        if root:
            extra = extra.replace("<project_root>", root)
        if "/**/" in extra and not extra.endswith("/**"):
            names.append(extra)
        else:
            locations.append(extra)
    return locations, names


def protected_conflicts(team, grant):
    """Reasons a grant touches a protected path; [] when it is clean."""
    grant = normalize_glob(grant)
    locations, names = core_protected(team)
    hits = []
    grant_root = tree_root(grant)
    for loc in locations:
        loc = normalize_glob(loc)
        loc_prefix, loc_tail = split_glob(loc)
        if grant_root is None:
            if glob_match(loc, grant):
                hits.append(f"grant {grant} names protected {loc}")
            continue
        if under(loc_prefix, grant_root):
            hits.append(f"grant {grant} contains protected {loc}")
        elif loc_tail == "**" and under(grant_root, loc_prefix):
            hits.append(f"grant {grant} lies inside protected {loc}")
        elif loc_tail and under(grant_root, loc_prefix):
            # A wildcard entry such as assignments/*/assignment.md: reject when
            # the grant's tree can hold a matching file, or when unclear.
            last = loc.rsplit("/", 1)[-1]
            if any(ch in last for ch in "*?[") or glob_match(loc, f"{grant_root}/{last}"):
                hits.append(f"grant {grant} can reach protected {loc}")
    if grant_root is None:
        for pattern in names:
            if glob_match(normalize_glob(pattern), grant):
                hits.append(f"grant {grant} matches protected name pattern {pattern}")
    return hits


def is_name_protected(team, path):
    _, names = core_protected(team)
    path = realpath(path)
    return any(glob_match(normalize_glob(p), path) for p in names)


# ---------------------------------------------------------------- herdr

def herdr_bin():
    return os.environ.get("HAT_HERDR_BIN", "herdr")


def herdr(*args, parse=True):
    try:
        proc = subprocess.run([herdr_bin(), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CannotTell(f"herdr {' '.join(args)} failed: {exc}")
    if not parse:
        if proc.returncode != 0:
            raise CannotTell(f"herdr {' '.join(args)} exit {proc.returncode}: {proc.stderr.strip()}")
        return proc.stdout
    try:
        data = json.loads(proc.stdout or proc.stderr or "{}")
    except json.JSONDecodeError:
        raise CannotTell(f"herdr {' '.join(args)} printed no JSON")
    return proc.returncode, data


def agent_info(name):
    """The live agent record, or None when Herdr says the agent is gone."""
    code, data = herdr("agent", "get", name)
    error = (data.get("error") or {}).get("code")
    if error == "agent_not_found":
        return None
    if code != 0 or error:
        raise CannotTell(f"herdr agent get {name}: {data.get('error') or code}")
    agent = ((data.get("result") or {}).get("agent")) or {}
    if not agent:
        raise CannotTell(f"herdr agent get {name} returned no agent")
    return agent


def agent_state(info):
    return "gone" if info is None else (info.get("agent_status") or "unknown")


def identity_mismatch(name, rec, info):
    """Compare a live Herdr agent record with the recorded identity.

    Returns (mismatches, missing): mismatches prove another process or place;
    missing means the evidence cannot be compared. Fields: pane_id, kind
    (Herdr's `agent`), cwd (real paths), and process identity (Herdr's
    agent_session value vs process_identity.agent_session_id). See
    identity-and-launch.md "Inventory and ownership".
    """
    mismatches, missing = [], []
    rec = rec or {}
    if info is None:
        return [f"{name}: no live agent"], []
    pairs = (("pane_id", info.get("pane_id"), rec.get("pane_id")),
             ("kind", info.get("agent"), rec.get("kind")))
    for label, live, recorded in pairs:
        if live is None or recorded is None:
            missing.append(f"{name}: {label} missing (live={live!r}, recorded={recorded!r})")
        elif live != recorded:
            mismatches.append(f"{name}: {label} {live!r} differs from recorded {recorded!r}")
    live_cwd, rec_cwd = info.get("cwd"), rec.get("cwd")
    if not live_cwd or not rec_cwd:
        missing.append(f"{name}: cwd missing (live={live_cwd!r}, recorded={rec_cwd!r})")
    elif realpath(live_cwd) != realpath(rec_cwd):
        mismatches.append(f"{name}: cwd {live_cwd} differs from recorded {rec_cwd}")
    session = (info.get("agent_session") or {}).get("value")
    recorded_session = (rec.get("process_identity") or {}).get("agent_session_id")
    if recorded_session is None or session is None:
        missing.append(f"{name}: process identity not comparable "
                       f"(live={session!r}, recorded={recorded_session!r})")
    elif session != recorded_session:
        mismatches.append(f"{name}: process changed ({session} != {recorded_session})")
    return mismatches, missing


def die_usage(parser, message):
    parser.print_usage(sys.stderr)
    print(message, file=sys.stderr)
    raise SystemExit(USAGE)
