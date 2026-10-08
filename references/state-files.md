# State files

## Canonical project root

Resolve in this order: (1) an explicit User path; (2) an explicit recorded
canonical root for this team, verified against repository/worktree
relationships; (3) the nearest directory upward from cwd that holds any
`.herdr-agent-team*` team folder; (4) the current git repository's root.
Multiple candidates require a User decision. For a first non-git team,
confirm cwd if no root was specified.

## Knowledge root and code repositories

ADR 0004 separates two roots. `project_root` is the **knowledge root**: it
holds the team folder and all shared knowledge (plans, progress, decisions,
task-relay files). `code_repos` in team.yaml lists zero or more **code
repositories**, each with a stable `name`, an absolute `path` (a git
repository root), a `base_branch`, and an optional absolute `rules_file`
that holds the company's git rules for that repository.

Pick the checkout layout from team.yaml:

| team.yaml has | Layout |
|---|---|
| neither `checkout_mode` nor `code_repos` | **legacy single-root**: `project_root` is also the code repository. ADR 0002 worktrees apply as before. |
| `checkout_mode: isolated` | Each writer gets its own worktree of a code repository. The knowledge root is never split. |
| `checkout_mode: shared` | No worktrees at all. Every member works in the one checkout of each code repository. One writer per checkout (writer-rules.md). |

A team.yaml with only one of the two fields is invalid; stop and ask. In
every non-legacy team the knowledge root is never split into worktrees,
copies, or snapshots. Every member reads knowledge by absolute path from
the knowledge root, never by a path relative to its own cwd. The knowledge
base may already record the code repository paths; Assemble copies them
into team.yaml so validation and Status never guess. Assemble always writes
both fields for a new team, so a new team never falls into the legacy
layout by omission. A knowledge-only team uses `checkout_mode: shared` and
`code_repos: []`.

## Team folder and team_dir

One project root may hold several teams (ADR 0003). Each team lives in its
own folder at the root: `.herdr-agent-team` (the default team) or
`.herdr-agent-team-<team-id>`, for example `.herdr-agent-team-dev`. The
suffix is the Team ID and matches `[a-z][a-z0-9_-]{0,23}`. One folder holds
exactly one team.

Select the team before reading or writing anything:

1. Collect every `.herdr-agent-team*` directory directly under the root.
2. The User named a team ID: use that folder. For a new team, the folder
   must not exist yet.
3. No team named and exactly one folder: use it.
4. No team named and several folders: list them with their Lead names and
   stop, or ask which one. Never guess.
5. A new team with no name and no folder: use the default folder. A new
   team while other folders exist: ask for a Team ID.

Record the selected absolute path as `team_dir` in both team.yaml and
team-state.yaml. The two values must match; a mismatch stops every
workflow before any write. Every control path in every workflow, prompt,
and Assignment is built from `team_dir`, never from the literal default
folder name. The Team ID is the default task prefix for new agent names;
the User can override it.

In a linked worktree, use `git worktree list --porcelain` and the common git
directory to verify the recorded relationship. Do not assume this checkout's
root is the canonical root or create another team directory because the
canonical one is in a sibling checkout.

All prompts use absolute Assignment/log/report paths. A writer pane starts
with explicit `--cwd <checkout_dir>`. The canonical root stores control
files; the Checkout Dir stores implementation. Scope any needed extra access
to the Assignment's owned output paths; do not broaden sandbox permissions
automatically to the canonical repository. Use normal permission routing.

## Layout

All team control files live under `<team_dir>/`, including with optional
task-relay integration. Never duplicate this tree
in writer checkouts. Artifacts are versioned, not overwritten during review.

```
<team_dir>/                # .herdr-agent-team or .herdr-agent-team-<team-id>
├── team.yaml
├── team-state.yaml
├── role-tree.md           # Lead-owned, rendered from team.yaml, read-only
├── lead-handoff.md        # Lead-owned narrative snapshot; refreshed at settled boundaries
└── assignments/<assignment-id>/
    ├── assignment.md  # Lead-owned
    ├── log.md         # Sub-Agent-owned after initialization
    ├── handoff.md     # Sub-Agent-owned, current attempt narrative
    ├── report.md      # Sub-Agent-owned
    ├── status.json    # optional, Sub-Agent-owned; hint only, never proof (see assemble.md)
    └── artifacts/     # explicit control-output grant only
```

