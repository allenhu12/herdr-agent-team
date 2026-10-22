# Resume

Reattach after a Lead Agent restart. Panes and Sub-Agents can very well
still be alive when the Lead Agent restarts — what's actually lost is the
Lead Agent's own memory and its background monitor handles. Everything
needed to recover must come from files, never memory, and step 2 below is
what confirms whether a still-alive agent is genuinely safe to reattach to.

## 1. Read state

- Select the team folder and `team_dir` (state-files.md). If
  `<team_dir>/lead-handoff.md` exists, read it first. Then read
  `<team_dir>/team.yaml` (static definition) and
  `<team_dir>/team-state.yaml` (last known snapshot). Stop if their
  `team_dir` values differ.
- When the project uses task-relay, read its `progress.log` after
  team-state.yaml. A task left `in_progress` there must match a running
  Assignment with the rotated role on the team side.
- `herdr agent list` to see what's actually alive right now.
- `herdr pane list` and the current pane to validate the Lead's identity and
  succession through identity-and-launch.md. Do not overwrite a live Lead's
  mapping or rename an unrelated pane. Read legacy migration in state-files.md.
- Spawned Lead taking over: this session's verified pane equals
  `lead.pane_id`, and `lead.launched_by_team` is true or a handoff record
  names this session. That is valid succession. Record `handoff_at` if it
  is missing; add no `lead_history` entry for the first spawned Lead. A
  live Launcher pane is not a competing Lead and is never closed here.
- This session matches a `launcher` record whose `handoff_at` is set:
  refuse, name the Lead pane, and stop. The Launcher does not resume.

## 2. Joint validation, per role

A live agent only counts as "still ours" if **all** of these match the
`team-state.yaml` record: role name, live pane id, agent kind, cwd. Any
single mismatch means treat it as invalid — never reuse it and never assume
it's the same agent just because the name matches.

For v2 also verify process_identity, recorded real checkout/index identity,
and intended model/profile/effort against current header evidence. A restarted
process invalidates launch_verification. Missing configuration evidence is a
dispatch gate, not permission to destroy a live pane. Reconcile/monitor
existing work, but send no new/continuation prompt until verified. Validate
one writer per checkout (writer-rules.md) before continuation. Legacy working roles may
finish under their existing leases; never forcibly rename them for v2.

Two failure shapes, handled differently:

- **Gone** (pane closed, agent exited): rebuild the role from scratch using
  Assemble's pane-split/agent-start/opening-instruction sequence
  (`assemble.md` steps 3–5, including preflight and header verification).
  If it has `context_roots`, perform Assemble's bounded read after READY.
  Verify and reuse its recorded checkout; do not discard interrupted edits
  or recreate it from the original base. If missing, inspect frozen artifacts
  and logs and report any unrecoverable uncommitted work before continuing.
- **Alive but validation failed** (e.g. something else is squatting the role
  name, so Herdr's name-uniqueness rule blocks a rebuild): **quarantine**.
  Escalate to the User — stop, start, or rename the conflicting agent is
  their call. Do not attempt to rebuild that role until the User resolves
  it.

Roles that are alive and pass validation are left untouched — resume never
recreates something that's already correctly in place.
For an idle role whose context configuration changed, use Assemble's
bounded reminder before its next context-dependent dispatch. Do not prompt
a working role to refresh context.

## 3. Continuation instruction and watcher, together

**First, roles with no dispatched Assignment.** A role counts as having
dispatched work only when it holds an Assignment in running or blocked,
or a pending record with `dispatched_at` set or an active lease. A role
with none of these (a fresh team after Launcher handoff, or a role whose
work is all terminal or only queued) is verified as in step 2, left
idle, and gets no prompt and no watcher. Queued records stay queued for a
later Dispatch. Settled terminal reports that still await acceptance go
to Dispatch's acceptance protocol, not to a continuation prompt. Apply
the branches below only to roles with dispatched work.

Before sending anything, `agent get` the role to check its live state — a
still-alive Sub-Agent may already be mid-turn from before the restart. For
each branch that arms a watcher, register its host task handle in
`team-state.yaml`'s monitors list (see step 4 for the replace-not-append
rule). Acceptance, unresolved blocked questions, or unverified settled
roles may leave no monitor. Treat sending a prompt and arming its watcher
as one unit, same as in `dispatch.md`, so no window opens where work
resumes unwatched.

