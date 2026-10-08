# Adjust

Change a live team's roster or launch settings: add a role, remove a
role, replace a role's model or effort, or replace a spawned Lead. Only
the current Lead runs Adjust. A Launcher after handoff refuses it.

## Shared rules

1. **Select the team.** Resolve `team_dir` (state-files.md). Read
   team.yaml and team-state.yaml. Stop if their `team_dir` values differ.
2. **Preflight first, change second.** Adjust needs `python3` with
   PyYAML for the renderer dry run; without it, stop before any change.
   Build the resulting team.yaml in memory. Validate it with assemble.md step 3: name pattern and
   uniqueness (including other team folders), kind, explicit model,
   profile checks, effort valid for kind, launch_args, access,
   checkout layout (one source writer in shared mode), protected paths,
   and the fixed chain. Dry-run
   `assets/render-role-tree.py` on it. A failed preflight changes
   nothing: no pane stops, no file changes.
3. **Recompute the chain.** After any add, remove, or rename, rewrite
   every position from role order: role 1 `right` from `lead`, role N
   `down` from role N-1.
4. **Write together.** Update team.yaml and team-state.yaml atomically in
   the same step, then re-render `<team_dir>/role-tree.md` from the new
   team.yaml (assemble.md step 6).
5. **Busy roles are untouched.** A role is busy when it holds a running or
   blocked Assignment, a leased or dispatched pending Assignment, or its
   live `agent get` state is working or blocked. Refuse the change and say
   which Assignment must settle first. Cancelling is the User's call and
   follows the handshake in monitoring.md.

## Add a role

1. Resolve the new role like assemble.md step 2c. A `prompt_file`, if
   given, must be an absolute path to an existing file. Append the role
   to the end of the role order. Its position is `down` from the current last role, or
   `right` from `lead` if it is the only role.
2. Preflight (shared rule 2).
3. Create its checkout (none in a shared-mode team: the pane's cwd is
   the knowledge root, or the code repository for a source writer), split the pane from its chain anchor, start it,
   verify its header, and send the opening instruction (assemble.md
   steps 4a and 5).
4. Write both files and re-render.

Example: "Add a DeepSeek implementer to the dev team" resolves to kind
`codex`, model `deepseek-v4-flash`, profile `deepseek-v4-flash`, label
`deepseek`, name `dev-implementer-deepseek`. A missing or conflicting
profile fails preflight; never substitute another provider. In a
shared-mode team that already has a source writer, a new role whose
ceiling holds tracked source paths fails preflight; replace the existing
source writer's model instead.

## Remove a role

1. Refuse a busy role (shared rule 5).
2. Preflight the remaining roster with the chain recomputed. Removing the
   first role makes the second role `right` from `lead`. Removing a
   middle role anchors the next one on the previous role.
3. Stop the agent and close its pane only if `created_by_team` is true.
   Otherwise leave the pane and report it.
4. Delete the role from team.yaml. Move its state record to the archive
   with a timestamp. Queued Assignments for it stay recorded, marked
   `held: role removed`, and are listed in the report; never drop them.
5. Surviving panes keep their places. The recomputed positions describe
   the chain in team.yaml for future launches and rebuilds; they do not
   move live panes. Whether Herdr re-flows the space of a closed split is
   unverified until runtime case V2-28 runs. Report the visible layout as
   observed, and flag any gap from the fixed picture as "layout
   migration needed".
6. Write both files and re-render.

## Replace a role's model or effort

1. Refuse a busy role (shared rule 5).
2. Resolve the new model, effort, profile, and model label. The new name
   is `<task>-<role>-<new-label>`; it stays the same if the label does
   not change.
3. Preflight the resulting team.yaml. On failure the current agent keeps
   running untouched.
4. Stop the agent and close its pane. Split a new pane from the same
   chain anchor, start the agent with the new explicit arguments, and
   verify its header. On a header failure, report it, keep the role
   record with the failed evidence, and do not dispatch to it.
5. On a rename: add the old name to that role's `role_history` with a
   timestamp, move the next role's `position.from` and every queued
   Assignment's assignee to the new name, and keep the old name on
   finished Assignments. Rename the pane label to match.
6. Send the opening instruction. The agent loses its in-session memory;
   Assignment files carry the context.
7. Write both files and re-render.

To replace a role session while its Assignment remains running, use
[Rotate](rotate.md), not this quiet-role replacement procedure.

## Replace the Lead

- **Session Lead (`lead.mode: session`)**: it cannot replace itself from
  inside. Tell the User to switch the model in this session, or to start
  a new team with a spawned Lead.
- **Spawned Lead (`lead.mode: spawned`)**: only the current spawned Lead
  runs this, as the state owner.
  1. Check the team is quiet, live: no Assignment in running or blocked,
     no pending Assignment with `dispatched_at` or a lease, every role
     idle or done in `agent get`, and every monitor in state ended.
     Undispatched queued work may stay. Otherwise refuse and list what
     must settle.
  2. Preflight the candidate's kind, model, profile, effort, and
     arguments.
  3. Start the candidate in a new pane right of the current Lead pane,
     with no ownership: do not write its identity into `lead` yet.
     Verify its header. On any failure, close the candidate pane and
     keep the current mapping.
  4. After verification, in one atomic write: move the current Lead's
     identity to `lead_history`, write the candidate's full identity
     into `lead` with `handoff_at`, and update the effective `lead`
     fields in team.yaml. Re-render the Role Tree. Finish every write.
  5. Send the new Lead: the absolute SKILL.md path, `team_dir`, and "You
     are the Lead Agent <name> and own this team. Load the skill and run
     Resume." Then stop writing team files.
  6. If that prompt fails to deliver, retry or report it. Never take
     ownership back automatically. The old Lead pane stays open; closing
     it is the User's call.

## Report

Show what changed, the new Role Tree, any role refused as busy, any
held queued work, and any pane that was kept because the team did not
create it.
