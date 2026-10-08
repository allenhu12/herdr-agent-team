# Writer rules

## Single writer, unrestricted reads

Every file has exactly one owner, and only the owner writes it. Reading is
never restricted — any Sub-Agent may read anything in the project, including
other Sub-Agents' `log.md`/`report.md` and shared docs. This is what lets
Sub-Agents stay well-informed without needing broad write access: they don't
lose project context just because they can't write outside their own
workspace dir.

- A Sub-Agent's default (and usually only) write scope is its own Assignment
  workspace dir (`<team_dir>/assignments/<id>/`) — but not every file
  in it. `assignment.md` in that same directory is Lead-Agent-owned (the
  Lead Agent writes it before dispatch and appends rework notes to it); the
  Sub-Agent's default control writes are `log.md`, `report.md`, `handoff.md`,
  optional `status.json`, and temp files
  used for the atomic-rename pattern. Additional versioned evidence/artifact
  paths under this Assignment's Workspace Dir need an explicit control-output
  grant. This grant never includes assignment.md or shared state. Dispatch
  initializes `log.md` from `assets/log.md.template` so the timestamp/role-header convention is
  already in place before the Sub-Agent's first entry.
- Shared documents — progress files, plan docs, state files — are written
  only by the Lead Agent. A Sub-Agent that produces something meant for a
  shared doc reports it back; the Lead Agent integrates and writes it.
- In a two-root team (state-files.md) all shared knowledge lives in the one
  knowledge root. Read it by absolute path from there, never through a path
  relative to a code checkout. A role such as `writer` may get a grant for
  named knowledge-base document paths, through the two-tier rule below and
  never over a protected path.
- When dispatching, attach paths to the relevant background docs so the
  Sub-Agent has context without needing write access to them.

This is a **soft constraint**: nothing at the filesystem level enforces it.
Formatters, dependency installers, git, and the like can all produce
out-of-scope writes incidentally. Compensate at acceptance time — a `git
diff` (or equivalent) audit of what actually changed, and escalate anything
outside the granted scope to the User. Separate checkouts reduce accidental
file collisions; they do not enforce permissions or restrict reads.

## One writer per checkout

Every checkout has one writer at a time (ADR 0004 amending ADR 0002). Two
implementation writers must never write one checkout at the same time, even
with disjoint file grants: formatters, generated files, and the shared git
index still collide. The team's `checkout_mode` decides how this holds.

### Isolated mode and legacy single-root teams

Give each writer role a separate worktree/checkout and git index. In a
two-root team, create worktrees only from `code_repos`, never from the
knowledge root. A legacy single-root team keeps creating them from
`project_root`.
Resolve real paths and inspect `git worktree list --porcelain`, repository
identity, and `git rev-parse --absolute-git-dir`; two symlink paths to one
checkout do not provide isolation. Assign branches without name collisions.
The Lead owns worktree creation and shared git configuration. Sub-Agents may
make scoped commits in their own checkout, not change shared git settings.

Before creating a worktree, verify the base commit, repository and exact
destination, and preserve existing files/dirty work. Never reset a User
checkout to the requested base. The integration checkout has one writer;
only an explicit handoff transfers it to a conflict resolver (acceptance.md).

### Shared mode

No worktrees are created from any repository. Every member works in the
User's one checkout of each code repository, so the single writer comes
from role ceilings:

- **One source writer.** At most one role's `write_ceiling` may contain
  tracked source paths under a `code_repos` path. In the develop template
  this role is the implementor. Assemble and Adjust reject a second one and
  name both roles.
- **Tester output exception.** A tester role may hold declared generated,
  cache, and output paths under a code repository (for example `build/`,
  `coverage/`, a snapshot output directory), in both its ceiling and its
  lease. These never include tracked source. They are the only exception
  to the one-source-writer rule, and they are usable only during the
  tester's serialized window (dispatch.md).
- **Code changes by request.** Any other member that needs a code change
  asks the implementor: by a direct message when its Assignment authorizes
  that peer and the implementor is idle, otherwise through its own log and
  report for the Lead to relay (below).
- **Git operations.** The source writer edits only on the repository's
  `base_branch` or a branch the Lead names. It commits only when the Lead
  asks after the commit gate (acceptance.md): the User confirmed the file
  list, or the User's own auto-commit switch is on. This holds for work
  done on a peer request too. It does not switch branches, rebase, push,
  stash, or reset. The User does those, or
  the Lead asks the User first as the repository's `rules_file` requires.
  The company rules in `rules_file` apply only to that code repository,
  never to the knowledge root.
- **User's dirty files.** The User's checkout may hold uncommitted work.
  Dispatch records a dirty-path baseline and snapshots dirty files inside
  the write scope; acceptance re-checks the baseline, and the commit gate
  shows the User every such file before it is committed (dispatch.md,
  acceptance.md). Never reset and never exclude a dirty path from the
  audit.

