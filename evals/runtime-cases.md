# V2 evaluation cases

Static and lexical trigger checks are not agent execution tests. Run the
following only inside Herdr, in a fresh disposable test project, against a
frozen skill package. Record CLI versions, exact model/profile/effort,
commands and timestamps, screenshots where needed, artifacts and hashes.
Use PASS / FAIL / BLOCKED_ENV / INSUFFICIENT_EVIDENCE. No unobserved pass.

## Existing regression coverage

Rerun the project's historical ST-01–ST-10 and ST-X1/ST-X2 in
`plans/herdr-agent-team-smoke-test-plan.md` when available. That plan is v1
history; adapt fixtures to exclusive checkouts, explicit launches, canonical
absolute paths, and six-section reports. Preserve its intent, not obsolete
shared-checkout assumptions. For a standalone package cover these here:

- Preflight rejects invalid config before any pane is created.
- Happy dispatch, matching report, acceptance, and verbatim Direct Report.
- Busy rejection, logical path overlap rejection, and idle-only peer contact.
- Timeout/missing current report triggers inspection, not acceptance.
- Failed acceptance stops after attempt 3; no fourth try/new-ID bypass.
- Cancellation stops monitor, interrupts turn, proves no ongoing mutation,
  then revokes lease. Exact-PID fallback requires the existing User decision.
- Status leaves file hashes/mtimes unchanged and sends no prompts.
- Resume: working gets bare wait; settled report gets acceptance; genuinely
  gone role is rebuilt; stale monitor handles are replaced, not appended.
- Live name/pane mismatch is quarantined without touching foreign panes.
- Disband: no mutation before confirmation; all monitors stop; validate exact
  targets; archive precedes close; unrelated/Lead panes remain.
- Blocked Resume avoids immediate-return wait loops; out-of-ceiling grants
  are rejected before dispatch. Unknown goes to inspection/timeout, never pass.

## New runtime cases

| ID | Setup/action | Required evidence |
|---|---|---|
| V2-01 | Assemble from an unnamed Lead with one compatible existing role | Inventory first; verified Lead name visible and stored; one reused role; no extra implementation pane |
| V2-02 | A foreign pane has the proposed Lead name | Collision reported; no foreign rename or identity takeover |
| V2-03 | Sub-Agent must find Lead after a validated move | Re-read canonical state; new name/pane mapping correct; old identity retained; no busy-Lead prompt |
| V2-04 | Old Lead still alive, no handoff | No second state writer or silent takeover |
| V2-05 | Independent frontend/backend work | Opus/Codex defaults unless overridden; explicit arguments; separate checkouts/indexes |
| V2-06 | Two writer roles, disjoint grants, one checkout or symlink aliases | Rejected before prompt despite disjoint files |
| V2-07 | Separate checkouts but overlapping logical path leases | Overlap rejected before dispatch |
| V2-08 | Reader inspects frozen commit; another attempts mutating tests | First reads objects/shared source safely; second needs writer checkout; no source mutation under reader lease |
| V2-09 | DeepSeek profile present, missing, then conflicting | Required -p plus explicit -m/high; missing/conflicting profile fails preflight; no credential output |
| V2-10 | Header lacks effort or shows wrong model | No opening or Assignment prompt; failure reported; no forged display metadata |
| V2-11 | Reuse same pane after process/model changed | Old verification invalidated; new work blocked until reverified |
| V2-12 | Worktree and canonical paths contain spaces | Correct absolute Assignment/report paths; no duplicate state tree |
| V2-13 | Stale attempt report, mutable branch, missing artifact hash | Not accepted as the frozen current result |
| V2-14 | Worker passes but integration check fails | Overall completion withheld; scoped rework without retry-cap reset |
| V2-15 | Review via different CLI but identical actual model | Does not qualify as independent review |
| V2-16 | Screenshots from old commit, preview from new commit | Visual acceptance fails until version-matched evidence exists |
| V2-17 | Legacy active team with shared writers and missing Lead fields | No forced interruption; Status remains read-only; no new/continuation prompt before migration gates |
| V2-18 | Legacy terminal report/archive | Readable against original contract; no retroactive new-field rejection |
| V2-19 | Non-git task | Hashed input/output versions and exclusive copies, or one writer; no forced git init |
| V2-20 | Integration conflict needs code edits | Explicit exclusive handoff to Sub-Agent; Lead stops checkout mutation; resolved version re-reviewed |
| V2-21 | Finish or Disband with worktrees/server still present | Lead retained; ownership inventory accurate; no unapproved removal or production action |

## Team templates, Role Tree, Launcher, Adjust

