# Dispatch

Hand one Sub-Agent an Assignment, and see it through to acceptance. See
`monitoring.md` for the wake-up mechanism and exception branches this
workflow relies on, and `state-files.md` for the Assignment lifecycle and
schema.

## 1. Busy check

First verify the Lead mapping, role ownership, live configuration/header,
and checkout identity under identity-and-launch.md. Read legacy migration
rules before issuing work from old state. Keep the smallest sufficient team;
do not create an extra role for an Assignment a compatible idle role can do.

**Model check before every prompt.** A CLI can change its own model
between turns (runtime finding 11: Codex switched gpt-5.6-sol to
gpt-5.6-luna with no agent action). Before each work prompt (dispatch,
rework, commit request), read the pane's last lines
(`herdr agent read <role> --lines 3`) and compare the model and effort
shown there with the role's recorded model and effort. On a mismatch,
send nothing, record the drift in team-state.yaml, and ask the User:
switch it back, accept the new model, or replace the role (adjust.md).
Opening and window notices that ask for no work do not need the check.

Look up the target role in `team-state.yaml`. If it already holds an active
Assignment (`assignment_status` in `pending`/`running`/`blocked`), reject the
dispatch outright — don't queue by overwriting. Record the new work as
queued in `team-state.yaml` if the User wants it held for later instead.

A queued pending record with dispatched_at null and no lease is not active.
Selecting that record is allowed once the role is free. Pending rework of
the same ID is also allowed after its previous attempt has stopped, its
lease is revoked, and its monitor removed. Do not reject the Assignment
against its own pending rework record. A live working/blocked role is still
busy regardless of these bookkeeping exceptions.

The book alone isn't sufficient — a role can be busy for reasons
`team-state.yaml` doesn't know about, e.g. an authorized peer message or
direct manual interaction. Also `agent get <role-name>` for the live state
before dispatching:

- `idle` / `done` → clear to dispatch.
- `working` → treat as busy the same as an active Assignment: reject or
  queue, same as above.
- `blocked` → don't dispatch new work over an open question; route through
  the `blocked` branch in `monitoring.md` first.
- `unknown` → don't dispatch blind; `agent read` to see what's actually
  happening before deciding.

## 2. Write assignment.md before sending anything

