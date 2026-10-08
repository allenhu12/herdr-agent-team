# herdr-agent-team User Guide

This skill turns the current session into the Lead Agent, or into a
Launcher that starts a separate Lead pane and steps back. It defines
Assignments, sends them to Sub-Agents in Herdr panes, monitors completion,
reviews frozen results, and verifies the integrated result. Sub-Agents do
routine implementation; the Lead can integrate accepted commits and run checks.

## Requirements and invocation

Run inside Herdr (`HERDR_ENV=1`) with the Herdr CLI/skill and the selected
agent CLIs installed. Ask, for example:

> Use Herdr to complete this task: improve the internal parser and its tests.
> Use Codex with my deepseek-v4-flash profile.

The skill starts with an agent/pane inventory. It uses one Sub-Agent when
sufficient. Frontend defaults to Opus; backend, architecture, debugging, and
testing default to Codex. An explicit model choice overrides those defaults.
Codex alone does not identify an exact model; supply it or configure it in
team.yaml. Another Sub-Agent is justified by independent work or review.

Requests to explain Herdr, edit this skill, or evaluate a quoted prompt do
not start an operational team.

## Find the Lead Agent

Both the registered agent name and pane label identify the Lead, for example:

```
Lead Agent: parser-lead-codex → pane w1:p1
Sub-Agent:  parser-api-deepseek → pane w1:p2
```

The Lead is the current session, not a new agent launched for naming.
The canonical team-state.yaml stores its name and pane in a separate lead
entry. Opening instructions give every Sub-Agent this identity and the
absolute state path. Status displays the Lead first. On a validated handoff,
Resume updates the mapping and retains history.

The alias `up_agent: lead` still works through that mapping. Knowing the
pane does not authorize interrupting it; reports, logs, and Herdr monitors
remain the handoff mechanism.

## One control directory, one writer per checkout

```
canonical-project/.herdr-agent-team/   # team_dir; or .herdr-agent-team-<team-id>
  team.yaml
  team-state.yaml
  role-tree.md                      # rendered from team.yaml, read-only
  assignments/<id>/
    assignment.md
    log.md
    report.md
    artifacts/attempt-1/<version>/    # only with an explicit output grant

writer-checkout/                     # implementation, separate git index
integration-checkout/                # accepted work and final checks
```

Workspace Dir means the Assignment's metadata/output directory. Checkout
Dir means the source tree. A writer pane uses its own checkout as cwd and
absolute paths to the canonical Assignment. It never creates another copy
of team state.

This layout shows isolated mode. New teams use shared mode unless you ask
for isolated. Two writers cannot write one checkout at the same time, even
with disjoint file grants. In isolated mode each writer
has a separate worktree or checkout. Logical path ownership still applies:
two worktrees do not authorize simultaneous edits to the same logical file.
Readers can share a checkout and write their own reports. A test or formatter
that changes project files requires writer access. Non-git projects use
hashed snapshots and separate copies, or one writer when isolation fails.

## Worked example

### Assemble

The Lead resolves the team configuration and validates all launch mappings
before creating panes. It preserves compatible existing roles and foreign
panes. Starting with assets/team.yaml.template, the parser role would use:

```yaml
name: parser-api-deepseek
responsibility: Improve the internal parser and its tests.
kind: codex
model: deepseek-v4-flash
model_label: deepseek
profile: deepseek-v4-flash
effort: high
launch_args: ["-p", "deepseek-v4-flash", "-m", "deepseek-v4-flash", "-c", 'model_reasoning_effort="high"']
access: writer
checkout_dir: /absolute/parser-writer
position: {direction: right, from: lead}
write_ceiling: ["src/parser/**", "tests/parser/**"]
up_agent: lead
low_agent: []
```

This is an illustrative role fragment, not a complete team definition.
The launch is equivalent to:

```bash
codex -p deepseek-v4-flash -m deepseek-v4-flash -c 'model_reasoning_effort="high"'
```

There are no sandbox or approval flags, because teams default to
`permissions: inherit`. Each agent follows your own CLI config, for
example `approval_policy` and `sandbox_mode` in `~/.codex/config.toml`.
Command-line flags would override that config. Set `permissions: scoped`
in team.yaml only if you want the skill to add
`-s workspace-write --add-dir <dir> -a on-request` instead. Under scoped,
a Codex Lead must approve every `herdr` command, because the sandbox
blocks the Herdr socket.

The profile selects provider configuration. Explicit flags select the model
and effort. For frontend work the default is `claude --model opus --effort
high`. After each launch the Lead verifies the name, actual model, and
effort in the pane header before sending even the opening instruction.
Missing/wrong fields stop dispatch. Display labels are not proof of settings.