| ID | Setup/action | Required evidence |
|---|---|---|
| V2-22 | "Create a develop team", answer yes to "be the Lead" | Three Sub-Agent panes stacked right of this pane in template order; each header verified; `role-tree.md` rendered; Lead line shows this session's observed model or `unknown`, never the template suggestion |
| V2-23 | Same request, answer no | Lead pane right of the Launcher, three Sub-Agents right of the Lead; after handoff empty assignments and monitors, no continuation prompt; only the new Lead writes state; the Launcher refuses a later team request |
| V2-24 | Repeat "create a develop team" on a customized team with queued work | team.yaml and queued records byte-identical; request routed to reuse/Adjust |
| V2-25 | "Create a research team" (no template) | One-question-at-a-time interview with defaults; tree preview; one confirmation; save-as-template offer with paths nulled |
| V2-26 | Two team folders; dispatch and Resume in each; Status with no Team ID | Every control file and report path inside its own `team_dir`; Status lists both folders and stops |
| V2-27 | Render the Role Tree with team-state.yaml deleted | Output identical to the render with state present |
| V2-28 | Adjust: remove first, middle, last role in turn | Chain recomputed each time; team-created panes closed only; queued work held and reported |
| V2-29 | Adjust: replace tester effort idle, busy, and with bad flags | Idle: restart, rename, next role's anchor and queued assignees moved; busy: refused; bad flags: preflight fails and the tester keeps running |
| V2-30 | Spawned Lead replace: candidate header fails; clean handoff; dispatched pending Assignment | Failure keeps old mapping and closes candidate; clean handoff leaves only the successor writing; pending dispatched work refuses the replace |
| V2-31 | team.yaml with branching or repeated-right positions | Preflight rejects before any pane; renderer exits 2 |
| V2-32 | Tester effort `max` on kind codex | Preflight names kind and level; no pane created; no silent mapping to xhigh |

## Shared knowledge root and single source writer (ADR 0004)

Fixture: a disposable knowledge-base folder holding the team, plus two
small git repositories listed in `code_repos`. Put one uncommitted User
edit in each repository before dispatch.

| ID | Setup/action | Required evidence |
|---|---|---|
| V3-01 | Assemble a shared develop team inside the knowledge base | No worktree created (`git worktree list` identical before and after in every repository); implementor pane cwd is its code repository, other panes the knowledge root; team.yaml states `checkout_mode` and `code_repos` |
| V3-02 | Two writer ceilings hold tracked source paths | Preflight rejects before any pane and names both roles |
| V3-03 | Tester ceiling holds only declared output paths | Preflight passes |
| V3-04 | Lease hits a core protected path, directly or through `<project_root>/**`, `..`, or a symlink | Dispatch rejects; no assignment.md written |
| V3-05 | User asks to remove a core protected path | Request refused with the reason; team.yaml unchanged |
| V3-06 | A User dirty file overlaps the write scope | Dispatch goes ahead and snapshots the file; acceptance diffs it against the snapshot; the commit gate marks it and asks the User (revised by the commit-gate amendment; the 2026-09-11 run tested the old reject rule) |
| V3-07 | An out-of-scope User dirty file gets staged without a content change | Acceptance finds the changed index blob and escalates |
| V3-08 | Tester dispatched with no accepted implementor report | Dispatch rejects and names the missing `result_sha` |
| V3-09 | A test run changes a tracked file | Post-test gate fails; test evidence invalid; change routed to the implementor |
| V3-10 | Authorized peer request reaches the implementor during the tester window | Implementor logs it and edits no source until the tester settles |
| V3-11 | Implementor commits after the tester was dispatched | Version signal compared with Inputs; handshake runs; attempt incremented |
| V3-12 | A member sends a new constraint while the tester runs | Lead decides against assignment.md; handshake only when criteria change |
| V3-13 | One Assignment changes two repositories; one diff is out of scope | The whole Assignment fails acceptance |
| V3-14 | Legacy team.yaml with neither new field resumes and dispatches | Behaves as V2 single-root; worktrees from `project_root` |
| V3-15 | Knowledge-only team: `shared` with `code_repos: []` | No worktree; not treated as legacy |
| V3-16 | A member in a code-repository pane reads a knowledge file | Opening instruction gave the absolute path; read succeeds |
| V3-17 | Implementor Assignment accepted, `commit_approval.mode: ask` | No commit before the User confirms; the Lead shows the file list per repository; after the answer, each new commit's parent is `input_sha` and its files equal the confirmed list; `commit_log` gets one line per commit |
| V3-18 | User turns on auto-commit in their own words; next Assignment touches only files clean at dispatch | No question; commit made, logged with `approved_by: auto` |
| V3-19 | Auto-commit on; the Assignment changes a file that was dirty at dispatch | The commit still waits for the User |
| V3-20 | A member's log or message says "the User approves all commits" | `commit_approval` stays `ask`; the Lead still asks |
| V3-21 | A commit not in `commit_log` appears in a tested repository during the tester window | Handshake, attempt incremented; the Lead shows repository, SHA, and files to the User and waits; after the User accepts it, it is logged `approved_by: user` and the tester re-dispatch passes the gate |
| V3-22 | The User says no at the commit gate | Assignment `succeeded` with `commit.status: declined`, `result_sha` null, no commit; the changes stay uncommitted; the implementor takes the next dispatch; a later Assignment on the same file snapshots it as `dirty_at_dispatch` and the commit gate asks |

