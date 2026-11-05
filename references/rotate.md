# Rotate

Replace one Sub-Agent session while its Assignment stays `running`. Only the
Lead runs Rotate. The Assignment ID, attempt, checkout, lease, and accepted
history stay unchanged.

## 1. Validate the handoff

1. Read the role's Assignment and current `attempt` from team-state.yaml.
2. Verify `<team_dir>/assignments/<id>/handoff.md` exists and its Attempt
   equals the Assignment attempt. If not, send the role
   "Write your handoff now, then stop." (by the role's `steering`,
   monitoring.md "Steering") and wait through the watcher for
   `handoff`. If the role is gone, use Resume's "Gone" branch.
3. Check all seven sections. Do not rotate during an unsaved edit or running
   test. Confirm the role is idle after its final checkpoint.
4. Read Gotchas. If task-relay is used, capture general-value items in
   `<project_root>/00-current/memory.md` through the Lead's memory capture.

## 2. Stop the old session

Stop the old pane's agent. Keep its pane open read-only until the new role
confirms its first action; then close it if it was created by the team.
Never stop or close a foreign pane. Preserve the Assignment workspace,
checkout, log, report, and handoff.

## 3. Rebuild the same role

Use Assemble steps 3–5, including preflight, pane ownership checks, launch,
and exact header verification. Keep the same role name, kind, model, effort,
profile, and checkout. Do not create a new Assignment or change its lease.
For configured `context_roots`, complete the bounded read after READY.
Compare current root versions with the running Assignment's frozen Inputs.
If a root changed or disappeared, follow Dispatch's late-signal procedure
before continuing; preserve the Assignment workspace and evidence.

Send this continuation through `watch-assignment.sh` as its fifth argument:

> You are `<role>`. Read `<absolute-workspace-dir>/assignment.md`,
> `<absolute-workspace-dir>/handoff.md`, and the entries after the last
> `## checkpoint` in `<absolute-workspace-dir>/log.md`. Start with the first
> action in handoff.md. Do not redo
> what handoff.md lists as done.

All paths in the actual prompt must be absolute paths built from `team_dir`.
Register the new monitor handle; remove the old handle. Keep the pane open
read-only until the new role confirms it took the first action from the
handoff. After starting the watcher, check the new role's live state and
read its screen if needed to confirm that first action before closing the
old pane.

## 4. Record and report

Atomically update team-state.yaml with the new `pane_id`, `process_identity`,
and `launch_verification`. Append a role `rotations` entry with `at`,
`reason`, and `handoff_path`. Replace the monitor handle while preserving
the running Assignment and its attempt. Refresh `lead-handoff.md` before
the next dispatch.

If task-relay is used, append one line to
`<project_root>/20-working/<ITEM>/log.md`:
`role <name> rotated at <time>; handoff at <path>`.
Report the rotation and retained Assignment to the User. Do not treat the
handoff as a completed report.

Lead rotation is not this workflow. See "Lead context handoff".

## Lead context handoff

Use this at the trigger in state-files.md ("lead-handoff.md"). Do not ask the
User first; tell the User in one line.

**Claude Code Lead: use `/compact`. Do not use `/clear`.** `/compact` keeps a
summary, the session id, the Herdr agent name, and running watchers. `/clear`
loses the context and the agent name.

1. Reach a settled boundary. Refresh `lead-handoff.md` in full.
2. Start the helper detached, with the Lead's pane id:
   `nohup python3 <skill-dir>/assets/lead-compact.py <pane-id> <lead-name> <team-dir> &`
3. End the turn. A slash command cannot run inside a working turn.
4. After the continue prompt arrives, read `lead-handoff.md`, newest block
   first. Check `<team-dir>/lead-compact.log` and `herdr agent get <lead-name>`.
   Re-arm any stopped watcher with no prompt. Do not run full Resume unless
   the session was lost.

If the helper does not act, ask the User to type `/compact`.

**Any other Lead kind** (not tested with this helper): the User opens a new
session and runs Resume, which reads `lead-handoff.md` before team-state.yaml.
