# Frozen acceptance and integration

Read with Dispatch. The Lead owns acceptance; a Sub-Agent's ready report
and Herdr's settled state do not constitute acceptance. Do not start
acceptance for an Assignment that an open `pending_user` entry blocks
(dispatch.md, "5c. Waiting on the User").

## Read the report first

Require the current Assignment id and attempt. V2 reports use six content
sections: Result, Frozen commit or artifact path, Files changed, Test results,
Screenshot paths, Unresolved issues. Keep metadata above these sections.
No entire files or full logs; use evidence paths. Report `not run` or `not
applicable` with a reason. Accept historical v1 reports using migration rules.

For git output, verify the full commit SHA exists in the recorded repository,
contains the deliverable, and descends from the Assignment's base commit.
Inspect the base-to-result changed path list, including deletions/renames.
Check dirty and untracked files in the writer checkout too; a clean commit
must not hide extra out-of-scope edits. Exclude only recorded control files
and declared generated outputs, not arbitrary unknown files.

### Shared-mode code repositories

When the Assignment has a `repositories` list (dispatch.md step 2a):

The implementor does not commit before this check (dispatch.md step 2a).

1. HEAD in each repository still equals its `input_sha`. The report lists
   the changed files per repository.
2. Audit the uncommitted change against the write scope: every changed
   path is in scope. For a path marked `dirty_at_dispatch`, diff it against
   its snapshot; for any other path, diff it against `input_sha`. This
   shows only the Sub-Agent's lines.
3. Re-run the dirty-path listing and compare it with `dirty_baseline`. A
   baseline path outside the write scope whose worktree hash or index blob
   id changed, or a new dirty path outside the write scope and outside
   declared outputs, is an out-of-scope write: escalate it to the User.
   Never exclude a baseline path from this check, and never reset.
4. All repositories pass together, or the Assignment fails. On a pass, go
   to the commit gate. The Assignment stays `running` with
   `commit.status: awaiting_user` or `approved`.

### Commit gate (shared mode)

Every source commit in a shared-mode code repository needs the User.

