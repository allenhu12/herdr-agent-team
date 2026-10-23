#!/usr/bin/env python3
"""Static package-contract checks. Does not launch Herdr or test agent behavior."""
import importlib.util
import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.dont_write_bytecode = True


ROOT = Path(__file__).resolve().parents[1]
results = []


def check(name, condition, detail=""):
    results.append({"check": name, "passed": bool(condition), "detail": detail})


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def run_archive_fixture():
    script = str(ROOT / "assets/archive-state.py")
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "team-state.yaml"
        original = read("evals/fixtures/team-state-archive.yaml").replace("TEAM_DIR", tmp)
        state_path.write_text(original, encoding="utf-8")

        def run(*args):
            return subprocess.run([sys.executable, script, *args], capture_output=True, text=True)

        run("archive", tmp, "--keep", "1")
        state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
        raw = state_path.read_text(encoding="utf-8")
        docs = list(yaml.safe_load_all((Path(tmp) / "state-archive.yaml").read_text(encoding="utf-8")))
        done1 = next(d["record"] for d in docs if d["record"].get("id") == "done-1")
        state_path.write_text(original, encoding="utf-8")
        run("archive", tmp, "--keep", "1")
        rerun = list(yaml.safe_load_all((Path(tmp) / "state-archive.yaml").read_text(encoding="utf-8")))
        return {
            "live_ids": [a["id"] for a in state["assignments"]],
            "archived_ids": [d["record"]["id"] for d in docs if d["kind"] == "assignment"],
            "commit_log": [c["assignment_id"] for c in state["commit_log"]],
            "done1_log": [c["sha"] for c in done1["commit_log"]],
            "lead_history": [h["name"] for h in state["lead_history"]],
            "rotations": [r["handoff_path"] for r in state["roles"]["demo-api-codex"]["rotations"]],
            "questions": [q["id"] for q in state["pending_user"]],
            "updated_at_is_str": "updated_at: '" in raw,
            "rerun_docs": len(rerun),
            "busy_rc": run("archive", tmp, "--remove-role", "demo-api-codex").returncode,
            "find_rc": run("find", tmp, "done-1").returncode,
        }


