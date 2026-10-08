# Status

A read-only reconciliation sweep. Nothing in this workflow writes anything.

## Procedure

0. Select the team folder (state-files.md). With several team folders and
   no Team ID named, list each folder with its Lead name and stop; do not
   pick one.
1. Read `<team_dir>/team-state.yaml` — the book state: per role, its current Assignment
   (if any), `assignment_status`, `expected_agent_state`.
   Include the separate lead record and recorded resource inventory. Legacy
   state without lead identity is flagged as missing; do not migrate it here.
2. For each role, `herdr agent get <role-name>` — the live Herdr state
   (`working`/`idle`/`done`/`blocked`/`unknown`).
   Read the role's `status.json` `handoff_ready` field when present. During
   this Status pass, the Lead may also read the bottom line of the role's
   pane for its CLI context figure. Both are hints only; neither proves
   completion or changes the state.
3. Reconcile: flag any mismatch between book and live state — e.g. books say
   `expected_agent_state: working` but Herdr reports `idle`, or vice versa.
   Read-only checks may compare Lead/role name, pane, kind, cwd, process,
   checkout identity, and visible model/effort with recorded verification.
   Flag missing/stale evidence; never manufacture it or repair mappings.

## Output

A table: role / current Assignment id / book state / live state / flag.
Flag anything inconsistent; otherwise leave it blank.
Show `Team: <team_dir>` and `Role Tree: <team_dir>/role-tree.md` first,
then `Lead Agent: <name> → <pane-id>` with its mode (session or spawned), plus role checkout paths and
unresolved integration/resource state. A missing Lead mapping is explicit.

## Hard constraint

This workflow **never** dispatches, never writes `team-state.yaml` or any
other file, and never sends a prompt to a Sub-Agent. If a mismatch is found,
report it — don't fix it here. Fixing a stuck or misreported role goes
through Dispatch's acceptance protocol or the exception routing in
`monitoring.md`, triggered as its own follow-up action, not folded into this
sweep.
