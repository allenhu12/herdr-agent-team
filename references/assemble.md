# Assemble

Build or reuse the smallest team that satisfies the User's request.

## 1. Preconditions and inventory

Check HERDR_ENV, resolve the canonical project root and select the team
folder (state-files.md, "Team folder and team_dir"), then read that
folder's existing team definition/state. Confirm `python3` with PyYAML
is available; the Role Tree renderer is a required preflight gate, so
without it Assemble stops before any pane is created. Follow identity-and-launch.md to list
agents/panes and verify ownership. Inventory before creating or renaming
anything. A live matching role is a reuse candidate, not a reason to start
another. Busy roles remain untouched; Resume monitors existing work.

## 2. Define missing configuration

### 2a. New team or existing team

Decide this only after step 1's inventory.

- `<team_dir>/team.yaml` exists: this is an existing team. Reuse it as it
  is. Route requested roster, model, or effort changes to
  [adjust.md](adjust.md). Never copy a template over it, even when the
  User repeats "create a <team-type> team".
- No team.yaml: take the team type from the request and look for
  `assets/teams/<team-type>/team.yaml`.
  - Found: seed from it. Set `template: false`, `team_type`, `team_id`,
    `team_dir`, `project_root`, `checkout_mode`, `code_repos`, and replace `<task>` in role names with
    the task prefix (default: the Team ID). Keep the template's role
    order; positions follow the fixed chain. Resolve every relative
    `prompt_file` against the template's folder and store the absolute
    path; a missing file fails preflight.
    Keep each role's `context_roots` list (absent means `[]`); do not add
    a machine-specific root to a distributed template.
  - Not found: interview the User one question at a time, each with a
    default: number of Sub-Agents (default 1); then, only when the Lead
    will be spawned (2b), Lead kind, model, effort; then per Sub-Agent:
    role word, one-line responsibility, kind, model, effort, and writer
    or reader, an optional absolute `prompt_file` path, and any
    User-supplied context directories. Do not ask
    for positions; they follow the fixed chain.
    Render the Role Tree preview and ask for one confirmation.
    After a successful assemble, offer once to save it as
    `assets/teams/<team-type>/team.yaml` with `template: true`, paths set
    to null, and effective Lead fields cleared into `lead.suggested`.

### 2a-2. Knowledge root and code repositories

`project_root` is the knowledge root (state-files.md). For every new team,
write both `checkout_mode` and `code_repos`, even when the list is empty;
never leave both out, or the team reads as legacy single-root.

- Take `checkout_mode` from the template (the develop template says
  `shared`), else use `shared` without asking. Use `isolated` only when
  the User asks for it, for example when two writers must edit one code
  repository at the same time. A knowledge-only team uses `shared` with
  `code_repos: []`.
- Fill `code_repos` from the User's request or from the paths the
  knowledge base already records. Read the knowledge base for them before
  asking. Each entry gets `name`, absolute `path`, `base_branch`, and
  `rules_file` (absolute, or null). Show the resolved list with the
  configuration; never guess a path.
- Under `shared`, set `integration.checkout_dir: null`. Set the
  implementor's `checkout_dir` to its main code repository and every other
  role's to the knowledge root.

### 2b. Who is the Lead

Ask "Should this session be the Lead?" unless the request already says.

- Yes: `lead.mode: session`. Template Lead values are advice only. Write
  this session's observed kind/model/effort into the effective `lead`
  fields, or explicit null when Herdr cannot expose them. Tell the User
  once, for example: "Template suggests codex gpt-6-astra medium. This
  session is claude opus-5 medium. Continuing with this session." No
  confirmation needed.
- No: this session becomes the Launcher. `lead.mode: spawned`. The
  effective `lead` fields are the explicit launch spec, taken from
  `lead.suggested` or the interview, and are verified in step 4b.

### 2c. Resolve per-role configuration

Use the seeded file, or assets/team.yaml.template. Select one Sub-Agent by default; add one for
independent work/review or preserve an explicit User roster. Apply the model
routing in identity-and-launch.md. Resolve responsibility, kind, exact model
or documented alias, optional profile, model_label, effort, access,
checkout_dir, write_ceiling, and split position. Set the team's
`permissions` field (default `inherit`; see identity-and-launch.md). Only
under `scoped` does a writer role get permission arguments folded into
`launch_args`; a reader role never gets them.
Record Lead name and one integration checkout. Ask only for missing choices
that cannot be resolved from the User's request or explicit team
configuration.

Show the resolved configuration. Existing authorization covers the requested
team setup; do not ask again for choices the User already supplied. Validate
a supplied file too. Legacy definitions follow state-files.md migration.

## 3. Validate before building anything

Stop on a failure before creating any pane:

- Names match `[a-z][a-z0-9_-]{0,31}`, are unique including Lead, and new
  names follow task-role-model-label. A collision with a foreign live agent
  is not permission to rename it.
- Each responsibility is non-empty; kind is an installed Herdr-supported
  kind. Model/effort are explicit; resolve and record launch_args and CLI
  version using identity-and-launch.md, including required profile checks.
