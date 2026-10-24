# Changelog

One section per version, newest first. The top version must equal
`metadata.version` in SKILL.md (`evals/check_package.py` checks this).
Check the version you use with `python3 assets/skill-version.py`.

Version numbers: a change to rules or workflows raises the middle number;
a wording or fix-only change raises the last number. A change that needs
new team files or breaks old ones raises the first number.
`schema_version` in team.yaml and team-state.yaml is a different number:
it is the state file format, and it stays 2.

## 4.3.0 - 2026-10-24

### Added

- Gate scripts that run the mechanical dispatch and acceptance checks and
  refuse instead of relying on the Lead to type every command. Each prints
  one JSON line and exits 0 (pass), 1 (refuse), 2 (usage), or 3 (cannot
  tell, treated as refuse); a crash is never a pass.
  - `assets/dispatch-precheck.py`: busy check, live identity (pane, kind,
    cwd, process, checkout), recorded model footer, write ceiling,
    protected paths, lease overlap by repository-relative path, one writer
    per checkout, tester window, and tester gate.
  - `assets/dirty-baseline.py`: shared-mode `capture` of the dirty
    baseline and snapshots, and `compare` for acceptance (`accept`) and
    the tester gates (`tester-pre`, `tester-post`).
  - `assets/commit-gate.py`: `precheck` before the implementor commits and
    `verify` after it, bound to the content the User approved.
  - `assets/gate_lib.py`: shared path, protected-path, git, and Herdr
    helpers.
- Offline tests for every refusal path in `evals/gate_cases.py`, run by
  `evals/check_package.py` with a fake Herdr.

### Changed

- The dirty baseline is now `dirty-baseline.jsonl`: paths are stored as
  base64 of their raw bytes, so names with tabs or newlines survive, and
  worktree and index state are recorded separately.
- dispatch.md has a fixed Dispatch order: precheck, pending record,
  capture, tester-pre, prompt. Assignment records carry `kind` and a
  `lease: {paths, outputs}` shape.
- The commit gate binds approval to `accept-snapshot.json` (per-path
  content ids). A file changed after approval, a stray staged path, or a
  committed blob that differs from the approved content is refused.
- `launch_verification.model_footer_text` (optional) lets the precheck
  check model drift; without it the check stays manual.

## 4.2.0 - 2026-10-23

### Added

- `assets/archive-state.py`: moves settled Assignments, their commit_log
  lines, answered questions, and old history entries from team-state.yaml
  to the append-only `<team_dir>/state-archive.yaml`. `find` looks up one
  past Assignment without reading the whole archive.
- `pending_user` in team-state.yaml: each question to the User gets an id
  and the Assignments it blocks. A report for a blocked Assignment is held
  (`deferred`) until the answer arrives. Every reply ends with the open
  questions. See dispatch.md, "5c. Waiting on the User".
- `assets/skill-version.py` and this changelog. SKILL.md carries
  `metadata.version`. Assemble records `skill_version` in team-state.yaml,
  and Status shows when a team was built with another version.

### Changed

- Handoff thresholds: a Sub-Agent writes its handoff below 40% context
  (was 25%). The Lead refreshes lead-handoff.md in full below 40% (was
  30%).
- A Sub-Agent that passes the threshold on its last sub-step writes its
  report instead of a handoff.
- The Lead waits for a settled boundary before it recommends a new
  session. Below 20% it does this at once.
- `state-archive.yaml` is a core protected path.

### Upgrade notes

- Running Sub-Agents keep their old opening instruction (25% threshold)
  until they are rebuilt by Rotate or Resume.
- Existing team-state.yaml files work as they are. The first
  `archive-state.py archive` run adds the `archive` field.

## 4.1.0 - 2026-10-22

### Added

- Optional per-role `context_roots` in team.yaml: absolute directories a
  role reads as task context, with a bounded first read at Assemble and
  versioned Assignment Inputs.

## 4.0.0 - 2026-10-08

First public release.

### Added

- Session handoff: the seven-section `handoff.md` for each role, the
  Lead-owned `lead-handoff.md`, and the Rotate workflow that replaces one
  role session while its Assignment keeps running.

## 3.0.0 - 2026-09-11

Summary rebuilt from git history.

### Added

- `assets/watch-assignment.sh`, so the Lead wakes only on outcomes it must
  act on.
- Team Templates, the rendered Role Tree, the Launcher handoff, and the
  Adjust workflow.
- Shared checkout mode (ADR 0004) as the default: one knowledge root, code
  repositories in team.yaml, one writer per checkout, and the commit gate.

## 2.0.0 - 2026-09-05

Summary rebuilt from git history and `reports/v2-evaluation.md`.

### Added

- Schema 2 team files: visible Lead identity, launch verification from
  pane headers, explicit model and effort mappings, frozen acceptance, and
  six-section reports.

## 1.0.0 - 2026-08-25

- First implementation from the approved design.