Each role may write one `handoff.md` for its current attempt. It has exactly
seven short sections: Where I am, Done, Not done, Decisions and why, Gotchas,
First action next, and Open questions. Write two or three short sentences
per section; do not paste logs or whole files. Include the attempt number
outside the sections. Write it to a same-directory temporary file and
atomically rename it. A rework keeps previous handoffs at
`artifacts/attempt-<n>/handoff.md`. `team-state.yaml` remains structured
truth; when a handoff disagrees with state, state wins and the Lead reports
the difference.

The Lead owns `<team_dir>/lead-handoff.md`. Refresh it atomically after each
acceptance and before the next dispatch, before every question to the User,
and in full when the Lead's context is below 30%. Include current
Assignments, armed monitors, decisions, learned User preferences, and the
next step. At below 30%, tell the User: "Recommend a new session that runs
Resume." Start from `assets/lead-handoff.md.template`. Resume reads this
narrative first and then team-state.

Append one `## checkpoint` log entry after every finished Sub-Agent
sub-step. Continuations read only entries after the last checkpoint plus
handoff.md. `status.json` may include `handoff_ready: true`; this is a hint,
never proof. A context figure read from a role screen is also a hint and is
only read during Status or at acceptance when a report says work is
incomplete.

The optional `status.json` remains Sub-Agent-owned and should include its
existing `phase`, `note`, and `updated_at` fields. `handoff_ready` is an
additional optional Boolean. The Lead does not copy it into structured
team-state or use it as proof that the handoff file is complete.

## team.yaml — static definition