- write_ceiling is present and a list of path/glob strings, including an
  explicit empty list for a reader. Missing/scalar/map values are errors.
- Every `context_roots` value is a list of distinct, non-empty absolute
  directory paths (absent means `[]`). Before a new role is launched,
  check that each configured directory exists. Name a missing path and
  stop before pane creation. The renderer checks shape but not existence.
  For a live reused role, keep its pane and active work; block only new
  context-dependent dispatch until the missing path is corrected or the
  User provides an explicit alternative.
- access is writer or reader; all checkout paths are absolute and normalized.
- Checkout layout (state-files.md, writer-rules.md "One writer per
  checkout"). `checkout_mode` and `code_repos` are both present or both
  absent; one alone stops preflight.
  - Every `code_repos` path is a real git repository root, names are
    unique, and each `base_branch` exists. A `rules_file`, when set, exists.
  - Isolated or legacy: writers have separate real checkouts/indexes.
    Validate repository and base before creating isolated worktrees;
    preserve dirty User files. In a two-root team, a worktree source is
    always a `code_repos` path, never the knowledge root.
  - Shared: create no worktree. At most one role's write_ceiling holds
    tracked source paths under a `code_repos` path; a second one stops
    preflight and the error names both roles. A tester may hold declared
    generated/cache/output paths there, never tracked source.
    `integration.checkout_dir` is null.
  - No write_ceiling overlaps a protected path (writer-rules.md,
    "Protected paths").
- Positions follow the fixed chain: role 1 `right` from `lead`, role N
  `down` from role N-1. Reject any other shape for a new launch; a live
  legacy layout is kept and reported as "layout migration needed".
  Validate current-tab anchors before splitting.
- Effort is valid for the kind (identity-and-launch.md, "Effort levels").
  A bad pair stops preflight; never map it to a nearby level.
- `template` is false. `team_dir` matches the selected folder, and no
  role name collides with another team folder's roles at this root.
- Run `assets/render-role-tree.py <team.yaml>` as a dry run; a non-zero
  exit is a preflight failure.
- up_agent is lead and low_agent is empty. Keep exactly two layers.
- Existing role reuse passes name/pane/kind/cwd/process identity checks, and
  the required launch/configuration evidence. No source work to an unverified
  agent. Missing fields follow the legacy migration path.

After successful configuration validation, establish/verify the Lead's
visible identity and atomic state mapping through identity-and-launch.md.
Do not reset existing roles, Assignments, resources, or monitors.

## 4. Create panes and start missing agents in team.yaml order

### 4a. When this session is the Lead

Keep reusable roles in place. For a missing role, resolve position.from:
lead means the verified state.lead.pane_id; another role means its recorded,
freshly verified pane. Explicit IDs avoid confusing focus with identity.

```bash
herdr pane split --pane <verified-anchor-id> --direction <right|down> --cwd "<checkout_dir>" --no-focus
herdr agent start <role-name> --kind <kind> --pane <new-pane-id> -- <resolved-app-arguments>
```

Read the new pane id from .result.pane.pane_id. Record its ownership and
checkout immediately, even if startup later fails. Keep focus with Lead.
Do not derive new flags here; use step 3's resolved argument array.

### 4b. When this session is the Launcher

This session only builds the team, then hands it over. Follow
identity-and-launch.md, "Launcher and spawned Lead".

1. Record this session as `launcher` in state (name, pane_id, kind,
   process_identity).
2. Split one pane right of the Launcher pane and start the Lead there
   with its resolved explicit arguments:

   ```bash
   herdr pane split --pane <launcher-pane-id> --direction right --cwd "<project_root>" --no-focus
   herdr agent start <lead-name> --kind <lead-kind> --pane <new-pane-id> -- <lead-launch-args>
   ```

3. Verify the Lead's header exactly as for a Sub-Agent. A failure stops
   here: report it, create no Sub-Agent panes, and do not hand off.
4. Create the Sub-Agent panes along the fixed chain, with `lead`
   resolved to the new Lead pane, then verify each header. Sub-Agent
   opening instructions (step 5) name the new Lead and its pane, never
   the Launcher.

Agent detection defaults to 30 seconds. Once ready, perform the header
verification in identity-and-launch.md before any opening prompt. Record
process identity and header evidence atomically. Any missing/wrong/unverifiable
name, model, or effort stops further launch/dispatch; preserve previously
started roles and monitors. Do not mark a partial team fully assembled.

## 5. Send the opening identity instruction

Only after identity/header verification, use agent prompt <role> --wait to
send the following (this establishes identity, not an implementation task):

- Role name, responsibility, absolute Checkout Dir, canonical project
  root, and absolute `team_dir`. Every control path in the prompt is built
  from `team_dir`.
- In a two-root team: the absolute knowledge root, the absolute paths of
  its key knowledge files (plans, progress, decisions), and the rule "Read
  knowledge by absolute path from the knowledge root, never from a path
  relative to your code checkout." List each code repository's name and
  path. Under `shared`, add the role's code rule: the implementor is the
  only source writer; every other role asks the implementor for code
  changes (by an authorized message when it is idle, otherwise through the
  Lead) and never edits tracked source. Tell the implementor: while the
  Lead says a tester window is open, it edits no source and only logs a
  code request (dispatch.md step 2a). Also tell it: edit, but commit only
  when the Lead asks after the commit gate (acceptance.md).
- Lead's visible name, pane ID, and absolute team-state.yaml path. Alias
  lead resolves there; find the current Lead by re-reading state. Do not
  interrupt a working Lead.
- Absolute Assignment paths will arrive with dispatch. Default control
  writes are only own log.md, report.md, handoff.md, optional status.json,
  and atomic temp files. assignment.md and
  shared state are Lead-owned. Extra project/control outputs need explicit
  grants (writer-rules.md).
- The six-section report template, id/attempt/status metadata, frozen artifact
  and evidence requirements; no full logs or entire files.
- Atomic-write requirement for files read by other agents.
- Optional: ask the Sub-Agent to maintain `status.json` in its own Workspace
  Dir (`phase`, `note`, `updated_at`; same atomic-write pattern) so Status
  can reconcile from a small file instead of `agent read`. This is a hint
  for humans and Status, never a completion signal — acceptance still reads
  only `report.md` for the current attempt.
- Peer contact needs per-Assignment authorization and a fresh idle-state
  check. If a peer is working, use own log/Lead handoff. Both log agreements.
- Absolute paths to relevant background documents.
- If this project uses task-relay, include the absolute path to
  `<project_root>/00-current/memory.md` in the background documents.
- The role owns `<team_dir>/assignments/<id>/handoff.md` for its current
  attempt. It writes the seven-section handoff after a checkpoint when the
  Lead says "Write your handoff now, then stop."; by itself when its CLI
  shows less than 25% context left; and before a rework rotation requested
  before any rework; the Lead decides whether to rotate. Do not start
  another sub-step after the warning or request.
  Never write during an unsaved edit or running test. Finish the current
  sub-step, append a `## checkpoint` entry after every finished sub-step,
  then write `handoff.md` atomically and append
  `HANDOFF READY attempt=<n>` to `log.md`.
  Set `status.json`'s optional `handoff_ready: true` as a hint. Stop in idle.
- If the role has `prompt_file`, append that file's content verbatim
  after these points. If it has `skills`, add one line: "Use these skills
  when relevant: <names>." Nothing else changes when both are empty.
- If the role has `context_roots`, name each absolute root and say it is
  task context only. Keep the opening reply and READY handshake unchanged;
  do not paste repository contents into the identity instruction.

Observe the opening prompt's result; do not label it idle on a timeout or
block. Resolve through monitoring.md before dispatching work.

After READY, send an idle configured role a separate bounded context-read
prompt. Have it read each root's README.md first when present (or a small
top-level index), then identify the sections relevant to its role. Use
`rg --files` and `rg -n` for navigation; read only relevant sections of
large files. If an index exceeds 8 KB, read its headings and relevant
section first. Do not load a whole repository tree, secret files, credentials,
or login transcripts. Wait for this read to finish before a
context-dependent Assignment. When reusing an idle role whose configured
roots are new or changed, send this reminder and repeat the bounded read
when uncertain. Never interrupt a working role; its active Assignment
remains authoritative, and new context belongs in the next Assignment.

