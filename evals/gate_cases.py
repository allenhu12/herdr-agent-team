"""Offline cases for the gate scripts. Called by check_package.py.

Each case builds a throwaway team in a temp directory: a real git repository,
team.yaml, team-state.yaml, and a fake herdr (fixtures/gates/fake-herdr.py).
No Herdr server and no agent is used.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
FAKE = ROOT / "evals/fixtures/gates/fake-herdr.py"
SESSION = "sess-impl-1"


def sh(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


class Fixture:
    def __init__(self, tmp, mode="shared"):
        self.tmp = Path(os.path.realpath(tmp))
        self.repo = self.tmp / "app"
        self.repo.mkdir()
        sh("git", "init", "-q", "-b", "main", str(self.repo))
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "src").mkdir()
        (self.repo / "src/a.txt").write_text("a\n")
        (self.repo / "src/b.txt").write_text("b\n")
        (self.repo / "docs").mkdir()
        (self.repo / "docs/readme.md").write_text("r\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        self.base = git(self.repo, "rev-parse", "HEAD")
        self.team_dir = self.tmp / ".herdr-agent-team"
        self.team_dir.mkdir()
        self.herdr_state = self.tmp / "herdr.json"
        self.team = {
            "schema_version": 2, "template": False, "team_dir": str(self.team_dir),
            "project_root": str(self.tmp), "checkout_mode": mode,
            "code_repos": [{"name": "app", "path": str(self.repo), "base_branch": "main", "rules_file": None}],
            "protected_paths_extra": [], "permissions": "inherit",
            "roles": [
                {"name": "t-impl-sol", "kind": "codex", "access": "writer", "checkout_dir": str(self.repo),
                 "write_ceiling": [f"{self.repo}/**"], "steering": "prompt"},
                {"name": "t-test-luna", "kind": "codex", "access": "writer", "checkout_dir": str(self.tmp),
                 "write_ceiling": [f"{self.repo}/build/**"], "steering": "prompt"},
            ]}
        self.state = {
            "schema_version": 2, "team_dir": str(self.team_dir), "project_root": str(self.tmp),
            "roles": {
                "t-impl-sol": self.role_rec("w1:p2", str(self.repo), SESSION),
                "t-test-luna": self.role_rec("w1:p3", str(self.tmp), "sess-test-1"),
            },
            "assignments": [], "monitors": [], "commit_log": [],
            "commit_approval": {"mode": "ask", "granted_by_words": None, "granted_at": None}}
        self.agents = {
            "t-impl-sol": self.agent("w1:p2", str(self.repo), SESSION),
            "t-test-luna": self.agent("w1:p3", str(self.tmp), "sess-test-1"),
        }
        self.save()

    @staticmethod
    def role_rec(pane, cwd, session):
        return {"pane_id": pane, "kind": "codex", "cwd": cwd,
                "process_identity": {"agent_session_id": session},
                "launch_verification": {"process_identity": {"agent_session_id": session},
                                        "model_footer_text": "gpt-5.6-sol high"}}

    @staticmethod
    def agent(pane, cwd, session, status="idle"):
        return {"agent": {"agent": "codex", "agent_status": status, "pane_id": pane, "cwd": cwd,
                          "agent_session": {"value": session}},
                "screen": "gpt-5.6-sol high · 80% left"}

    def save(self):
        (self.team_dir / "team.yaml").write_text(yaml.safe_dump(self.team, sort_keys=False))
        (self.team_dir / "team-state.yaml").write_text(yaml.safe_dump(self.state, sort_keys=False))
        self.herdr_state.write_text(json.dumps({"agents": self.agents, "log": []}))

    def reload(self):
        self.state = yaml.safe_load((self.team_dir / "team-state.yaml").read_text())
        return self.state

    def env(self):
        env = dict(os.environ)
        env["HAT_HERDR_BIN"] = str(FAKE)
        env["HAT_FAKE_HERDR_STATE"] = str(self.herdr_state)
        return env

    def run(self, script, *args):
        proc = subprocess.run([sys.executable, str(ASSETS / script), *args], capture_output=True,
                              text=True, env=self.env())
        try:
            line = json.loads(proc.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            line = {"raw": proc.stdout, "stderr": proc.stderr}
        return proc.returncode, line

    def precheck(self, role="t-impl-sol", kind="source", scope=None, assignment="a1", extra=()):
        args = ["--team-dir", str(self.team_dir), "--role", role, "--assignment", assignment,
                "--attempt", "1", "--kind", kind]
        for s in (scope if scope is not None else [f"{self.repo}/src/**"]):
            args += ["--scope", s]
        return self.run("dispatch-precheck.py", *args, *extra)

    def add_assignment(self, aid="a1", assignee="t-impl-sol", kind="source", status="running",
                       paths=None, outputs=None, attempt=1):
        item = {"id": aid, "attempt": attempt, "assignee": assignee, "kind": kind,
                "assignment_status": status, "dispatched_at": "2026-10-24T00:00:00Z",
                "checkout_dir": self.team["roles"][0]["checkout_dir"],
                "lease": {"paths": paths if paths is not None else [f"{self.repo}/src/**"],
                          "outputs": outputs or []}}
        self.state["assignments"].append(item)
        self.save()
        return item

    def db(self, *args):
        return self.run("dirty-baseline.py", *args)

    def gate(self, *args):
        return self.run("commit-gate.py", *args)


def precheck_cases(check):
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        rc, out = f.precheck()
        check("precheck passes an idle verified role inside its ceiling", rc == 0, out)
        check("precheck prints a JSON result line", out.get("script") == "dispatch-precheck", out)

        f.add_assignment("other", status="running")
        rc, out = f.precheck(assignment="a2")
        check("precheck refuses a role holding an active Assignment",
              rc == 1 and any("active Assignment other" in r for r in out["reasons"]), out)
        f.state["assignments"] = []
        f.save()

        for status, want in (("working", 1), ("blocked", 1), ("unknown", 3)):
            f.agents["t-impl-sol"]["agent"]["agent_status"] = status
            f.save()
            rc, out = f.precheck()
            check(f"precheck maps live {status} to exit {want}", rc == want, out)
        f.agents["t-impl-sol"]["agent"]["agent_status"] = "idle"
        gone = f.agents.pop("t-impl-sol")
        f.save()
        rc, out = f.precheck()
        check("precheck refuses a gone role", rc == 1 and any("gone" in r for r in out["reasons"]), out)
        f.agents["t-impl-sol"] = gone

        f.agents["t-impl-sol"]["screen"] = "gpt-6-luna medium"
        f.save()
        rc, out = f.precheck()
        check("precheck cannot tell when the recorded footer is not on screen", rc == 3, out)
        f.agents["t-impl-sol"]["screen"] = "gpt-5.6-sol high"

        f.agents["t-impl-sol"]["agent"]["agent_session"]["value"] = "sess-other"
        f.save()
        rc, out = f.precheck()
        check("precheck refuses a changed process identity",
              rc == 1 and any("process changed" in r for r in out["reasons"]), out)
        f.agents["t-impl-sol"]["agent"]["agent_session"]["value"] = SESSION
        f.agents["t-impl-sol"]["agent"].pop("cwd")
        f.save()
        rc, out = f.precheck()
        check("precheck cannot tell when Herdr omits cwd", rc == 3, out)
        f.agents["t-impl-sol"]["agent"]["cwd"] = str(f.repo)
        f.save()

        rc, out = f.precheck(scope=[f"{f.repo}/src/../../escape/**"])
        check("precheck refuses a .. escape from the ceiling",
              rc == 1 and any("outside" in r for r in out["reasons"]), out)
        os.symlink(f.tmp, f.repo / "src" / "link")
        rc, out = f.precheck(scope=[f"{f.repo}/src/link/**"])
        check("precheck refuses a symlink escape from the ceiling", rc == 1, out)
        os.unlink(f.repo / "src" / "link")

        f.team["roles"][0]["write_ceiling"] = [f"{f.tmp}/**"]
        f.save()
        for target in (f"{f.team_dir}/team-state.yaml", f"{f.team_dir}/assignments/a1/assignment.md",
                       f"{f.tmp}/notes/progress-1.md", f"{f.team_dir}/**"):
            rc, out = f.precheck(scope=[target])
            check(f"precheck refuses protected grant {Path(target).name}",
                  rc == 1 and any("protected" in r for r in out["reasons"]), out)
        rc, out = f.precheck(scope=[f"{f.team_dir}/assignments/a1/artifacts/**"])
        check("precheck allows an artifacts grant that cannot reach assignment.md", rc == 0, out)
        f.team["roles"][0]["write_ceiling"] = [f"{f.repo}/**"]
        f.save()

        wt = f.tmp / "wt"
        git(f.repo, "worktree", "add", "-q", str(wt), "-b", "side")
        f.team["checkout_mode"] = "isolated"
        f.team["roles"][1]["write_ceiling"] = [f"{wt}/**"]
        f.team["roles"][1]["checkout_dir"] = str(wt)
        f.state["roles"]["t-test-luna"]["cwd"] = str(wt)
        f.agents["t-test-luna"]["agent"]["cwd"] = str(wt)
        f.save()
        f.add_assignment("other", assignee="t-impl-sol", paths=[f"{f.repo}/src/a.txt"])
        rc, out = f.precheck(role="t-test-luna", scope=[f"{wt}/src/**"], assignment="a2")
        check("precheck refuses a lease overlap across worktrees by repo-relative path",
              rc == 1 and any("overlaps" in r for r in out["reasons"]), out)
        rc, out = f.precheck(role="t-test-luna", scope=[f"{wt}/docs/**"], assignment="a2")
        check("precheck allows disjoint repo-relative leases", rc == 0, out)

    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        f.state["assignments"].append({"id": "a1", "attempt": 1, "assignee": "t-impl-sol",
                                       "assignment_status": "pending", "dispatched_at": None})
        f.save()
        rc, out = f.precheck()
        check("precheck allows a queued pending record", rc == 0, out)
        f.state["assignments"][0].update({"dispatched_at": "x", "lease": None})
        f.save()
        rc, out = f.precheck(extra=["--rework"])
        check("precheck allows a stopped rework of the same Assignment", rc == 0, out)
        rc, out = f.precheck()
        check("precheck refuses the same pending record without --rework", rc == 1, out)

        f.state["assignments"] = []
        f.add_assignment("t1", assignee="t-test-luna", kind="tester", paths=[],
                         outputs=[f"{f.repo}/build/**"])
        rc, out = f.precheck(assignment="a2")
        check("precheck refuses source work while a tester window is open",
              rc == 1 and any("tester window" in r for r in out["reasons"]), out)
        f.state["assignments"] = []
        f.save()
        rc, out = f.precheck(role="t-test-luna", kind="tester", scope=[], assignment="t1",
                             extra=["--output", f"{f.repo}/build/**"])
        check("tester gate refuses a HEAD with no commit_log entry",
              rc == 1 and any("commit_log" in r for r in out["reasons"]), out)


def context_cases(check):
    root_a, root_b = "/tmp", "/usr"
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        role = f.team["roles"][1]
        role["context_roots"] = [root_a]
        rec = f.state["roles"]["t-test-luna"]
        f.save()
        args = dict(role="t-test-luna", kind="reader", scope=[])
        rc, out = f.precheck(**args)
        check("context gate: no read refuses", rc == 1 and "no context read" in str(out), out)
        rec["context_read"] = {"session": "old-session", "roots": [root_a]}
        f.save()
        rc, out = f.precheck(**args)
        check("context gate: another session refuses", rc == 1 and "another session" in str(out), out)
        rec["context_read"] = {"session": "sess-test-1", "roots": [root_b]}
        f.save()
        rc, out = f.precheck(**args)
        check("context gate: other roots refuse", rc == 1 and "other roots" in str(out), out)
        rec["context_read"] = {"session": "sess-test-1"}
        f.save()
        rc, out = f.precheck(**args)
        check("context gate: legacy record without roots refuses", rc == 1, out)
        rec["context_read"] = {"session": "sess-test-1", "roots": [root_a]}
        f.save()
        rc, out = f.precheck(**args)
        check("context gate: same session passes", rc == 0, out)
        del f.agents["t-test-luna"]["agent"]["agent_session"]
        rec["process_identity"] = {}
        rec["launch_verification"]["process_identity"] = {}
        f.save()
        rc, out = f.precheck(**args)
        check("context gate: no session id is cannot tell", rc == 3 and "no live session id" in str(out), out)
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        rc, out = f.precheck(role="t-test-luna", kind="reader", scope=[])
        check("context gate: role with no roots is unchanged", rc == 0, out)
    send = lambda f: f.run("context-read.py", "send", "--team-dir", str(f.team_dir), "--role", "t-test-luna",
                           "--timeout", "0.3", "--poll", "0.05")
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        f.team["roles"][1]["context_roots"] = [root_a]
        f.agents["t-test-luna"]["on_prompt"] = {"echo": True}
        f.save()
        rc, out = send(f)
        check("context read: prompt echo alone records nothing",
              rc == 3 and "context_read" not in f.reload()["roles"]["t-test-luna"], out)
        f.agents["t-test-luna"]["on_prompt"] = {"echo": True, "context_reply": True}
        f.save()
        rc, out = send(f)
        got = f.reload()["roles"]["t-test-luna"].get("context_read") or {}
        check("context read: a real reply records session and roots",
              rc == 0 and got.get("session") == "sess-test-1" and got.get("roots") == [root_a], out)
        rc, out = f.precheck(role="t-test-luna", kind="reader", scope=[])
        check("context read: then the gate passes", rc == 0, out)
        f.agents["t-test-luna"]["agent"]["agent_status"] = "working"
        f.save()
        rc, out = send(f)
        check("context read: a busy role is refused", rc == 1 and "idle role" in str(out), out)
        f.agents["t-test-luna"]["agent"]["agent_status"] = "idle"
        f.agents["t-test-luna"]["agent"]["agent_session"] = {"value": "sess-other"}
        f.save()
        rc, out = send(f)
        check("context read: unsaved new identity is refused", rc == 1 and "save the verified" in str(out), out)
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        f.team["roles"][1]["context_roots"] = [root_a]
        del f.agents["t-test-luna"]["agent"]["agent_session"]
        f.save()
        rc, out = send(f)
        log = json.loads(f.herdr_state.read_text()).get("log")
        check("context read: no session id sends nothing and records nothing",
              rc == 3 and not log and "context_read" not in f.reload()["roles"]["t-test-luna"], (out, log))
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        f.team["roles"][1]["context_roots"] = [root_a]
        later = yaml.safe_load(yaml.safe_dump(f.state))
        later["assignments"].append({"id": "later", "assignee": "t-impl-sol"})
        f.agents["t-test-luna"]["on_prompt"] = {
            "context_reply": True,
            "write": {"path": str(f.team_dir / "team-state.yaml"), "text": yaml.safe_dump(later)}}
        f.save()
        rc, out = send(f)
        got = f.reload()
        check("context read: a state write during the read is kept",
              rc == 0 and [a["id"] for a in got["assignments"]] == ["later"]
              and got["roles"]["t-test-luna"].get("context_read"), out)


def context_reply_cases(check):
    spec = importlib.util.spec_from_file_location("context_read", ASSETS / "context-read.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    prompt = mod.prompt_text(["/r"], "abc123")
    check("context read: the prompt text is not a reply", not mod.answered(prompt, "abc123"))
    check("context read: spaces around the hyphen count", mod.answered("x\n• CONTEXT-OK - abc123\ny", "abc123"))
    check("context read: another code does not count", not mod.answered("• CONTEXT-OK-abc124", "abc123"))


def rename_archive_cases(check):
    def tester(f):
        return f.precheck(role="t-test-luna", kind="tester", scope=[], assignment="t1")
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        head = git(f.repo, "rev-parse", "HEAD")
        f.state["assignments"].append({"id": "a1", "attempt": 1, "assignee": "t-impl-old", "kind": "source",
                                       "assignment_status": "succeeded", "dispatched_at": "2026-10-24T00:00:00Z"})
        f.state["commit_log"] = [{"repository": "app", "sha": head, "assignment_id": "a1", "files": []}]
        f.save()
        rc, out = tester(f)
        check("tester gate: a renamed writer does not refuse", rc == 0 and "gone" not in str(out), out)
        f.agents["t-impl-sol"]["agent"]["agent_status"] = "working"
        f.save()
        rc, out = tester(f)
        check("tester gate: the current writer working refuses",
              rc == 1 and "t-impl-sol is working" in str(out), out)
        f.agents["t-impl-sol"]["agent"]["agent_status"] = "idle"
        f.team["roles"][0]["write_ceiling"] = []
        f.save()
        rc, out = tester(f)
        check("tester gate: no current source writer refuses", rc == 1 and "one source writer" in str(out), out)
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        head = git(f.repo, "rev-parse", "HEAD")
        line = {"repository": "app", "sha": head, "assignment_id": "a1", "files": []}
        (f.team_dir / "state-archive.yaml").write_text(yaml.safe_dump_all(
            [{"kind": "assignment", "record": {"id": "a1", "assignee": "t-impl-sol", "commit_log": [line]}}]))
        f.save()
        rc, out = tester(f)
        check("tester gate: the latest commit is found in the archive",
              rc == 0 and "no commit_log" not in str(out), out)
        f.state["commit_log"] = [{"repository": "app", "sha": "0" * 40, "assignment_id": "a0", "files": [],
                                  "at": "2026-01-01T00:00:00Z"}]
        (f.team_dir / "state-archive.yaml").write_text(yaml.safe_dump_all(
            [{"kind": "assignment", "record": {"id": "a1", "assignee": "t-impl-sol",
                                               "commit_log": [dict(line, at="2026-02-01T00:00:00Z")]}}]))
        f.save()
        rc, out = tester(f)
        check("tester gate: a newer archived commit beats an older live one", rc == 0, out)


def baseline_cases(check):
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        (f.repo / "src/a.txt").write_text("user edit\n")             # in lease, dirty
        (f.repo / "docs/readme.md").write_text("user doc\n")         # outside lease, dirty
        (f.repo / "src/new\nline.txt").write_text("odd\n")           # newline name, untracked
        os.symlink("a.txt", f.repo / "src/ln")                       # symlink, untracked
        (f.repo / "src/b.txt").write_text("staged\n")
        git(f.repo, "add", "src/b.txt")
        (f.repo / "src/b.txt").write_text("b\n")                     # staged-only change
        f.add_assignment("a1", status="pending")
        rc, out = f.db("capture", "--team-dir", str(f.team_dir), "--assignment", "a1",
                       "--attempt", "1", "--record")
        check("capture records the dirty baseline", rc == 0, out)
        state = f.reload()
        item = state["assignments"][0]
        lines = [json.loads(x) for x in Path(item["dirty_baseline"]).read_text().splitlines()]
        import base64
        names = {base64.b64decode(e["path_b64"]).decode() for e in lines}
        check("baseline keeps a newline file name losslessly", "src/new\nline.txt" in names, sorted(names))
        by = {base64.b64decode(e["path_b64"]).decode(): e for e in lines}
        check("baseline records a symlink target, a staged-only index blob, and a clean worktree",
              by["src/ln"]["worktree"]["type"] == "symlink"
              and by["src/b.txt"]["index"] is not None
              and by["src/b.txt"]["xy"][0] == "M", by.get("src/b.txt"))
        dad = {d["path"] for d in item["dirty_at_dispatch"]}
        check("only in-lease dirty files are snapshotted",
              "src/a.txt" in dad and "docs/readme.md" not in dad, sorted(dad))
        snap = next(d for d in item["dirty_at_dispatch"] if d["path"] == "src/a.txt")
        check("snapshot holds the pre-dispatch content", Path(snap["snapshot"]).read_text() == "user edit\n")
        check("capture recorded input_sha", item["repositories"][0]["input_sha"] == f.base)
        rc, out = f.db("capture", "--team-dir", str(f.team_dir), "--assignment", "a1", "--attempt", "1")
        check("an identical capture rerun passes", rc == 0, out)
        (f.repo / "src/c.txt").write_text("late\n")
        before = Path(item["dirty_baseline"]).read_text()
        rc, out = f.db("capture", "--team-dir", str(f.team_dir), "--assignment", "a1", "--attempt", "1")
        check("a different capture for the same attempt is refused and the file kept",
              rc == 1 and Path(item["dirty_baseline"]).read_text() == before, out)
        os.unlink(f.repo / "src/c.txt")

        args = ["compare", "--team-dir", str(f.team_dir), "--assignment", "a1", "--attempt", "1",
                "--mode", "accept"]
        (f.repo / "src/a.txt").write_text("user edit\nagent line\n")
        rc, out = f.db(*args)
        check("accept compare passes in-lease edits", rc == 0 and out["changed"]["app"] == ["src/a.txt"], out)
        snap_json = json.loads(Path(out["accept_snapshot"]).read_text())
        entry = snap_json["repos"]["app"]["paths"][0]
        check("diff base for a dirty_at_dispatch file is its snapshot",
              entry["dirty_at_dispatch"] and entry["diff_base"].endswith("snapshots/app/src/a.txt"), entry)
        (f.repo / "docs/readme.md").write_text("agent touched doc\n")
        rc, out = f.db(*args)
        check("accept compare refuses a changed baseline path outside the lease",
              rc == 1 and any("docs/readme.md" in r for r in out["reasons"]), out)
        (f.repo / "docs/readme.md").write_text("user doc\n")
        (f.repo / "docs/new.md").write_text("n\n")
        rc, out = f.db(*args)
        check("accept compare refuses a new dirty path outside the lease", rc == 1, out)
        os.unlink(f.repo / "docs/new.md")
        (f.repo / "src/a.txt").write_text("user edit\n")
        git(f.repo, "stash", "-q", "--include-untracked")
        (f.repo / "x").write_text("x")
        git(f.repo, "add", "x")
        git(f.repo, "commit", "-q", "-m", "moved")
        rc, out = f.db(*args)
        check("accept compare refuses a moved HEAD", rc == 1 and any("HEAD" in r for r in out["reasons"]), out)


def commit_cases(check):
    def prepared(tmp):
        f = Fixture(tmp)
        (f.repo / "src/b.txt").write_text("before dispatch\n")
        f.add_assignment("a1", status="running")
        f.db("capture", "--team-dir", str(f.team_dir), "--assignment", "a1", "--attempt", "1", "--record")
        (f.repo / "src/a.txt").write_text("agent\n")
        (f.repo / "src/b.txt").write_text("before dispatch\nagent\n")
        rc, out = f.db("compare", "--team-dir", str(f.team_dir), "--assignment", "a1", "--attempt", "1",
                       "--mode", "accept", "--record")
        assert rc == 0, out
        f.reload()
        f.state["assignments"][0]["commit"].update(
            {"status": "approved", "approved_by": "user", "confirmed_files": ["src/a.txt", "src/b.txt"]})
        f.save()
        return f

    def gate(f, step, *extra):
        return f.gate(step, "--team-dir", str(f.team_dir), "--assignment", "a1", *extra)

    with tempfile.TemporaryDirectory() as tmp:
        f = prepared(tmp)
        rc, out = gate(f, "precheck")
        check("commit precheck passes an approved, unchanged list", rc == 0, out)
        f.state["assignments"][0]["commit"]["status"] = "awaiting_user"
        f.state["commit_approval"] = {"mode": "auto", "granted_by_words": "auto commit ok", "granted_at": "t"}
        f.save()
        rc, out = gate(f, "precheck")
        check("auto mode still asks the User for a dirty_at_dispatch file",
              rc == 1 and any("dirty_at_dispatch" in r for r in out["reasons"]), out)
        f.state["assignments"][0]["commit"]["status"] = "approved"
        f.state["commit_approval"]["mode"] = "ask"
        f.save()
        (f.repo / "src/a.txt").write_text("changed after approval\n")
        rc, out = gate(f, "precheck")
        check("commit precheck refuses content changed after approval",
              rc == 1 and any("after the User approved" in r for r in out["reasons"]), out)
        (f.repo / "src/a.txt").write_text("agent\n")
        (f.repo / "src/stray.txt").write_text("s\n")
        git(f.repo, "add", "src/stray.txt")
        rc, out = gate(f, "precheck")
        check("commit precheck refuses a stray staged entry", rc == 1, out)
        git(f.repo, "rm", "-q", "--cached", "src/stray.txt")
        os.unlink(f.repo / "src/stray.txt")
        rc, out = gate(f, "precheck")
        check("commit precheck passes again once the index is clean", rc == 0, out)

        git(f.repo, "commit", "-q", "-m", "work", "--", "src/a.txt", "src/b.txt")
        state_before = (f.team_dir / "team-state.yaml").read_text()
        rc, out = gate(f, "verify")
        check("commit verify passes one exact commit", rc == 0, out)
        check("verify without --record writes nothing",
              (f.team_dir / "team-state.yaml").read_text() == state_before)
        rc, out = gate(f, "verify", "--record")
        state = f.reload()
        item = state["assignments"][0]
        check("verify --record logs the commit and the post-commit baseline",
              rc == 0 and state["commit_log"][-1]["sha"] == git(f.repo, "rev-parse", "HEAD")
              and item["commit"]["status"] == "committed" and Path(item["post_commit_baseline"]).exists()
              and item["repositories"][0]["result_sha"] == git(f.repo, "rev-parse", "HEAD"), out)

        item["assignment_status"] = "succeeded"
        f.save()
        rc, out = f.precheck(role="t-test-luna", kind="tester", scope=[], assignment="t1",
                             extra=["--output", f"{f.repo}/build/**"])
        check("end to end: the tester gate passes on the accepted commit", rc == 0, out)
        f.add_assignment("t1", assignee="t-test-luna", kind="tester", paths=[],
                         outputs=[f"{f.repo}/build/**"])
        f.state["assignments"][-1]["checkout_dir"] = str(f.tmp)
        f.save()
        f.db("capture", "--team-dir", str(f.team_dir), "--assignment", "t1", "--attempt", "1", "--record")
        rc, out = f.db("compare", "--team-dir", str(f.team_dir), "--assignment", "t1", "--attempt", "1",
                       "--mode", "tester-pre")
        check("end to end: tester-pre passes after capture", rc == 0, out)
        (f.repo / "build").mkdir()
        (f.repo / "build/out.log").write_text("ok\n")
        rc, out = f.db("compare", "--team-dir", str(f.team_dir), "--assignment", "t1", "--attempt", "1",
                       "--mode", "tester-post")
        check("tester-post allows declared outputs", rc == 0, out)
        (f.repo / "src/a.txt").write_text("tester touched source\n")
        rc, out = f.db("compare", "--team-dir", str(f.team_dir), "--assignment", "t1", "--attempt", "1",
                       "--mode", "tester-post")
        check("tester-post refuses a tracked source change", rc == 1, out)

    for label, mutate in (
            ("an unconfirmed file", lambda f: (Path(f.repo / "src/extra.txt").write_text("e\n"),
                                               git(f.repo, "add", "src/extra.txt"),
                                               git(f.repo, "commit", "-q", "-m", "w"))),
            ("a missing confirmed file", lambda f: git(f.repo, "commit", "-q", "-m", "w", "--", "src/a.txt")),
            ("two commits", lambda f: (git(f.repo, "commit", "-q", "-m", "w1", "--", "src/a.txt"),
                                       git(f.repo, "commit", "-q", "-m", "w2", "--", "src/b.txt"))),
            ("another branch", lambda f: (git(f.repo, "switch", "-q", "-c", "other"),
                                          git(f.repo, "commit", "-q", "-m", "w", "--", "src/a.txt", "src/b.txt"))),
            ("different committed content", lambda f: (Path(f.repo / "src/a.txt").write_text("swapped\n"),
                                                       git(f.repo, "commit", "-q", "-m", "w", "--",
                                                           "src/a.txt", "src/b.txt")))):
        with tempfile.TemporaryDirectory() as tmp:
            f = prepared(tmp)
            mutate(f)
            before = (f.team_dir / "team-state.yaml").read_text()
            rc, out = gate(f, "verify", "--record")
            check(f"commit verify refuses {label} and writes nothing",
                  rc == 1 and (f.team_dir / "team-state.yaml").read_text() == before, out)


def robustness_cases(check):
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        (f.team_dir / "team-state.yaml").write_text("roles: [unclosed\n")
        rc, out = f.precheck()
        check("a broken team-state.yaml gives cannot tell", rc == 3, out)
        f.state["team_dir"] = "/elsewhere"
        f.save()
        rc, out = f.precheck()
        check("a team_dir mismatch gives cannot tell", rc == 3, out)


def inbox_env(f, **extra):
    env = f.env()
    env.update({"HAT_INBOX_GRACE_S": "0", "HAT_INBOX_RING_MAX": "2", "HAT_INBOX_POLL_S": "0.05"})
    env.update(extra)
    return env


def inbox(f, *args, env=None):
    proc = subprocess.run([sys.executable, str(ASSETS / "inbox.py"), *args, "--team-dir", str(f.team_dir)],
                          capture_output=True, text=True, env=env or inbox_env(f))
    try:
        return proc.returncode, json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return proc.returncode, {"raw": proc.stdout, "stderr": proc.stderr}


def herdr_log(f):
    return json.loads(f.herdr_state.read_text()).get("log", [])


def watcher(f, ws, steering, env_extra=None):
    env = inbox_env(f, HAT_STEERING=steering, HAT_TEAM_DIR=str(f.team_dir))
    env.update(env_extra or {})
    proc = subprocess.run(["bash", str(ASSETS / "watch-assignment.sh"), "t-impl-sol", str(ws), "1", "30"],
                          capture_output=True, text=True, env=env, timeout=120)
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"raw": proc.stdout, "stderr": proc.stderr}


def inbox_fixture(tmp):
    f = Fixture(tmp)
    f.team["roles"][0]["steering"] = "inbox"
    f.save()
    return f


def inbox_cases(check):
    with tempfile.TemporaryDirectory() as tmp:
        f = inbox_fixture(tmp)
        box = f.team_dir / "inbox" / "t-impl-sol"
        rc, out = inbox(f, "send", "--role", "t-impl-sol", "--kind", "note", "--body", "hello")
        check("inbox send writes 0001.msg and rings an idle role at once",
              rc == 0 and out["msg"] == "0001.msg" and out["ring"] == "rung"
              and any("INBOX:" in " ".join(e) for e in herdr_log(f)), out)
        text = (box / "0001.msg").read_text()
        check("inbox record carries schema, kind, and body",
              text.startswith("schema=hat-inbox.v1\n") and "kind=note" in text and text.endswith("--\nhello\n"))
        (box / "handled").mkdir(exist_ok=True)
        for n in (2, 3):
            (box / "handled" / f"{n:04d}.msg").write_text("x")
        rc, out = inbox(f, "send", "--role", "t-impl-sol", "--kind", "note", "--body", "b", "--no-ring")
        check("inbox sequence numbers skip handled ones (never reused)", out.get("msg") == "0004.msg", out)
        procs = [subprocess.Popen([sys.executable, str(ASSETS / "inbox.py"), "send", "--team-dir", str(f.team_dir),
                                   "--role", "t-impl-sol", "--kind", "note", "--body", f"c{i}", "--no-ring"],
                                  stdout=subprocess.DEVNULL, env=inbox_env(f)) for i in range(12)]
        for proc in procs:
            proc.wait()
        names = sorted(p.name for p in box.glob("*.msg"))
        check("concurrent sends get unique contiguous sequence numbers",
              len(names) == 14 and names[-1] == "0016.msg", names)
        check("no temp file is ever named *.msg", not any(p.name.startswith(".") for p in box.glob("*.msg")))
        rc, out = inbox(f, "send", "--role", "t-test-luna", "--kind", "note", "--body", "x")
        check("inbox send refuses a steering: prompt role", rc == 1, out)
        rc, out = inbox(f, "send", "--role", "t-test-luna", "--kind", "note", "--body", "check",
                        "--handshake", "--no-ring")
        check("Adjust handshake may send one note to a prompt role", rc == 0, out)
        rc, out = inbox(f, "send", "--role", "t-test-luna", "--kind", "nudge", "--body", "x", "--handshake")
        check("handshake sends only notes", rc == 2, out)

        for p in box.glob("*.msg"):
            p.unlink()
        f.agents["t-impl-sol"]["agent"]["agent_status"] = "working"
        f.herdr_state.write_text(json.dumps({"agents": f.agents, "log": []}))
        rc, out = inbox(f, "send", "--role", "t-impl-sol", "--kind", "note", "--body", "busy")
        check("inbox never rings a working role", out.get("ring") == "deferred" and not herdr_log(f), out)
        f.agents["t-impl-sol"]["agent"]["agent_status"] = "idle"
        f.herdr_state.write_text(json.dumps({"agents": f.agents, "log": []}))
        codes = [inbox(f, "ring", "--role", "t-impl-sol")[0] for _ in range(3)]
        check("ring rings, rings again after grace, then exits 4 unacknowledged", codes == [0, 0, 4], codes)
        for p in box.glob("*.msg"):
            os.replace(p, box / "handled" / p.name)
        rc, out = inbox(f, "ring", "--role", "t-impl-sol")
        check("an acknowledged inbox clears the ring state",
              rc == 0 and out["outcome"] == "empty" and not (box / ".ring-state").exists(), out)

    with tempfile.TemporaryDirectory() as tmp:
        f = inbox_fixture(tmp)
        box = f.team_dir / "inbox" / "t-impl-sol"
        f.agents["t-impl-sol"]["on_prompt"] = {"move_inbox": str(box)}
        f.save()
        inbox(f, "send", "--role", "t-impl-sol", "--kind", "tester-window", "--window", "t1",
              "--window-state", "closed", "--body", "Tester window closed.", "--no-ring")
        rc, out = inbox(f, "wait-ack", "--role", "t-impl-sol")
        check("wait-ack delivers to an idle role with no Assignment watcher", rc == 0
              and out["outcome"] == "inbox_acked", out)
        f.agents["t-impl-sol"].pop("on_prompt")
        f.save()
        inbox(f, "send", "--role", "t-impl-sol", "--kind", "note", "--body", "lost", "--no-ring")
        rc, out = inbox(f, "wait-ack", "--role", "t-impl-sol")
        check("wait-ack escalates an unacknowledged message", rc == 4 and out["outcome"] == "inbox_unacked", out)
        for p in box.glob("*.msg"):
            os.replace(p, box / "handled" / p.name)
        f.agents["t-impl-sol"]["statuses"] = ["working", "working", "idle"]
        f.agents["t-impl-sol"]["on_prompt"] = {"move_inbox": str(box)}
        f.save()
        inbox(f, "send", "--role", "t-impl-sol", "--kind", "note", "--body", "after report", "--no-ring")
        rc, out = inbox(f, "status", "--role", "t-impl-sol")
        check("status shows a message still pending after its watcher is gone",
              len(out["roles"]["t-impl-sol"]["pending"]) == 1, out)
        rc, out = inbox(f, "wait-ack", "--role", "t-impl-sol")
        check("wait-ack waits out working and rings once the role is idle",
              rc == 0 and len(herdr_log(f)) == 1, (out, herdr_log(f)))

    with tempfile.TemporaryDirectory() as tmp:
        f = inbox_fixture(tmp)
        box = f.team_dir / "inbox" / "t-impl-sol"
        f.add_assignment("a1", status="running", attempt=2)
        rc, out = inbox(f, "send", "--role", "t-impl-sol", "--kind", "handoff-request", "--assignment", "a1",
                        "--attempt", "1", "--body", "Write your handoff now, then stop.")
        check("send refuses a message for a past attempt", rc == 1 and not list(box.glob("*.msg")), out)
        inbox(f, "send", "--role", "t-impl-sol", "--kind", "handoff-request", "--assignment", "a1",
              "--attempt", "2", "--body", "Write your handoff now, then stop.", "--no-ring")
        f.state["assignments"][0]["attempt"] = 3
        f.save()
        rc, out = inbox(f, "ring", "--role", "t-impl-sol")
        check("ring retires a record whose attempt is no longer current, without ringing",
              out.get("outcome") == "empty" and (box / "retired/0001.msg").exists()
              and (box / "retired/0001.reason").exists() and not herdr_log(f), out)
        f.add_assignment("t1", assignee="t-test-luna", kind="tester", paths=[], outputs=[f"{f.repo}/build/**"])
        inbox(f, "send", "--role", "t-impl-sol", "--kind", "tester-window", "--window", "t1",
              "--window-state", "open", "--body", "Tester window open for t1.", "--no-ring")
        f.state["assignments"][-1]["assignment_status"] = "succeeded"
        f.save()
        inbox(f, "ring", "--role", "t-impl-sol")
        check("a delayed tester-window open after the window closed is retired",
              (box / "retired/0002.msg").exists(), sorted(p.name for p in box.rglob("*")))
        inbox(f, "send", "--role", "t-impl-sol", "--kind", "note", "--assignment", "a1", "--attempt", "3",
              "--body", "n", "--no-ring")
        rc, out = inbox(f, "retire", "--role", "t-impl-sol", "--assignment", "a1", "--before-attempt", "4",
                        "--reason", "rework")
        check("retire moves the Lead-named stale records", out.get("retired") == ["0003.msg"], out)

    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        ws = f.team_dir / "assignments" / "a1"
        ws.mkdir(parents=True)
        f.add_assignment("a1", status="running")
        out = watcher(f, ws, "prompt")
        log = herdr_log(f)
        check("watcher in prompt mode keeps the 4.2.0 typed nudge then no_report",
              out.get("outcome") == "no_report" and len(log) == 1 and log[0][0] == "prompt"
              and "Write '" in log[0][2], (out, log))

    with tempfile.TemporaryDirectory() as tmp:
        f = inbox_fixture(tmp)
        ws = f.team_dir / "assignments" / "a1"
        ws.mkdir(parents=True)
        f.add_assignment("a1", status="running")
        box = f.team_dir / "inbox" / "t-impl-sol"
        out = watcher(f, ws, "inbox")
        check("watcher in inbox mode writes the nudge and escalates when never acknowledged",
              out.get("outcome") == "inbox_unacked" and (box / "0001.msg").exists()
              and all("INBOX:" in e[2] for e in herdr_log(f)), (out, herdr_log(f)))
        (box / "handled").mkdir(exist_ok=True)
        for p in box.glob("*.msg"):
            os.replace(p, box / "handled" / p.name)
        f.agents["t-impl-sol"]["on_prompt"] = {"move_inbox": str(box)}
        f.save()
        out = watcher(f, ws, "inbox")
        check("watcher in inbox mode reports no_report after an acknowledged nudge",
              out.get("outcome") == "no_report" and (box / "handled/0002.msg").exists(), out)
        f.agents["t-impl-sol"]["on_prompt"] = {"write": {"path": str(ws / "report.md"),
                                                         "text": "# Report: a1\n**Attempt:** 1\n"}}
        f.save()
        out = watcher(f, ws, "inbox")
        check("watcher in inbox mode still exits on report", out.get("outcome") == "report", out)
        (ws / "report.md").unlink(missing_ok=True)
        f.state["assignments"][0]["attempt"] = 2
        f.save()
        out = watcher(f, ws, "inbox")
        check("watcher nudge after an attempt change is refused: superseded",
              out.get("outcome") == "superseded", out)


def legacy_cases(check):
    """Data written under 4.2.0: dirty-baseline.tsv, no accept snapshot, no
    post_commit_baseline, dirty_at_dispatch without path_b64."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Fixture(tmp)
        nested = f.repo / "common"
        nested.mkdir()
        sh("git", "init", "-q", str(nested))
        (nested / "n.txt").write_text("n")
        (f.repo / "docs/readme.md").write_text("user doc\n")
        doc_blob = git(f.repo, "hash-object", "docs/readme.md")
        doc_index = git(f.repo, "ls-files", "-s", "--", "docs/readme.md").split()[1]
        item = f.add_assignment("old", status="succeeded", paths=[f"{f.repo}/src/a.txt"])
        ws = f.team_dir / "assignments" / "old" / "artifacts" / "attempt-1"
        ws.mkdir(parents=True)
        tsv = ws / "dirty-baseline.tsv"
        tsv.write_text(f"app\tcommon/\t??\tnested-repo\tnone\napp\tdocs/readme.md\t M\t{doc_blob}\t{doc_index}\n")
        item.update({"repositories": [{"name": "app", "input_sha": f.base, "result_sha": None}],
                     "dirty_baseline": str(tsv), "dirty_at_dispatch": None,
                     "commit": {"status": "none", "confirmed_files": None, "approved_by": None, "approved_at": None}})
        f.save()
        (f.repo / "src/a.txt").write_text("agent fix\n")
        args = ["compare", "--team-dir", str(f.team_dir), "--assignment", "old", "--attempt", "1", "--mode", "accept"]
        rc, out = f.db(*args, "--record")
        check("legacy TSV: accept compare reads a 4.2.0 baseline with a nested repo",
              rc == 0 and out["changed"]["app"] == ["src/a.txt"], out)
        f.reload()
        f.state["assignments"][0]["commit"].update(
            {"status": "approved", "approved_by": "user", "confirmed_files": ["src/a.txt"]})
        f.save()
        rc, out = f.gate("precheck", "--team-dir", str(f.team_dir), "--assignment", "old")
        check("legacy TSV: a hand-accepted 4.2.0 Assignment reaches the commit gate after one compare --record",
              rc == 0, out)
        (f.repo / "docs/readme.md").write_text("changed outside the lease\n")
        rc, out = f.db(*args)
        check("legacy TSV: a changed out-of-scope baseline file is still refused",
              rc == 1 and any("docs/readme.md" in r for r in out["reasons"]), out)
        (f.repo / "docs/readme.md").write_text("user doc\n")

        git(f.repo, "commit", "-q", "-m", "fix", "--", "src/a.txt")
        head = git(f.repo, "rev-parse", "HEAD")
        f.reload()
        f.state["commit_log"] = [{"assignment_id": "old", "repository": "app", "sha": head,
                                  "files": ["src/a.txt"], "approved_by": "user", "at": "t"}]
        f.state["assignments"][0]["commit"]["status"] = "committed"
        f.save()
        rc, out = f.precheck(role="t-test-luna", kind="tester", scope=[], assignment="t1",
                             extra=["--output", f"{f.repo}/build/**"])
        check("legacy tester gate: a 4.2.0 commit without post_commit_baseline uses its dispatch baseline",
              rc == 0, out)
        (f.repo / "src/b.txt").write_text("uncommitted\n")
        rc, out = f.precheck(role="t-test-luna", kind="tester", scope=[], assignment="t1",
                             extra=["--output", f"{f.repo}/build/**"])
        check("legacy tester gate: an extra dirty source file still refuses", rc == 1, out)
        (f.repo / "src/b.txt").write_text("b\n")
        archived = f.state["assignments"].pop(0)
        f.save()
        (f.team_dir / "state-archive.yaml").write_text(
            __import__("yaml").safe_dump({"kind": "assignment", "record": archived}, sort_keys=False))
        rc, out = f.precheck(role="t-test-luna", kind="tester", scope=[], assignment="t1",
                             extra=["--output", f"{f.repo}/build/**"])
        check("legacy tester gate: the accepted Assignment is found in state-archive.yaml", rc == 0, out)
        (f.team_dir / "state-archive.yaml").unlink()
        rc, out = f.precheck(role="t-test-luna", kind="tester", scope=[], assignment="t1",
                             extra=["--output", f"{f.repo}/build/**"])
        check("legacy tester gate: a commit with no Assignment record passes with a 4.2.0-rule warning",
              rc == 0 and any("legacy commit" in w for w in out.get("warnings", [])), out)
        other = f.tmp / "other"
        other.mkdir()
        sh("git", "init", "-q", "-b", "main", str(other))
        git(other, "config", "user.email", "t@example.com")
        git(other, "config", "user.name", "t")
        (other / "x").write_text("x")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "x")
        f.team["code_repos"].append({"name": "other", "path": str(other), "base_branch": "main", "rules_file": None})
        f.save()
        rc, out = f.precheck(role="t-test-luna", kind="tester", scope=[], assignment="t1",
                             extra=["--output", f"{f.repo}/build/**"])
        check("tester gate with several code repositories needs --repo", rc == 3, out)
        rc, out = f.precheck(role="t-test-luna", kind="tester", scope=[], assignment="t1",
                             extra=["--output", f"{f.repo}/build/**", "--repo", "app"])
        check("tester gate checks only the named repository (an unrelated repo's HEAD is ignored)", rc == 0, out)
        f.state["assignments"].append({"id": "legacy-run", "attempt": 1, "assignee": "t-impl-sol",
                                       "assignment_status": "running", "dispatched_at": "t",
                                       "lease": {"paths": [f"{f.repo}/src/**"]}})
        f.save()
        rc, out = f.precheck(role="t-test-luna", kind="tester", scope=[], assignment="t1",
                             extra=["--output", f"{f.repo}/build/**", "--repo", "app"])
        check("tester gate treats a running pre-4.3.0 writer Assignment (no kind) as source work",
              rc == 1 and any("legacy-run" in r for r in out["reasons"]), out)
        f.state["assignments"][-1].update({"id": "legacy-test", "assignee": "t-tester-luna", "lease": {"paths": []}})
        f.save()
        rc, out = f.precheck(assignment="a2", scope=[f"{f.repo}/docs/**"])
        check("source dispatch sees a running pre-4.3.0 tester Assignment (no kind) as an open tester window",
              rc == 1 and any("tester window open (legacy-test)" in r for r in out["reasons"]), out)


def run(check):
    legacy_cases(check)
    inbox_cases(check)
    precheck_cases(check)
    context_cases(check)
    context_reply_cases(check)
    rename_archive_cases(check)
    baseline_cases(check)
    commit_cases(check)
    robustness_cases(check)