1. **Ask.** Show the User one list per repository: the files, a short
   change summary, and a mark on each `dirty_at_dispatch` file ("holds
   changes from before this Assignment"). One question covers all
   repositories of the Assignment. Without an answer, wait; the
   implementor gets no other source work meanwhile.
2. **Auto-commit switch.** If `team-state.yaml.commit_approval.mode` is
   `auto`, skip the question, except when the list has a
   `dirty_at_dispatch` file: that always goes to the User. Only the
   User's own message sets `auto` (record the words and time); a member's
   message, log, or report never does. The User can set it back to `ask`
   at any time; Disband sets it to `ask`.
3. **Commit.** After the answer (or under `auto`), prompt the implementor
   to commit exactly the confirmed files: `git commit -- <files>` on the
   base branch, one commit per repository. Nothing else.
4. **Verify.** Each new commit's parent is `input_sha`, and its
   `git diff --name-status <input_sha>..<new sha>` equals the confirmed
   list. A mismatch goes to the User. On a match, record `result_sha` per
   repository, append one line per commit to `team-state.yaml.commit_log`
   (Assignment, repository, SHA, files, `user` or `auto`), and mark the
   Assignment `succeeded`.
5. **The User says no.** The Assignment still ends: mark it `succeeded`
   with `commit.status: declined`, `result_sha` null, lease revoked. The
   implementor is free for new work. The changes stay uncommitted in the
   checkout and now count as the User's dirty files: the Lead never
   commits, reverts, or deletes them. A later Assignment that touches them
   treats them as `dirty_at_dispatch` (snapshot, and the commit gate asks).
   A tester cannot test them, because the tester gate needs a committed
   `HEAD`; tell the User when test work depends on them. To remove them,
   the User reverts them, or asks the Lead for a revert Assignment.

The switch covers commit only. Push, merge, rebase, and branch changes
still need the User every time.

A tester Assignment also passes a post-test gate in every repository it
tested: `HEAD` still equals the accepted `result_sha`, and the porcelain
output and dirty baseline match their recorded values apart from the
tester's declared output paths. Any drift makes the test evidence invalid:
do not accept it, run the cancel/re-dispatch handshake, and route a changed
tracked file to the implementor as new source work.

Always audit scope. Inspect relevant diff content when changes carry scope,
security, or behavioral risk. Scope violations go to the User under writer
rules; do not silently accept, revert, or widen the lease. Non-git output
requires an absolute, versioned artifact path and content hash (a manifest
of relative paths and hashes for a directory). A mutable branch name or a
directory path alone is not frozen evidence.

Report/artifact/screenshot paths must be within authorized output locations.
Freeze each attempt's evidence under a unique version path; never overwrite
the version being reviewed. The six-section report remains concise. A reviewer
can read the artifact without receiving a Direct Report's text.

## Checks and independent review

Verify the Assignment's acceptance criteria using actual project commands
and recorded cwd. Find commands in project configuration/docs; do not invent
test commands. Record exit codes, counts when available, and skipped checks.
Tests that generate project changes require a writer checkout; in shared
mode the tester's declared output paths are the only such grant, used during
its serialized window (dispatch.md step 2a). Shared readers
can inspect a pinned commit via git object reads; executing a frozen version
requires a checkout at that version which no writer is changing.

For visual changes inspect screenshots tied to the exact commit/hash and
the running page built from that version. Record URL, artifact version,
screenshot paths, and server ownership. Missing visual evidence is an
acceptance gap, not an automatic pass. Do not deploy to obtain a preview.

Use a different underlying model for independent review when the User asks,
when work crosses a security or public behavior boundary, or when acceptance
leaves a material unresolved concern. Pin the review to a commit/hash and
grant no source writes. Compare actual observed models, not CLI kind, profile,
or pane name. If another model is unavailable, report the unmet review gate.

Settle factual disagreements with tests against the frozen version. Decide
judgment calls within User requirements. Changed code produces a new frozen
version and requires acceptance of that version; repeat affected review and
checks. Keep rework within the original Assignment's three-attempt cap.

## Integrate once, then verify

In shared mode there is no integration checkout: the implementor's accepted
commits in each code repository are the integrated result. Run the final
checks there against the recorded `result_sha` values, with the tester or
the Lead, and record them in `team-state.yaml.integration`. The rest of this
section applies to isolated and legacy teams.

Use the designated `integration.checkout_dir`. Verify repository identity,
base, dirty state, and exclusive ownership before integrating. Preserve User
changes. Record the exact accepted commits/artifact hashes and integration
order. Do not run a broad add/commit over unrelated changes.

The Lead can integrate accepted commits and run checks; Sub-Agents perform
code edits and conflict resolution. Give any conflict resolver an explicit
exclusive lease on the integration checkout, pause Lead mutations there,
and review the resolved version before continuing. Other writers must not
use this checkout. Shared git administration/configuration is Lead-owned.

Rerun the project's real checks on the integrated result. Worker test success
alone is insufficient. Record final commit (or non-git artifact hash), check
commands/cwd/results, and unresolved issues in `team-state.yaml.integration`.
An accepted Assignment can be `succeeded` while integration is still pending
or failed. Once the Assignment is terminal, its artifact is in
`integration.accepted_artifacts`, and its monitor is removed, run
`archive-state.py archive` (state-files.md, "Archive settled history"). Do not call the overall task complete until integration checks and
required visual/review gates pass. Failures create scoped follow-up work,
without resetting or evading an existing Assignment's retry cap.

Finish with result, verification evidence, unresolved issues, and remaining
Lead/Sub-Agent panes, checkouts/worktrees, monitors, and test servers. Record
each resource's owner. Do not push, publish, deploy, touch production, or
expose secrets without explicit User approval. Disband and worktree cleanup
are separate operations; completion alone authorizes neither.