### Dispatch and accept

The Lead writes the Assignment before prompting: one outcome, full starting
commit SHA, checkout, allowed paths, exclusions, actual project checks with
cwd, and artifact format. The Sub-Agent inspects code and finds exact edits.
The Lead backgrounds `assets/watch-assignment.sh` through the host's
background-task facility when other work continues. The script sends the
opening prompt itself, then only wakes the Lead on an outcome that needs a
decision — a written `report.md`, a permission request held past 20
seconds, or a real timeout — never on an in-scope permission prompt the
Sub-Agent was already launched authorized to answer itself, and never on
an ordinary intermediate `working` state.

A settled pane is only a signal to inspect the current-attempt report. The
report has id/attempt/status metadata and six content sections:

1. Result
2. Frozen commit or artifact path
3. Files changed
4. Test results
5. Screenshot paths
6. Unresolved issues

Use full commit SHAs or versioned artifact paths with content hashes. No
full logs or source files in the report. Use not applicable/not run with
reasons. Rework keeps the Assignment ID and increases attempt, up to three.

The Lead reads the report, audits scope, and inspects relevant risky diffs.
Visual work also needs matching screenshots and a running page built from
the reviewed version. Independent review uses another actual model and a
specific commit/hash. Factual disagreements are tested; the Lead decides
judgment calls. Review is required for User requests, security/public
behavior boundaries, or material unresolved acceptance concerns.

Accepted work is integrated in one checkout. The Lead reruns the project's
real checks there; Sub-Agent test success alone does not prove integration.
Any conflict-resolution code is assigned to a Sub-Agent with exclusive
ownership of that checkout while it works.

### Knowledge base and code repositories (shared mode)

Many projects keep two kinds of repository. The knowledge base holds plans,
progress, and decisions. The code repositories hold the product code. Set up
the team inside the knowledge base. That folder is the project root, also
called the knowledge root.

```
knowledge-base/                      # project_root, never split
  .herdr-agent-team/                 # team_dir
  plans/  docs/  00-current/ ...
/src/frontend/                       # code_repos[0], the User's own checkout
/src/backend/                        # code_repos[1]
```

team.yaml lists the code repositories under `code_repos`. Set
`checkout_mode: shared` when worktrees cost too much, for example with many
repositories. The develop template does this. In shared mode:

- No member gets a worktree. All members read the same knowledge files by
  absolute path, so everyone sees the same plan and progress.
- The implementor is the only role that edits source code. Other members
  ask the implementor for a code change, or ask the Lead to pass it on.
- The tester runs tests only after the Lead accepts the implementor's
  work. The tester writes only build, cache, and test output paths. A check
  before and after the tests proves that the code did not change.
- The Lead writes the shared progress and plan files. Some paths are
  protected, and no member can get a grant for them.
- Before a dispatch, the Lead records your uncommitted files. If the work
  must change one of them, the Lead saves a copy first, so it can tell
  your lines from the implementor's lines.
- Nothing goes into git without you. The implementor edits but does not
  commit. After the Lead accepts the work, it shows you the files to
  commit, and marks files that held your uncommitted changes. You say yes,
  and then the implementor commits exactly those files.
- To skip that question, say so in your own words, for example "commit
  accepted work without asking me". Files that held your uncommitted
  changes still come to you. Say "ask me again" to turn it off; Disband
  also turns it off. Push, merge, and branch changes always need you.

A team.yaml with neither `checkout_mode` nor `code_repos` is an older
single-root team. It keeps working as before.

### Team templates and the Role Tree

For a full walk-through with one example from start to end, read the
[Team Templates Guide](team-templates-guide.md). This section is a short
summary.

Ask for a team by type:

> Use the herdr agent team skill to create a develop team.

The skill looks for `assets/teams/develop/team.yaml`. The develop
template has a Lead suggestion (codex gpt-6-astra, medium) and three
Sub-Agents: implementor (codex gpt-5.6-sol, medium), tester (codex
gpt-5.6-luna, xhigh), and writer (claude opus, medium). A template seeds
only a new team. If the team folder already has a team.yaml, the skill
keeps it and uses Adjust for changes.

If no template matches, the skill interviews you one question at a time,
shows the Role Tree, and asks once to confirm. After a good assemble it
offers to save the team as a new template.

The Role Tree is rendered from team.yaml and never edited by hand. For
the develop template it looks like this:

```text
lead  [template suggestion]
|  codex · gpt-6-astra · medium
|  Design, bug analysis, review, and orchestration.
|
+-- <task>-implementor-sol
|     codex · gpt-5.6-sol · medium · writer
|
+-- <task>-tester-luna
|     codex · gpt-5.6-luna · xhigh · writer
|
`-- <task>-writer-opus
      claude · opus · medium · writer