def main():
    skill = read("SKILL.md")
    front = yaml.safe_load(skill.split("---", 2)[1])
    interface = yaml.safe_load(read("agents/interface.yaml"))
    check("entrypoint identity", front["name"] == "herdr-agent-team")
    version = str((front.get("metadata") or {}).get("version") or "")
    check("SKILL.md carries a semantic version", re.fullmatch(r"\d+\.\d+\.\d+", version), version)
    top = re.search(r"^## \[?(\d+\.\d+\.\d+)", read("CHANGELOG.md"), re.M)
    check("CHANGELOG top version equals SKILL.md version", top and top.group(1) == version,
          top and top.group(1))
    probe = subprocess.run([sys.executable, str(ROOT / "assets/skill-version.py"), "--changes"],
                           capture_output=True, text=True)
    check("skill-version.py prints the version and its changes",
          probe.returncode in (0, 3) and f"version: {version}" in probe.stdout
          and f"## {version}" in probe.stdout, probe.stdout + probe.stderr)
    check("interface invocation alignment",
          "$" + front["name"] in interface["interface"]["default_prompt"])

    broken = []
    for path in ROOT.rglob("*.md"):
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                continue
            target = target.split("#", 1)[0].strip("<>")
            if not (path.parent / target).exists():
                broken.append(f"{path.relative_to(ROOT)}: {target}")
    check("local Markdown links resolve", not broken, broken)

    team = yaml.safe_load(read("assets/team.yaml.template"))
    state = yaml.safe_load(read("assets/team-state.yaml.template"))
    check("team/state schema versions agree", team["schema_version"] == state["schema_version"] == 2)
    check("canonical roots agree and are absolute",
          team["project_root"] == state["project_root"] and Path(team["project_root"]).is_absolute())
    check("Lead identity separate from roles",
          team["lead"]["name"] == state["lead"]["name"]
          and {"name", "pane_id", "kind", "cwd", "process_identity", "identity_verified_at"} <= state["lead"].keys()
          and "lead" not in state["roles"] and isinstance(state["lead_history"], list))
    required_role = {"name", "responsibility", "kind", "model", "model_label", "profile",
                     "effort", "launch_args", "access", "checkout_dir", "position",
                     "write_ceiling", "up_agent", "low_agent"}
    roles = team["roles"]
    check("role templates carry explicit launch and access fields",
          bool(roles) and all(required_role <= role.keys() for role in roles))
    check("role template hierarchy and scope shapes",
          all(role["up_agent"] == "lead" and role["low_agent"] == []
              and isinstance(role["write_ceiling"], list)
              and all(isinstance(p, str) for p in role["write_ceiling"])
              and role["access"] in {"reader", "writer"}
              and Path(role["checkout_dir"]).is_absolute() for role in roles))
    check("state preserves lifecycle collections",
          all(isinstance(state[k], list) for k in ("assignments", "monitors", "resources")))
    check("integration templates agree",
          team["integration"]["checkout_dir"] == state["integration"]["checkout_dir"]
          and {"status", "accepted_artifacts", "final_artifact", "checks"} <= state["integration"].keys())

    check("team_dir recorded in both templates and agrees",
          team.get("team_dir") == state.get("team_dir") and Path(team["team_dir"]).is_absolute())
    check("lead carries mode and effective fields",
          {"mode", "kind", "model", "effort", "suggested"} <= team["lead"].keys()
          and {"launched_by_team", "handoff_at"} <= state["lead"].keys() and "launcher" in state)
    check("team permissions default to inherit",
          team.get("permissions") == "inherit")
    check("role templates carry prompt_file and skills hooks",
          all("prompt_file" in r and isinstance(r.get("skills"), list) for r in roles))
    check("generic role contexts are empty and portable",
          all(r.get("context_roots") == [] for r in roles))

    handoff = read("assets/handoff.md.template")
    handoff_sections = re.findall(r"^## (.+)$", handoff, re.M)
    check("handoff template has seven required sections", handoff_sections == [
        "Where I am", "Done", "Not done", "Decisions and why", "Gotchas",
        "First action next", "Open questions"])
    check("handoff template carries attempt metadata", "**Attempt:** <attempt>" in handoff)
    check("workflow table exposes Rotate", "| Rotate:" in skill and "references/rotate.md" in skill)
    rotate = read("references/rotate.md")
    check("Rotate continuation uses only absolute workspace paths",
          "<absolute-workspace-dir>/assignment.md" in rotate
          and "<absolute-workspace-dir>/handoff.md" in rotate
          and "<absolute-workspace-dir>/log.md" in rotate
          and "<workspace>/" not in rotate)
    resume = read("references/resume.md")
    check("Resume continuation names absolute control paths",
          all(f"<absolute-workspace-dir>/{name}" in resume
              for name in ("assignment.md", "handoff.md", "log.md")))
    check("team state template supports rotation history",
          "rotations: []" in read("assets/team-state.yaml.template"))
    check("team state template names the archive",
          "archive" in state and state["archive"] is None)
    check("writer-rules protects the state archive", "<team_dir>/state-archive.yaml" in read("references/writer-rules.md"))
    archive_results = run_archive_fixture()
    check("archive moves only settled, unmonitored, gate-closed Assignments",
          archive_results["live_ids"] == ["gate-open", "watched", "live", "held", "queued"]
          and archive_results["archived_ids"] == ["done-1", "done-2"], archive_results)
    check("archive moves commit_log lines with their Assignment",
          archive_results["commit_log"] == ["gate-open"] and archive_results["done1_log"] == ["abc"],
          archive_results)
    check("archive trims history to --keep and keeps timestamps as strings",
          archive_results["lead_history"] == ["old-lead-2"] and archive_results["rotations"] == ["/h/2"]
          and archive_results["updated_at_is_str"], archive_results)
    check("archive moves answered questions only when no report waits on them",
          archive_results["questions"] == ["q-2", "q-3"], archive_results)
    check("archive rerun after a crash adds no duplicates", archive_results["rerun_docs"] == 5, archive_results)
    check("state template records the skill version", "skill_version" in state)
    check("state template records questions to the User",
          state.get("pending_user") == [] and state.get("user_question_seq") == 0)
    check("dispatch holds reports blocked by an open question",
          "## 5c. Waiting on the User" in read("references/dispatch.md")
          and "## Waiting on User" in read("assets/lead-handoff.md.template"))
    check("archive refuses to remove a busy role and finds archived ids",
          archive_results["busy_rc"] == 2 and archive_results["find_rc"] == 0, archive_results)
    watcher = read("assets/watch-assignment.sh")
    check("watcher emits current-attempt handoff outcome",
          "emit handoff" in watcher and "HANDOFF READY attempt=$attempt" in watcher
          and "has_handoff" not in watcher)

    spec = importlib.util.spec_from_file_location("render_role_tree", ROOT / "assets/render-role-tree.py")
    rrt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rrt)
    check("generic template passes fixed chain and effort rules", not rrt.validate(team), rrt.validate(team))
    legacy = copy.deepcopy(team)
    for role in legacy["roles"]:
        role.pop("context_roots", None)
    check("legacy v2 roles without context_roots remain valid", not rrt.validate(legacy), rrt.validate(legacy))
    with_context = copy.deepcopy(team)
    with_context["roles"][0]["context_roots"] = ["/sample/context"]
    rendered = rrt.render(with_context)
    check("absolute context root renders marker without path",
          not rrt.validate(with_context) and "[context]" in rendered
          and "/sample/context" not in rendered, rrt.validate(with_context))
    for label, bad_roots in (("scalar", "/sample/context"),
                             ("relative", ["relative/path"]),
                             ("empty", [""]),
                             ("duplicate", ["/sample/context", "/sample/context/"])):
        invalid = copy.deepcopy(team)
        invalid["roles"][0]["context_roots"] = bad_roots
        check(f"renderer rejects {label} context_roots",
              any("context_roots" in error for error in rrt.validate(invalid)),
              rrt.validate(invalid))

    seeds = sorted((ROOT / "assets/teams").glob("*/team.yaml"))
    check("at least the develop seed exists", any(p.parent.name == "develop" for p in seeds))
    for path in seeds:
        seed = yaml.safe_load(path.read_text(encoding="utf-8"))
        label = f"seed {path.parent.name}"
        sug = (seed.get("lead") or {}).get("suggested") or {}
        check(f"{label}: marked template with matching team_type",
              seed.get("template") is True and seed.get("team_type") == path.parent.name)
        check(f"{label}: permissions inherit or scoped, default inherit",
              seed.get("permissions") == "inherit")
        check(f"{label}: lead.suggested has kind/model/effort",
              all(sug.get(k) for k in ("kind", "model", "effort")))
        seed_role = required_role | {"prompt_file", "skills"}
        check(f"{label}: roles carry required keys and hooks",
              bool(seed.get("roles")) and all(seed_role <= r.keys() for r in seed["roles"]))
        check(f"{label}: fixed chain and effort valid for kind", not rrt.validate(seed), rrt.validate(seed))
        check(f"{label}: context roots default to empty",
              all(r.get("context_roots") == [] for r in seed["roles"]))
        check(f"{label}: states both checkout_mode and code_repos (ADR 0004)",
              seed.get("checkout_mode") in ("shared", "isolated")
              and isinstance(seed.get("code_repos"), list)
              and isinstance(seed.get("protected_paths_extra"), list))
        if seed.get("checkout_mode") == "shared":
            check(f"{label}: shared mode leaves integration checkout null",
                  (seed.get("integration") or {}).get("checkout_dir") is None)
        run = subprocess.run([sys.executable, str(ROOT / "assets/render-role-tree.py"), str(path)],
                             capture_output=True, text=True)
        check(f"{label}: renders every role and the lead",
              run.returncode == 0 and "lead" in run.stdout
              and all(r["name"] in run.stdout for r in seed["roles"]), run.stderr)

    check("generic team.yaml states checkout_mode, code_repos, protected_paths_extra",
          team.get("checkout_mode") in ("shared", "isolated")
          and isinstance(team.get("code_repos"), list)
          and isinstance(team.get("protected_paths_extra"), list))
    develop = yaml.safe_load(read("assets/teams/develop/team.yaml"))
    check("develop seed is shared mode with an implementor role",
          develop.get("checkout_mode") == "shared"
          and any("-implementor-" in r["name"] for r in develop["roles"])
          and not any("-developer-" in r["name"] for r in develop["roles"]))
    rules = read("references/writer-rules.md")
    core = ["<team_dir>/team.yaml", "<team_dir>/team-state.yaml", "<team_dir>/role-tree.md",
            "<team_dir>/assignments/*/assignment.md", "<project_root>/00-current/**",
            "<project_root>/**/progress*.md", "<project_root>/**/item-list.json"]
    check("writer-rules lists every core protected path",
          "## Protected paths" in rules and all(c in rules for c in core))
    check("writer-rules defines one writer per checkout for both modes",
          "## One writer per checkout" in rules and "### Shared mode" in rules
          and "### Isolated mode" in rules)
    files = read("references/state-files.md")
    check("state-files defines legacy single-root by field absence",
          "neither `checkout_mode` nor `code_repos`" in files and "legacy single-root" in files)
    dispatch = read("references/dispatch.md")
    check("dispatch covers dirty baseline, tester gate, and late signals",
          all(k in dispatch for k in ("dirty-baseline.tsv", "Tester gate", "## 5b. Late signals")))
    check("no reference still names exclusive writer checkouts",
          not any("exclusive writer checkouts" in (ROOT / "references" / n).read_text()
                  for n in ("resume.md", "writer-rules.md", "assemble.md")))

    generic_prompts = [r.get("prompt_file") for r in roles if r.get("prompt_file")]
    check("real team.yaml prompt_file paths are absolute",
          all(Path(x).is_absolute() for x in generic_prompts), generic_prompts)
    assemble = read("references/assemble.md")
    check("no unreachable skip-if-no-python path in Assemble",
          "python is unavailable" not in assemble and "PyYAML" in assemble)

    bad = subprocess.run([sys.executable, str(ROOT / "assets/render-role-tree.py"),
                          str(ROOT / "evals/fixtures/team-branching.yaml")], capture_output=True, text=True)
    check("renderer rejects branching layout and bad effort",
          bad.returncode == 2 and "fixed chain" in bad.stderr and "not valid for kind" in bad.stderr, bad.stderr)
    bad_context = subprocess.run([sys.executable, str(ROOT / "assets/render-role-tree.py"),
                                  str(ROOT / "evals/fixtures/team-invalid-context.yaml")],
                                 capture_output=True, text=True)
    check("renderer CLI rejects malformed context fixture",
          bad_context.returncode == 2 and "context_roots" in bad_context.stderr,
          bad_context.stderr)

    report = read("assets/report.md.template")
    sections = re.findall(r"^## (.+)$", report, re.M)
    check("report has exactly the six approved sections", sections == [
        "Result", "Frozen commit or artifact path", "Files changed",
        "Test results", "Screenshot paths", "Unresolved issues"])
    check("report retains attempt and status metadata",
          "**Attempt:**" in report and "**Status:**" in report and report.startswith("# Report: <assignment-id>"))
    assignment = read("assets/assignment.md.template")
    check("Assignment contract has outcome/version/scope/exclusions/checks/artifact",
          {"Outcome", "Inputs", "Acceptance Criteria", "Write Scope",
           "Must Not Touch", "Final Artifact", "Partner Authorizations", "Rework History"}
          <= set(re.findall(r"^## (.+)$", assignment, re.M)))
    check("Assignment includes Lead and team_dir path metadata",
          all(f"**{key}:**" in assignment for key in
              ("Lead", "Team dir", "Team state", "Checkout Dir", "Workspace Dir", "Report path"))
          and ".herdr-agent-team/" not in assignment)

    guide = read("user-guide.md")
    fragments = re.findall(r"```yaml\n(.*?)```", guide, re.S)
    check("guide role examples match template keys",
          bool(fragments) and all(set(yaml.safe_load(part)) <= set(roles[0]) for part in fragments))
    cases = json.loads(read("evals/trigger-cases.json"))
    check("trigger cases cover positives negatives and neighbors",
          all(cases.get(bucket) for bucket in ("should_trigger", "should_not_trigger", "near_neighbor")))
    failed = [r for r in results if not r["passed"]]
    print(json.dumps({"kind": "static-package-contract", "passed": len(results) - len(failed),
                      "total": len(results), "failures": failed}, indent=2))
    return bool(failed)


if __name__ == "__main__":
    raise SystemExit(main())
