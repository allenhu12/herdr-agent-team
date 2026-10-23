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

## Done: archive team-state.yaml history

`assets/archive-state.py` moves settled Assignments, their commit_log
lines, and old history entries to `<team_dir>/state-archive.yaml`. See
state-files.md, "Archive settled history".