## 6. Record, render, and report

Update role pane, kind, cwd/checkout identity, ownership, process identity,
model/profile/effort, launch_verification and expected_agent_state. Initialize
only new records, preserving history and monitors. Include Lead first in the
roster: name → pane → kind → observed model/effort → status, plus each role's
checkout. Explicitly label unknown Lead model/effort; do not invent values.

Render the Role Tree from the final team.yaml and write it atomically:

```bash
python3 <skill-dir>/assets/render-role-tree.py "<team_dir>/team.yaml" > "<team_dir>/role-tree.md.tmp" \
  && mv "<team_dir>/role-tree.md.tmp" "<team_dir>/role-tree.md"
```

Print the tree in the roster report. Never draw or edit the tree by
hand; step 1 already guarantees the renderer can run.

### 6b. Launcher handoff

Only when this session is the Launcher, after every pane is verified:

1. Write the final team.yaml and team-state.yaml: `lead.pane_id` = the new
   Lead pane, `lead.launched_by_team: true`, `lead.handoff_at` and
   `launcher.handoff_at` = now. Render role-tree.md. Finish every write.
2. Send the new Lead one prompt: the absolute SKILL.md path, the absolute
   `team_dir`, and "You are the Lead Agent <lead-name> and own this team.
   Load the skill and run Resume."
3. Tell the User which pane to talk to from now on.
4. From here the Launcher writes no team file, sends no prompt, and arms
   no monitor. If the prompt in step 2 fails to deliver, retry or report
   it; never take ownership back.

## 7. Startup failure

Report the failed role/pane, reason, existing resources, and missing evidence.
A timeout permits a User choice of retry, configuration change, or revised
roster. Missing header fields require the explicit resolution described in
identity-and-launch.md; do not silently skip that gate or use defaults.