Before creating the Assignment or prompting, reject a requested scope outside
the role ceiling, a logical path overlap with an active lease, or a second
writer sharing a checkout/index (in shared mode: a second source writer, or
source work while a tester window is open; see step 2a). Validate the base commit and repository
(or hashed non-git snapshot), preserve dirty User changes, and ensure the
Checkout Dir is at the intended starting version. Never reset it blindly.
Read-only review names the exact target version and grants no source writes.
Reject a lease that overlaps a protected path (writer-rules.md, "Protected
paths").

### 2a. Code repositories in a shared-mode team

When the Assignment touches any `code_repos` entry under `checkout_mode:
shared`, do these before writing `assignment.md`:

1. **Input SHAs.** For each touched repository record `{name, input_sha:
   <git -C path rev-parse HEAD>, result_sha: null}` in the Assignment's
   `repositories` list in team-state.yaml.
2. **Dirty baseline.** List every dirty or untracked path, file by file:

   ```bash
   git -C "<repo path>" status --porcelain=v1 -z --untracked-files=all
   ```

   For each path write one line to
   `<workspace>/artifacts/attempt-<n>/dirty-baseline.tsv`: repository
   name, path, status code, worktree hash (`git hash-object`, or `deleted`),
   and index blob id (from `git ls-files -s -- <path>`, or `none`). Record
   the file's absolute path as the Assignment's `dirty_baseline`. These are
   mechanical commands; do not read file contents.
3. **Snapshot dirty in-scope files.** A dirty path inside the write scope
   does not block dispatch. Copy each one to
   `<workspace>/artifacts/attempt-<n>/snapshots/<repo name>/<path>` so
   acceptance can separate the Sub-Agent's lines from earlier ones. Mark
   these paths `dirty_at_dispatch` in the Assignment. Dirty paths outside
   the scope stay as they are. Nothing is committed without the commit
   gate (acceptance.md), so earlier unsaved work never enters git unseen.
4. **Tester gate.** A tester Assignment needs, for every repository it
   tests: a `HEAD` recorded in `commit_log` (an accepted implementor
   commit with its `result_sha`, or a User-confirmed commit, below),
   the implementor idle with no background process left (the cancellation
   proof in monitoring.md), and no implementor source Assignment pending or
   running. Then run the pre-test gate: `HEAD` equals that SHA, and the
   porcelain output and dirty baseline match their recorded values. Any
   miss rejects the dispatch. The tester's lease holds only its declared
   generated/cache/output paths, and its verification commands carry an
   explicit cwd per repository.
5. **No commit during work.** The implementor's Assignment says: edit,
   do not commit, and list the changed files per repository in the report.
   The commit happens only after acceptance and the commit gate
   (acceptance.md, "Commit gate").
6. **During the tester window.** Do not dispatch source work to the
   implementor until the tester's Assignment settles. An authorized peer
   request that reaches the implementor meanwhile is logged, not acted on.
   The implementor cannot see the window by itself, so tell it: just
   before the tester prompt, send the idle implementor one line, "Tester
   window open for <tester id>. Edit no source. Log any code request in
   <implementor's last Assignment log.md> and do not act on it." When the
   tester Assignment settles, send "Tester window closed." Relay logged
   requests through a normal Assignment.

Create `<team_dir>/assignments/<id>/` (new id, or same id with `attempt` incremented for
rework) and write `assignment.md` from `assets/assignment.md.template`:
description, acceptance criteria, write scope (role ceiling ∩ this lease —
see `writer-rules.md`), partner authorizations if any, related-doc paths, and
the attempt number. Fill its Inputs section: the upstream report paths with
attempt numbers, one `<repo name>@<input_sha>` line per code repository, and
the knowledge documents it depends on with their mtime or hash. Inputs do not
change within an attempt. Include one deliverable, immutable starting version,
absolute checkout/control paths, exclusions, verification commands with cwd,
and final artifact format. Let the Sub-Agent inspect code and choose exact
edits; do not read every file to supply line numbers.

For a task that uses a role's declared `context_roots`, first verify each
needed directory still exists. Freeze each used root in Inputs as
`context: <absolute root>@<git HEAD SHA or snapshot hash>`; if a checkout
is dirty, also record hashes for selected files. For a non-Git root, use
a SHA-256 manifest of the selected files as the snapshot hash. Put only the files needed
for this attempt in Related Docs, as absolute paths. Tell the role to read
those files before context-dependent access or test commands. Do not copy
source text, secrets, or transcripts into the Assignment. Aim to keep the
selected read small; if it exceeds about 32 KB, record why in the log.
For unrelated work, omit the root. If a required path is missing, keep
existing work intact and block the new dispatch until the path is fixed or
the User gives an explicit alternative. A context root alone grants no
permission to run a device command. Compare a later root version change
with frozen Inputs using the late-signal procedure in step 5b.

**This file must exist on disk before the prompt is
sent** — the prompt itself is nothing more than "go read your
assignment.md," so a restart can always recover the original ask from disk
without relying on the Lead Agent's memory.

Also initialize `log.md` from `assets/log.md.template` at the same time
(first attempt only — a rework keeps the existing `log.md`). `assignment.md`
stays Lead-Agent-owned for the life of the Assignment; the Sub-Agent writes
only `log.md`, `report.md`, `handoff.md`, optional `status.json`, and
explicitly granted versioned control outputs (see `writer-rules.md`). All
control paths are absolute, built from `team_dir`
(state-files.md), not relative to a writer checkout and never the literal
default folder name. With several teams at one root, a Lead creates
Assignments only under its own `team_dir`.

## 3. Send the prompt through the watcher — one call, not two

Do not split this into a fire-and-forget `agent prompt` followed by a
separate `agent wait`: a bare `agent wait` started right after can simply
observe the Sub-Agent's *pre-existing* idle state and return immediately,
before the prompt has even taken effect — a false "done" with no work done
at all. The watcher's opening move (`agent prompt ... --wait`) avoids this
by design: Herdr requires an observed lifecycle change within five seconds
of a prompt sent from a non-working state, or it returns
`agent_prompt_stalled`, which the watcher surfaces as its own `stalled`
outcome instead of settling falsely (see the `herdr` skill and
`monitoring.md`).

So the monitor **is** `skill/assets/watch-assignment.sh`, backgrounded as
one unit, with the opening prompt as its last argument:

```bash
skill/assets/watch-assignment.sh <role-name> <absolute-workspace-dir> <attempt> <deadline-s> \
  "Read '<absolute-workspace-dir>/assignment.md' and work from there. Write '<absolute-workspace-dir>/report.md' when done."
```

The script sends that prompt, then loops silently and exits exactly once —
on `report`, `blocked` held past 20s, `unknown` held past 60s, `gone`,
`stalled`, `no_report`, or `timeout` — instead of waking the Lead on every
intermediate state. See `monitoring.md`'s outcome table for what each one
means and what to do about it. Ordinary in-scope permission prompts don't
even reach this list when the Sub-Agent's CLI does not prompt for them:
either the User's own config allows them (`permissions: inherit`) or the
scoped arguments pre-authorize them (`permissions: scoped`); see
`identity-and-launch.md`.

Default path — dispatching alongside other active work — run this exact
command through the host's own background-task facility (see
`monitoring.md`) and register its handle in `team-state.yaml`'s `monitors`
list immediately, so no window exists where the Sub-Agent is working and
nothing is watching it.

