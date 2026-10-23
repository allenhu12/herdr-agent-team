# Changelog

One section per version, newest first. The top version must equal
`metadata.version` in SKILL.md (`evals/check_package.py` checks this).
Check the version you use with `python3 assets/skill-version.py`.

Version numbers: a change to rules or workflows raises the middle number;
a wording or fix-only change raises the last number. A change that needs
new team files or breaks old ones raises the first number.
`schema_version` in team.yaml and team-state.yaml is a different number:
it is the state file format, and it stays 2.

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
