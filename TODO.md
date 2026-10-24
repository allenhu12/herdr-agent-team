# herdr-agent-team — future work

Ideas for later versions. Nothing here is scheduled or approved for
implementation — this is a holding pen for design decisions worth
remembering.

## Done: multiple teams in one project

Decided in `docs/adr/0003-one-team-per-suffixed-folder.md` and built on
branch `feature/agent-role-tree`: one team per `.herdr-agent-team` or
`.herdr-agent-team-<team-id>` folder, a recorded `team_dir`, and a
cross-team name check.

## Per-role prompt files and skill loading

**Why:** each role in a Team Template should get its own instructions and
skills. The schema hook exists now: `prompt_file` is appended to the
opening instruction, and `skills` is only mentioned by name.

**Open questions:**

1. How to load a named skill per CLI kind (Codex vs Claude Code) at
   launch, not just mention it.
2. Where shared prompt files live when two templates reuse one role.
3. Whether a prompt file change should force a role restart.

**Not started.**

## Team-level watcher and durable wake queue

**Why:** today each Assignment has its own background watcher, and a Lead
restart loses every watcher's pending result until Resume re-arms them.

**Sketch:** each Sub-Agent appends events (`report`, `handoff`, `blocked:`,
`paused:`) to `<team_dir>/assignments/<id>/events.log`. One team-level
watcher scans every events.log, report.md, and Herdr state, writes each
event the Lead must act on to `<team_dir>/wake-queue/NNN.wake`, and wakes
the Lead once. The Lead acknowledges with `ack --through <seq>` after
handling; an interrupted turn replays the queue (handling must be
idempotent). Resume then only checks the watcher is alive and drains the
queue.

**Not now:** it rewrites most of monitoring.md and resume.md and the
watcher's output contract, and the runtime evidence in `reports/` would
need re-running. Herdr has no push events, so the Lead still wakes through
the host's background-task notification.

**Revisit when** a Lead restart or session break loses a watcher result
that someone had to notice by hand, when five or more Assignments usually
run at once, or when inbox messages need one scheduler across Assignments.

**Not started.**

## Done: archive team-state.yaml history

`assets/archive-state.py` moves settled Assignments, their commit_log
lines, and old history entries to `<team_dir>/state-archive.yaml`. See
state-files.md, "Archive settled history".