Only when this is the sole active Assignment and the Lead Agent has nothing
else to do meanwhile, run the same command in the foreground instead — no
background monitor needed, and go straight to the acceptance protocol below
once it returns.

## 4. Update state

- Set `assignment_status: running`, `expected_agent_state: working` in
  `team-state.yaml`.
- Record dispatch once the prompt is sent. If a foreground call returns
  after work has settled, reconcile its result directly; do not overwrite a
  completed acceptance with a stale running state.
- Confirm the monitor registration (assignment id, attempt, assignee, task
  handle) landed in `team-state.yaml`'s `monitors` list when using a background
  monitor. Foreground-only dispatch has no monitor entry.
- The Lead Agent continues other work; acceptance happens on wake-up.

## 5. Acceptance protocol (triggered by a monitoring wake-up)

An outcome from the watcher is only a signal to go check — never proof by
itself (see `monitoring.md`). On a `report` outcome:

0. Check `pending_user` first. If an `open` entry lists this Assignment in
   `blocks`, follow "5c. Waiting on the User" and stop here.
1. Read the recorded absolute `report_path` first and confirm the Assignment
   id and current `attempt`. It is in the canonical Workspace Dir.
2. **Missing** → not actually done; treat as stuck and follow the "stuck"
   branch in `monitoring.md` (`agent read` to see what's on screen).
3. **Present** → follow acceptance.md: verify the frozen artifact, scope,
   tests, visual evidence, and any required independent review. A `failed`
   report does not pass merely because it exists.
   If the report says work is incomplete, the Lead may read the bottom line
   of the role pane for its context figure; treat it as a hint only.
   - **Pass**: set `assignment_status: succeeded`, update
     `expected_agent_state: idle`, record the accepted artifact and finished_at,
     revoke the lease and remove its completed monitor. Summarize the outcome
     (point to report and pane). This is Assignment acceptance, not final
     integration success; apply acceptance.md before final sign-off. Refresh
     `<team_dir>/lead-handoff.md` atomically before the next dispatch. If
     task-relay is in use, add one pointer line to `progress.log`. Read the
     handoff's Gotchas and move general-value items to `memory.md` through
     Lead-only task-relay memory capture.
   - **Fail, below the cap**: send "Write your handoff now, then stop."
     and wait through the watcher for `handoff` before rework. Archive the
     prior report and handoff under `artifacts/attempt-<n>/`,
     then append the gap to `assignment.md`. Complete the stop/proof and lease-release steps below,
     then increment `attempt`, set `assignment_status: pending`, and re-dispatch (go back to
     step 1 of this workflow with the same id). Cap at `max_attempts: 3` —
     first try plus at most two reworks. Exhausting the cap means escalate
     to the User rather than trying a fourth time.

`blocked`, timeout, and `unknown` wake-ups are handled entirely by the
exception routing table in `monitoring.md` — don't duplicate that logic here.

For rework, preserve the stable ID, log, and prior frozen artifacts; archive
the old report under its attempt before replacing it. Stop any remaining
turn/process through monitoring.md's handshake and remove the old monitor
before renewing the lease. Check all changes across the original base-to-result
range at acceptance, even if the new attempt starts from the prior result SHA.
An explicit cancellation/replacement is a fresh Assignment; an acceptance
rework keeps the same ID. At the cap, mark failed, revoke the settled lease,
remove its monitor, record finished_at, and escalate instead of attempt 4.

## 5b. Late signals

The Lead sees signals one turn at a time, so a signal can arrive after a
dispatch it should have shaped. Judge it by its content, not its sender:

- **Version or status signal only** (a new commit, a report's attempt
  number, an updated document, a state change): compare it mechanically
  with the running Assignments' Inputs. Unchanged: ignore it and keep
  waiting. Changed: run the cancel/redirect/re-dispatch handshake in
  monitoring.md, increment the attempt, and rewrite Inputs.
  In a shared-mode code repository, a new commit that is not in
  `commit_log` is an unknown commit (the User, another tool, or a member
  that broke the commit gate). After the handshake, tell the User the
  repository, SHA, and changed files, and wait. If the User accepts it,
  add it to `commit_log` with `approved_by: user` and use it as the new
  input; the tester gate then passes on it. If not, the User handles it;
  the Lead never reverts or resets it.
- **Message with new content** (from the User, a peer message, a log entry,
  or a report): read it and decide against the running Assignment's
  Outcome, Write Scope, and Acceptance Criteria. If it changes any of them,
  run the same handshake and append a rework note to `assignment.md`.
  Otherwise keep waiting. Never ignore a User correction just because no
  recorded version moved.

The Lead spends tokens on this only when new content arrives.

## 5c. Waiting on the User

The Lead often waits for a User answer while reports keep arriving. A
report must not push the open question out of the Lead's attention, and
acceptance must not decide what the answer could change.

1. **Record every question.** Before each question the User must answer
   for work to go on, add one `pending_user` entry: the next `q-<n>`
   (increment `user_question_seq`), asked_at, the question in one line,
   `blocks` (each Assignment whose Outcome, Scope, acceptance, commit, or
   next dispatch the answer can change; may be empty), and
   `status: open`. Show the id with the question. Then refresh
   `lead-handoff.md`. The commit gate's question gets an entry too.
2. **Hold blocked reports.** When a `report` arrives for an Assignment in
   an open entry's `blocks`, check only that `report.md` exists for the
   current attempt. Do not read the rest. Record `deferred` on the
   Assignment, remove its finished monitor, and keep
   `assignment_status: running`. Do not accept, fail, commit, rework,
   or dispatch dependent work. Tell the User in one line that the report
   is held for `q-<n>`.
3. **Independent reports go on.** A report for an Assignment in no open
   entry's `blocks` follows step 5 as usual. Do not take any step there
   that changes a blocked Assignment.
4. **Repeat the open question.** While any entry is `open`, end every
   reply to the User with one line per entry: "Waiting on you: q-<n> —
   <question>". This holds after acceptance work too.
5. **Match the answer.** On a User message, read `pending_user` first and
   match the message to an entry by id or content. If it is unclear which
   question it answers, ask; do not guess. Record `status: answered`,
   answered_at, and the answer in one line. Apply it through 5b if it
   changes a running Assignment. Then run step 5 for each Assignment
   whose `deferred.question` is this id, and clear `deferred`. A deferred
   report stays valid only for its `report_attempt`.
6. **Leave settled entries to the archive.** `archive-state.py` moves an
   answered entry once no Assignment names it in `deferred`.

## 6. Direct Report

If the User's original instruction explicitly asked for a given role to
"report directly," that role's `report.md` is presented **verbatim** to the
User at acceptance time instead of being summarized: no rewriting, no
compressing, and no forwarding its content into any other Sub-Agent's
context. Still tell the User which pane holds that role, so they can look at
the live session themselves.

This is a verbatim-presentation mode, not a confidentiality mechanism —
`report.md` still lives in the ordinary Assignment workspace dir, and any
other Sub-Agent can technically read it under the normal "reads are
unrestricted" rule (see `writer-rules.md`). If the User needs an actually
confidential channel, that requires a separate restricted directory excluded
from the open-read rule — not supported by this skill; say so if asked.