Top level: `schema_version: 2`, absolute `project_root`, absolute
`team_dir`, `permissions` (`inherit` or `scoped`, default `inherit`),
`team_type` and `team_id` (null when not used), `template`
(false for a real team), `checkout_mode` and `code_repos` (see "Knowledge
root and code repositories"; both absent only in a legacy team),
`protected_paths_extra` (User-added protected paths, default `[]`; see
writer-rules.md), the `lead` block, `integration.checkout_dir`, and
`roles`. Under `checkout_mode: shared`, `integration.checkout_dir` is null:
integration is the implementor's commits in each code repository.

The `lead` block holds `name`, `mode` (`session` when the running session
is Lead, `spawned` when the team launched a Lead pane), and the effective
`kind`, `model`, `model_label`, `profile`, `effort`, `launch_args`. For a
session Lead these are observed values, or explicit null when Herdr
cannot expose them; never copy advice into them. For a spawned Lead they
are the verified launch spec. `lead.suggested` keeps template advice and
is never shown as the actual Lead. The Role Tree renders from team.yaml
alone, so it is the same with or without team-state.yaml.

Roles also accept optional `prompt_file` (appended to the opening
instruction) and `skills` (a list of names, mentioned in the opening
instruction only). In a built-in template, `prompt_file` may be relative
to that template's folder. In a real team.yaml it is always an absolute
path: Assemble resolves a relative template path when it seeds the team,
and the interview and Adjust accept only absolute paths.

One entry per Sub-Agent role:
name, responsibility, kind, model, model_label, optional profile (null if
unused), explicit effort, resolved launch_args, cli_version, access
(`writer` or `reader`), absolute checkout_dir, position, write_ceiling,
up_agent, low_agent. Under `checkout_mode: shared` a checkout_dir is only
the pane's working directory, never a worktree: the implementor points at
its main code repository, other roles at the knowledge root. A
write_ceiling entry that points into a code repository is an absolute path
or glob under that repository's `path`. The model label is for names; model is the selection.
Resolve launch_args before starting; an empty unresolved list cannot launch.
CLI mappings and header checks live in `identity-and-launch.md`.

Position is split direction plus anchor, current-tab only. New launches
use the fixed chain: role 1 is `{direction: right, from: lead}` and role
N is `{direction: down, from: <role N-1 name>}`. Adjust recomputes the
chain from role order after any add, remove, or rename. A live team in any
other layout keeps its panes and is reported as "layout migration needed";
no new pane is launched into it until its team.yaml follows the chain. The static Lead
name is separate from roles; dynamic state maps it to its current pane.
Read-only roles have `write_ceiling: []`; every checkout has one writer at
a time (writer-rules.md).
Keep exactly two layers: `up_agent: lead` and `low_agent: []`.

Names match `[a-z][a-z0-9_-]{0,31}` and are unique across live agents,
including Lead, and across the roles and Lead of every other team folder
at the same root. New names use task-role-model-label; the broader expression
remains valid for legacy names. Start from a built-in Team Template in `assets/teams/<team-type>/` when
one matches, otherwise from `assets/team.yaml.template`. A seed has
`template: true` and may leave `checkout_dir` and `write_ceiling` null;
Assemble fills them and sets `template: false`. A file with
`template: true` never launches.

## role-tree.md — rendered view

Render with `assets/render-role-tree.py <team_dir>/team.yaml` and write
the output atomically to `<team_dir>/role-tree.md` after Assemble and after
every Adjust. Never edit it by hand and never read decisions from it. The
script refuses a team.yaml that breaks the fixed chain or the effort rules
in identity-and-launch.md.

## team-state.yaml — dynamic snapshot

Lead-Agent-owned only. Top level:

- `schema_version`, `updated_at`, absolute `project_root`, absolute
  `team_dir` (equal to team.yaml's).
- `lead`: name, pane_id, kind, cwd, process_identity, identity_verified_at,
  and observed model/effort when available. `lead_history` preserves prior
  identities after validated succession. Alias `lead` resolves here.
  `lead.launched_by_team` and `lead.handoff_at` record a spawned Lead.
- `launcher`: null, or the Launcher's name, pane_id, kind,
  process_identity, and handoff_at. The Launcher writes nothing after
  handoff_at; it is never a second Lead.
- `roles`: pane_id, kind, cwd, expected_agent_state, checkout_identity
  (real root and git_dir, or non-git snapshot identity), created_by_team,
  process_identity, intended model/profile/effort, launch_verification,
  and `role_history` (prior names after an Adjust rename).
  A role may also have `rotations: [{at, reason, handoff_path}]` for
  replacement sessions during a running Assignment.
  Verification fields are timestamped observations, not live state.
- `assignments`: full active and queued list, each with id, attempt,
  assignee, assignment_status, base_commit or input_snapshot, checkout_dir,
  absolute report_path, artifact, lease, and created/finished timestamps.
  Pending queued records have `dispatched_at: null` and no active lease.
  An Assignment that touches code repositories also records
  `repositories`: one `{name, input_sha, result_sha}` entry per repository
  (`result_sha` null until accepted), and `dirty_baseline`: the absolute
  path of the dirty-path baseline file in the Assignment's Workspace Dir
  (dispatch.md), or null. A shared-mode source Assignment also records
  `dirty_at_dispatch` (in-scope paths snapshotted at dispatch) and
  `commit`: `{status: none | awaiting_user | approved | committed | declined,
  confirmed_files, approved_by: user | auto, approved_at}`
  (acceptance.md, "Commit gate").
- `commit_approval` (shared mode): `{mode: ask | auto, granted_by_words,
  granted_at}`. Default `ask`. Only the User's own message sets `auto`;
  Disband resets it to `ask`.
- `commit_log` (shared mode): one entry per source commit made through the
  commit gate: assignment_id, repository, sha, files, approved_by, at.
- `monitors`: assignment_id, attempt, assignee, host task_handle, so a
  wake-up/cancel targets the right work. Not a raw shell PID. The handle
  belongs to a backgrounded `skill/assets/watch-assignment.sh` run (see
  `monitoring.md`), not a bare `agent wait` — its last observed `outcome`
  (`report`/`blocked`/`unknown`/`gone`/`stalled`/`no_report`/`timeout`) may
  be recorded alongside the handle for Status/Resume's benefit, but the
  handle itself, not a cached outcome, is what identifies live work.
- `integration`: checkout_dir, status, accepted_artifacts, final_artifact,
  checks. Status is pending/running/succeeded/failed/not_applicable, distinct
  from Assignment state. Read-only tasks can use not_applicable with a reason.
- `resources`: type, id_or_path, owner, created_by_team for panes, worktrees,
  and servers. Inventory supports reporting, not automatic cleanup. A
  shared-mode team records no worktrees; the User's code checkouts are
  never team resources.

### Three status fields — never mix these up

- `assignment_status`: pending → running → (blocked) → succeeded/failed/cancelled.
- `expected_agent_state`: the Lead's belief about a role, not an observation.
- Herdr's live working/idle/done/blocked/unknown state is never persisted.
  Query it fresh with `agent get`.

Every transition updates state: dispatch, report, rework, cancel, blocked,
timeout, re-arm. Write temp-file-then-rename. Preserve unrelated records on
Assemble/reuse. See `assets/team-state.yaml.template` for field shapes.

## Legacy migration

Legacy single-root layout (no `checkout_mode`, no `code_repos`) is not a
schema migration: it stays schema 2 and keeps working. Switching an
existing team to two roots is an explicit User decision: edit team.yaml at a
settled boundary (no active Assignment) and validate it with assemble.md
step 3 before any dispatch.

Unversioned static definitions and schema-version-1 state are legacy. Status
and Disband read them without requiring new fields. Status never migrates.
Reject unknown future versions before writing. Preserve existing keys,
Assignment history, queued items, monitor mappings, and terminal reports.

During authorized Assemble/Resume, first reconcile processes. Do not
interrupt active work or rename legacy roles solely to enforce v2. Working
legacy agents can finish under their existing grants and get a bare monitor.
Apply v2 configuration and checkout checks before any new or continuation
prompt. If evidence is missing or writer checkouts collide, report migration
needed and send no dependent work. Judge settled legacy reports against
their original Assignment contract, not the new report template. New and
reworked Assignments use v2.

At a safe settled boundary, populate explicit missing fields, assign
exclusive checkouts, validate launches, and atomically upgrade each file from
preserved versioned backups. Track per-role migration readiness until all
are ready; do not label incomplete data schema 2. If the two-file upgrade is
interrupted, reconcile versions with backups before dispatch without losing
newer Assignment history. Never infer ownership/model evidence. Keep legacy
names during migration; use new names for new/replacement roles.

## Assignment lifecycle

- Stable ID = the assignment's directory name under
  `<team_dir>/assignments/`, unique within the team.
- State machine: `pending → running → (blocked) → succeeded / failed /
  cancelled`.
- Each Sub-Agent holds **at most one active Assignment** at a time. A dispatch
  aimed at a busy Sub-Agent is rejected outright. Anything else queued for
  that role is recorded in `team-state.yaml`'s assignment list, not held in
  the Lead Agent's memory.
- Rework does not create a new Assignment. Increment `attempt` on the same ID
  and append the gap description to `assignment.md`. Cap: `max_attempts: 3`
  (the first try plus at most two reworks); exhausting it escalates to the
  User.
- Cancel / redirect / re-dispatch always follows the handshake in
  `monitoring.md` — stopping the background monitor alone is not enough,
  since the Sub-Agent keeps editing files until its turn is actually
  interrupted.

## Atomic writes

Any file more than one process might read mid-write — `team-state.yaml`,
and a Sub-Agent's `report.md` — must be written as: write to a temp file in
the same directory, then rename over the target. This is what prevents the
Lead Agent (or a Sub-Agent recovering after a crash) from reading a
half-written file. State the requirement explicitly in the opening
instructions sent to every new Sub-Agent (see `assemble.md`).

## Optional: task-relay integration

`herdr-agent-team` has zero dependency on any project-management tool. When a
project also uses task-relay, keep the two handoff layers separate:

| Layer | Owner | Unit | Handoff |
|---|---|---|---|
| Project relay | task-relay, Lead only | item or task | `progress.log` overflow note and `memory.md` |
| Role relay | herdr-agent-team | Assignment and attempt | `handoff.md` and `lead-handoff.md` |

- The Lead Agent is task-relay's sole operator; it owns `00-current/`
  (`item-list.json`, `progress.log`, etc.) the same way it owns
  `team-state.yaml`.
- The Lead writes one handoff. Add one pointer line to `progress.log`:
  `Lead handoff at <team_dir>/lead-handoff.md`.
  Keep one current pointer line when refreshing the handoff; do not copy its
  narrative into `progress.log`.
- On Rotate, append one line to the item's `20-working/<ITEM>/log.md` with
  the role, time, and handoff path.
- At acceptance or Rotate, the Lead reads the Gotchas section and moves
  generally useful knowledge into `00-current/memory.md` through the
  task-relay memory capture. Sub-Agents never write task-relay files.
- The opening instruction names the absolute path to
  `<project_root>/00-current/memory.md` when it exists.
- The Lead Agent may map an Assignment to one or more task-relay items at
  whatever granularity it chooses, and record the assignee role on the item
  for traceability after a restart.
- Assignment workspace dirs still always live under
  `<team_dir>/assignments/` — no exception. The link from task-relay's
  side is a pointer line written into `20-working/<ITEM>/log.md`: "this item
  is executed by `<role>`; log and report are at
  `<team_dir>/assignments/<assignment-id>/`."
- Sub-Agents may read task-relay's files (`progress.log`, specs,
  `item-list.json`) but never write them. These paths are core protected
  paths (writer-rules.md): no role ceiling or Assignment lease may cover
  them.
- The same pattern generalizes to any other project-management approach
  (plain markdown todos, GitHub issues, ...) without changing this skill.