- **Rebuilt, or already-alive and settled (idle/done)**: first check
  recorded absolute `report_path` for the current `attempt` —
  it may already have been written before the restart, in which case skip
  straight to the acceptance protocol in `dispatch.md` instead of sending a
  continuation prompt at all. Otherwise, recheck the configuration/checkout
  gates before backgrounding a continuation prompt. If unverified, record
  the unresolved gate and send nothing. For an Assignment with frozen
  context Inputs, compare each current root version with the recorded
  version before continuation. A change follows
  Dispatch's late-signal procedure; a missing root blocks continuation
  without discarding the Assignment or pane. Then run
  `watch-assignment.sh` with the
  continuation prompt as its fifth argument, exactly like a fresh dispatch
  — the script's opening move is `agent prompt --wait` as one call, never a
  bare separate `agent wait`, for the same idle-race reason described in
  `monitoring.md`:
  `skill/assets/watch-assignment.sh <role-name> <absolute-workspace-dir>
  <attempt> <deadline-s> "You are <role>. Read
  '<absolute-workspace-dir>/assignment.md',
  '<absolute-workspace-dir>/handoff.md', and the entries after the last
  '## checkpoint' in '<absolute-workspace-dir>/log.md'. Start with the first
  action in handoff.md. Do not redo what handoff.md lists as done."`,
  backgrounded through the host facility. If no current-attempt handoff
  exists, use the assignment/log continuation and report the gap.
- **Already-alive and `working`**: don't prompt it — interrupting a live
  turn with an unrelated continuation message is exactly the kind of
  interleaving the `herdr` skill warns against. Run `watch-assignment.sh`
  with **no** fifth argument instead (backgrounded the same way) — it
  starts straight into its polling loop with a bare `agent wait` internally
  and lets the current turn finish naturally; the next wake-up carries one
  of the outcomes in `monitoring.md`'s table and routes to the normal
  acceptance protocol or exception routing.
- **Already-alive and `blocked`**: do **not** arm the watcher here —
  `blocked` is one of `agent wait`'s default settled states, so a watcher
  started while already blocked would exit on `blocked` immediately without
  ever holding it the required 20 seconds, achieving nothing. Resolve the
  block first, synchronously, following the `blocked` branch in
  `monitoring.md` (`agent read`, answer if pre-authorized and in scope, else
  escalate to the User). Only once the role has actually moved off
  `blocked` — because you answered it and it resumed working, or the User's
  guidance let it proceed — arm the watcher at that point, using whichever
  of the two patterns above fits the state it's now in. If it's still
  `blocked` pending the User's answer when this workflow finishes, leave no
  monitor armed for it and flag it in the report (step 4) as awaiting the
  User — a later Status or Resume pass will pick it up.
- **Already-alive and `unknown`**: `agent read` to see what's actually on
  screen; if it settles into a recognizable state, handle it per that
  state's branch above. If it stays genuinely unclassifiable, escalate to
  the User rather than guessing. Unlike `blocked`, `unknown` is *not* one of
  `agent wait`'s default settled states, so arming the watcher for it here
  is safe — it holds `unknown` for 60 seconds before surfacing it as its own
  outcome, matching the `unknown` handling in `monitoring.md`.

## 4. Update state and report

- Every entry in `team-state.yaml`'s `monitors` list from before the restart
  refers to a host background task that's gone — **replace the whole list**
  with the monitors armed in step 3, don't append to it, so no dead handle
  from the old session can later be mistaken for a live one.
- Update `team-state.yaml` to reflect the current reality (pane ids may have
  changed on rebuild).
- Report to the User: who resumed in place, who was rebuilt, who is
  quarantined pending a role-name conflict decision, and who is still
  `blocked` awaiting an answer.
- Include Lead name → pane, unresolved launch/migration gates, and remaining
  checkouts/monitors/servers. Refresh the Lead mapping only after verified
  succession; Sub-Agents locate it through the canonical state path.