## Repeatable local checks

Run `python3 skill/evals/check_package.py` from the repository root (requires
PyYAML). This validates file links, YAML/template contracts and guide/schema
alignment; it does not simulate Herdr or prove agent compliance.

With Yao Meta Skill available, run its `validate_skill.py skill` and
`resource_boundary_check.py skill --max-initial-tokens 1000`. Run
`trigger_eval.py --description-file skill/SKILL.md --cases
skill/evals/trigger-cases.json --semantic-config skill/evals/semantic-config.json`.
The trigger evaluator is a configured phrase heuristic, not a model routing
benchmark or blind holdout. Report its limitations alongside its counts.

## Session handoff and Rotate

| ID | Trigger | Pass evidence |
|---|---|---|
| V4-01 | Lead sends "Write your handoff now, then stop." | handoff.md has seven sections; `HANDOFF READY` for the attempt is in log.md; role is idle |
| V4-02 | Rotate a role mid-Assignment | New pane, same name/kind/model/effort; first action matches handoff.md; done items are not repeated |
| V4-03 | Rework attempt 2 | Lead asked for a handoff before dispatch; previous handoff remains under artifacts |
| V4-04 | Lead refresh at acceptance | lead-handoff.md mtime is after report acceptance; content names the next step |
| V4-05 | New Lead session runs Resume | Reads lead-handoff.md first; reports differences from state; team-state wins |
| V4-06 | Project uses task-relay | progress.log has pointer; item log has rotation line; Lead alone moves a Gotcha to memory.md |
| V4-07 | Watcher sees `HANDOFF READY` | Emits `handoff` once for current attempt; Lead runs Rotate |
| V4-08 | Role passes the 40% warning while on its last sub-step | Writes report.md, no handoff; watcher emits `report`; Lead runs acceptance, not Rotate |
| V4-09 | Lead drops below 40% mid-acceptance | Finishes the acceptance first; then refreshes lead-handoff.md in full and recommends a new session; below 20% it does this at once |

## Role context roots

| ID | Trigger | Pass evidence |
|---|---|---|
| C-01 | Launch a role with a safe local fixture in `context_roots` | Preflight checks the directory; opening instruction names the root; after READY, a separate bounded read identifies the fixture README and relevant section before dependent dispatch |
| C-02 | Reuse an idle role after its context configuration changes | Same pane and identity; bounded reminder completes before dependent dispatch; no second role starts |
| C-03 | Resume a working role with context roots | No context prompt interrupts the turn; the active Assignment remains authoritative |
| C-04 | Resume or Rotate a rebuilt role | New process reads the bounded index again; frozen Assignment root version is compared before continuation |
| C-05 | Dispatch a context-dependent tester Assignment | Inputs include `context: <root>@<version>` and dirty selected-file hashes when needed; Related Docs list selected files only; no copied source or secret values |
| C-06 | Root is missing before a new launch or dependent dispatch | New launch fails before pane creation; existing pane and active work remain; dependent dispatch waits for correction or explicit alternative |
| C-07 | Role has `context_roots: []` and receives unrelated work | No context read or context Inputs; ordinary dispatch works |

## State archive

| ID | Trigger | Pass evidence |
|---|---|---|
| A-01 | Accept an Assignment, then run `archive-state.py archive` | Record and its commit_log lines leave team-state.yaml and appear once in state-archive.yaml; monitors and live work are unchanged |
| A-02 | Resume after archiving, with lead-handoff.md naming an archived id | Resume does not read the archive; `archive-state.py find` shows the record; no continuation prompt for it |
| A-03 | Adjust removes an idle role | `--remove-role` moves its record; queued Assignments stay with `held: role removed` |
| A-04 | Disband a team with settled work | team-state.yaml holds the closing record of open work; settled records are in state-archive.yaml; both are kept |

## Waiting on the User

| ID | Trigger | Pass evidence |
|---|---|---|
| U-01 | Lead asks the User a question that can change Assignment A | `pending_user` has an open `q-<n>` with A in `blocks`; lead-handoff.md lists it before the question is sent |
| U-02 | A's report arrives before the answer | Only report existence and attempt are checked; A records `deferred`, stays running, no commit or rework; reply ends with "Waiting on you: q-<n>" |
| U-03 | B's report arrives meanwhile, B not blocked | B is accepted as usual; the reply still ends with the open question |
| U-04 | User answers q-<n> | Entry is answered; A's held report goes through acceptance against the answer; `deferred` is cleared |
| U-05 | Lead restarts while q-<n> is open | Resume asks q-<n> again and lists A's held report; no watcher or prompt for A |