+----------+------------------------+
|          | <task>-implementor-sol |
|          +------------------------+
|   lead   |   <task>-tester-luna   |
|          +------------------------+
|          |   <task>-writer-opus   |
+----------+------------------------+
```

The layout is fixed: the Lead on the left, Sub-Agents stacked top to
bottom on the right. Effort must be valid for the kind. Codex has no
`max`, so a Codex role set to `max` fails preflight.

### This session as Lead, or a separate Lead pane

Before creating a team the skill asks whether this session should be the
Lead.

- **Yes.** This session is the Lead. The template's Lead suggestion is
  only advice. The Role Tree shows this session's real model and effort,
  or `unknown`.
- **No.** This session is the Launcher. It starts a Lead pane with the
  template's Lead settings, then the Sub-Agent panes to its right. It
  writes the first team files, tells the new Lead to run Resume, and
  steps back. From then on you talk to the Lead pane. The Launcher does
  not relay messages.

### Several teams in one project

Each team has its own folder at the project root, for example
`.herdr-agent-team-dev` and `.herdr-agent-team-investment`. Name the team
when more than one exists; the skill never guesses. The Team ID is also
the default prefix for agent names, such as `dev-tester-luna`.

### Adjust a live team

> Add a DeepSeek implementer to the dev team.

Adjust adds `dev-implementer-deepseek` at the bottom of the right-hand
stack, launched with `codex -p deepseek-v4-flash -m deepseek-v4-flash`.
Codex reads that profile from `~/.codex/deepseek-v4-flash.config.toml`,
layered over your base config. If the file is missing or selects another
model, preflight stops.

> Replace the dev tester's effort with high.

Adjust refuses a busy role. For an idle role it checks the new settings
first, then restarts the pane with the new flags and verifies the header.
If the model label changes, the role is renamed and the old name is kept
in its history. Every change re-renders the Role Tree.

A spawned Lead can be replaced only when the team is quiet: no active
Assignment and no running monitor. A session Lead cannot replace itself.

### Status, Resume, Disband

Status reads state and Herdr observations, displays the Lead and roster,
and flags mismatches. It does not rename, repair, dispatch, or write files.

Resume validates the Lead handoff and each role's pane/kind/cwd/process and
configuration. Working agents get a bare wait, not a continuation prompt.
Settled current reports go to acceptance. Gone agents are rebuilt with
explicit launch checks while preserving their checkouts. Name collisions
are quarantined. Blocked waits are not re-armed in a tight loop.

### Rotate a role with an active Assignment

When a role warns that less than 25% context remains, it finishes its
current sub-step, records a checkpoint, writes its handoff, and stops. The
Lead then runs Rotate. For example, an active `parser-api` Assignment can
continue in a fresh session without changing its ID or attempt:

1. Confirm `assignments/parser-api/handoff.md` is for the current attempt.
2. Stop the old pane and keep it open read-only while the replacement starts.
3. Rebuild `parser-api` with the same kind, model, effort, and checkout.
4. Prompt it through the watcher to read `assignment.md`, `handoff.md`, and
   log entries after the last checkpoint. It starts with the listed first
   action and does not redo completed work.
5. Update the role pane/process verification and rotation history. Keep the
   Assignment `running`; record the new watcher handle and report the rotate.

Disband lists exact agent/pane targets and requires explicit confirmation.
It stops monitors, validates ownership, archives outcomes before closure,
and closes only team-created Sub-Agent panes. It retains the Lead and
reports remaining worktrees and servers; those need separate cleanup scope.

## Existing v1 teams

Old state, names, reports, and archives remain readable. Status never
migrates. Active work is not renamed or interrupted just to enforce v2.
Before a new/continuation dispatch, missing launch evidence and shared writer
checkouts must be resolved at a safe boundary. Migration preserves history.
A missing Lead identity is shown explicitly until it is verified and recorded.

## Common limits

- Busy role: reject or record separate queued work; never overwrite its Assignment.
- Scope outside role ceiling: reject before writing the Assignment or prompting.
- Missing header model/effort: report the gap; do not fill a label and call it verified.
- Blocked question: the Lead handles only pre-authorized in-scope questions;
  existing permission/deletion/publishing/credential/spend escalation remains.
- Cancellation: keypresses may leave background jobs running. Verify file
  stability or process death; exact-PID termination follows the existing
  explicit User-decision rule.
- Final output: result, verification, unresolved issues, Lead/role panes,
  worktrees, monitors, and servers. Do not push/publish/deploy/touch production
  or expose secrets without explicit approval.
