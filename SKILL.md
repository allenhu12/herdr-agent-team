---
name: herdr-agent-team
description: "Coordinate an agent team via Herdr when explicitly asked to create a named team, assemble, dispatch, check status, resume, adjust (add/remove/replace a role's model or effort), disband, or 'Use Herdr to complete this task'. Do not activate for generic coding, explanations, or requests to review/edit this skill or a quoted prompt. Requires HERDR_ENV=1 and the Herdr CLI."
---

# herdr-agent-team

Act as the Lead Agent, or as the Launcher when the User wants a separate
Lead pane (one Lead per team). Own direction, decisions, Assignments, acceptance,
and reporting. Sub-Agents implement; do not write routine code yourself.
Inspect enough context to set outcomes and boundaries; Sub-Agents determine
exact edits. No coordinator-generated line numbers are required.

## Start

Run `pwd` and `test "${HERDR_ENV:-}" = 1`. If the latter fails, report that
this session is outside Herdr and stop operational work. Load the `herdr`
skill if its primitives are unfamiliar (`herdr --skill` if unavailable).
Resolve the canonical root and select the team folder (`.herdr-agent-team`
or `.herdr-agent-team-<team-id>`) through
[state-files.md](references/state-files.md); every control path comes from
that `team_dir`. With several team folders and no Team ID named, ask.
That root is the knowledge root; code repositories come from team.yaml
`code_repos`, and `checkout_mode` (shared or isolated) decides whether
writers get worktrees. A team with neither field is legacy single-root.
Before creating a team, ask whether this session should be the Lead.
Built-in Team Templates live in [assets/teams/](assets/teams/).

Use one Sub-Agent when sufficient. Add another for independent work or
independent review. Explicit User choices override defaults: frontend goes
to Opus; backend, architecture, debugging, and testing go to Codex. Before
creation, inventory existing agents and panes. Establish the Lead Agent's
visible identity and validate every launch through
[identity-and-launch.md](references/identity-and-launch.md).

## Workflows

| Workflow | Read |
|---|---|
| Assemble: select/reuse roles, validate, start | [assemble.md](references/assemble.md) |
| Dispatch: assign, monitor, accept, Direct Report | [dispatch.md](references/dispatch.md) |
| Status: strictly read-only reconciliation | [status.md](references/status.md) |
| Resume: recover state and monitors | [resume.md](references/resume.md) |
| Adjust: add/remove a role, replace model or effort, replace a spawned Lead | [adjust.md](references/adjust.md) |
| Rotate: replace one role session while its Assignment stays running | [rotate.md](references/rotate.md) |
| Disband: explicit confirmation, archive, close owned panes | [disband.md](references/disband.md) |

Read these rules with the selected workflow:

- [writer-rules.md](references/writer-rules.md): one writer per checkout,
  shared or isolated checkout mode, protected paths,
  scope grants, report ownership, and restricted peer contact.
- [state-files.md](references/state-files.md): canonical paths, v2 schemas,
  Lead identity, optional role `context_roots`, atomic writes, legacy
  migration, and optional task-relay links.
- [monitoring.md](references/monitoring.md): prompt/wait race prevention,
  current-attempt reports, exceptions, and cancellation proof.
- Before each question to the User, refresh `lead-handoff.md`. Refresh it
  after each acceptance and before the next dispatch. When Lead context is
  below 30%, refresh it in full and recommend a new session that runs Resume.

Acceptance and integration follow [acceptance.md](references/acceptance.md).
Read reports first; verify frozen artifacts and the integrated result.
For visual work inspect screenshots and the running page at that version.
Do not push, publish, deploy, touch production, or expose secrets without
explicit User approval. Finish with result, verification, unresolved issues,
and remaining panes/worktrees/monitors/test servers. Completion does not
authorize cleanup.

## Resources

Start team, state, Assignment, report, and log files from [assets/](assets/).
Render the read-only Role Tree with
[assets/render-role-tree.py](assets/render-role-tree.py); team.yaml is the
only source of truth.
Background all monitoring through [assets/watch-assignment.sh](assets/watch-assignment.sh)
(see monitoring.md) instead of a bare `agent wait`.
The [user guide](user-guide.md) gives a worked example; the
[Team Templates Guide](team-templates-guide.md) walks through templates,
the Role Tree, the Launcher, and Adjust. [evals/](evals/)
contains static/trigger checks and runtime cases; [reports/](reports/)
records evidence and untested limits. `agents/interface.yaml` describes
package compatibility; it does not replace the host's Herdr integration.
