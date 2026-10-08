# Disband

Tear the team down. Closing a pane is irreversible, so this workflow always
confirms with the User before touching anything.

## 1. Inventory open work

Select the team folder and `team_dir` first (state-files.md). Disband
touches only that team; other team folders at the same root are out of
scope.

List anything not cleanly finished: roles currently `working`/`blocked`,
Assignments not yet through acceptance. Present these as warnings — disband
can still proceed, but the User should see what's being left unfinished.

## 2. Confirm before acting

Show the User exactly which agents and panes are about to close. Only
proceed after explicit confirmation — this workflow must not close anything
on its own judgment call.
Include the Lead name/pane as retained, not a close target. A spawned
Lead is still the Lead and is retained; a Launcher pane is also not a
close target. List worktrees
and test servers separately; pane closure does not prove their cleanup.

## 3. Stop every background monitor

Before touching any pane, stop every entry in `team-state.yaml`'s
`monitors` list (kill each tracked host background task) and clear the
list. Do this for **all** monitors, not just ones tied to Assignments being
cancelled — a monitor left running past this point can still wake up after
its pane is closed and try to run acceptance against an archived, no-longer-
live Assignment. This mirrors the cancel handshake in `monitoring.md`: stop
the watcher before touching what it's watching.

## 4. Re-validate before each close

Immediately before closing a given pane, run the same joint-validation check
as `resume.md` (role name, live pane id, kind, cwd all match
`team-state.yaml`). Any mismatch — stale record, pane repurposed since the
last snapshot — means **skip that pane** and report it, rather than closing
whatever happens to occupy that pane id now.
For v2 include process and checkout identity. Header/model drift blocks new
work but is not by itself proof a pane is foreign; require verified ownership
and the User's listed close targets. Legacy state uses original identity and
creation evidence; do not infer ownership from a similar name. Never close
the Lead pane or an adopted/foreign pane.

## 5. Archive

In a shared-mode team, set `commit_approval.mode` back to `ask`; an
auto-commit switch never outlives its team.

Write a closing record into `team-state.yaml`: for every Assignment, its
final outcome and timestamp. This becomes the disband archive — don't delete
it afterward. Keep `<team_dir>/role-tree.md` beside it as the last
rendered roster.

## 6. Close

End each Sub-Agent and close its pane, one role at a time. Close **only**
panes this skill created — never touch a pane the team doesn't own, even if
it looks related.

## 7. Report

Confirm disband completion to the User, and point them at the archived
`team-state.yaml` for the record of what happened.
Report remaining Lead/other panes, worktrees, monitors, and servers. Do not
remove worktrees or stop unlisted servers without scoped authorization.
Update the archive to the observed final pane outcomes without stale current
fields contradicting historical events; preserve timestamps and history.