### Readers and command effects

Research/read-only reviewers may share a checkout, with private control
outputs. Classify commands by their effects: tests/formatters/installers
that change project files or its index require a writer checkout. Declare
generated/cache output paths in the lease. A source review can inspect git
objects at a frozen SHA while another checkout changes; executing that
version requires a stable checkout at that version.

For non-git work use versioned input snapshots and separate copies per
writer; record hashes. If safe isolation is unavailable, use one writer.
Do not initialize git simply to fill a template field.

## Two-tier write authorization

Two layers combine by intersection, and dispatch never widens beyond the
narrower one:

1. **Role ceiling** (`team.yaml`, permanent): the maximum paths a role could
   ever be granted, set once when the team is defined.
2. **Assignment lease** (`assignment.md`, temporary): the paths granted for
   *this* Assignment, revoked automatically when the Assignment ends.

The effective write scope is the intersection of the two. When dispatching,
if the requested write scope overlaps another Sub-Agent's currently-active
Assignment scope, reject the dispatch rather than create a collision.
Compare logical repository-relative paths across checkouts, not just absolute
paths: separate worktrees do not authorize concurrent ownership of one file.
Independently reject two writer roles assigned the same checkout. Shared
control-output grants are limited to each Assignment's own outputs above.

Normalize every granted path before writing it into `assignment.md` — resolve
`..` segments and symlinks so a written grant can't be walked outside its
intended boundary.
Recheck real paths before writes and at acceptance; an absolute path outside
the role's checkout, a declared code repository, or a granted knowledge-root
document is not a project grant. Keep canonical Assignment paths
absolute and quoted across all panes (state-files.md).

## Protected paths

Some files are never granted to any Sub-Agent, whatever the role ceiling or
lease says. There are two layers:

- **Core entries** follow from the single-owner rule. They are fixed in
  this skill, and the User cannot remove them:

  ```
  <team_dir>/team.yaml
  <team_dir>/team-state.yaml
  <team_dir>/role-tree.md
  <team_dir>/assignments/*/assignment.md
  <project_root>/00-current/**
  <project_root>/**/progress*.md
  <project_root>/**/item-list.json
  ```

- **Extra entries** are the User's `protected_paths_extra` list in
  team.yaml. The User may add or remove them.

Expand `<team_dir>` and `<project_root>` to absolute paths, and normalize
both sides with the procedure above: resolve `..` and symlinks to real
paths. Protected entries come in two kinds, and each kind is checked its
own way:

- **Location entries** name a file or a directory tree: the `<team_dir>`
  files and `<project_root>/00-current/**`. Reject a grant that names one
  of these files, lies inside one of these trees, or is a parent glob
  that contains one (such as `<project_root>/**`). When it is unclear
  whether a grant reaches such a location, reject it.
- **Name-pattern entries** match file names anywhere: `**/progress*.md`
  and `**/item-list.json`. Reject a grant that names a matching file. A
  directory glob such as `<project_root>/docs/**` stays valid, and the
  pattern is subtracted from it: the Sub-Agent may not write a matching
  file there, and acceptance treats such a write as out of scope.

User-added entries follow the same two kinds: an entry that ends in `/**`
or names one file is a location entry; an entry that starts with `**/` is
a name pattern. Check role ceilings at Assemble and Adjust, and Assignment
leases at Dispatch; reject as above. Core entries
do not live in team.yaml, so no edit can drop them; refuse a User request to
remove one and explain why.

## Sub-Agent-to-Sub-Agent communication

Sub-Agents *can* technically message each other with `herdr agent prompt`,
but unrestricted use breaks the Lead Agent's monitoring (a state change might
come from a peer message, not task completion), loses global visibility
(side decisions the Lead Agent never sees), and risks mutual-wait deadlocks.
The compromise:

- **Reading is fully open.** A Sub-Agent may read any peer's workspace dir at
  any time — it doesn't disturb the peer, change its state, or create a
  conflict.
- **Direct messaging requires per-Assignment authorization.** When
  dispatching, if the Lead Agent foresees a collaboration need (e.g.
  frontend/backend contract work), it explicitly names the authorized
  counterpart in the Assignment's instructions. Unauthorized Sub-Agents don't
  message each other.
- **Only message an idle counterpart.** Herdr's `agent prompt` doesn't track
  individual turns — sending into a working peer's pane interleaves with its
  current work. Before sending, check the counterpart's state; if it's
  working, don't prompt it. Instead write the note into your own `log.md`
  (for the peer to read later) or ask the Lead Agent to relay.
- **Log every agreement.** Whatever two Sub-Agents settle on through direct
  contact, both sides record it in their own `log.md`, so the Lead Agent sees
  it at acceptance time.
- The Lead Agent, when monitoring an authorized pair, should keep in mind
  that a state change might be a peer message landing, not the Assignment
  finishing — don't treat every wake-up as completion (see
  `monitoring.md`).
