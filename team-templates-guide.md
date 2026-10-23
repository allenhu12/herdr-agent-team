# Team Templates Guide

This guide shows how to build an agent team from a template, read its
Role Tree, change the team while it runs, and close it. It follows one
example from start to end.

For the full skill (Dispatch, acceptance, Resume, writer checkouts), read
the [user guide](user-guide.md). This guide covers only the team-template
features.

## What you get

- **Team Templates.** A template is a ready team definition. The skill
  ships one template, `develop`. It lives in
  [assets/teams/develop/team.yaml](assets/teams/develop/team.yaml).
- **A Role Tree.** The skill draws the team as a text tree and saves it
  as `role-tree.md` in the team folder. The skill makes this file from
  `team.yaml`. Do not edit the tree. Change `team.yaml` instead.
- **A fixed layout.** The Lead is on the left. The Sub-Agents are
  stacked top to bottom on the right.
- **Two ways to lead.** Your current session can be the Lead. Or the
  skill can start a separate Lead pane and step back.
- **Changes while the team runs.** You can add a role, remove a role, or
  change a role's model or effort level.
- **Several teams in one project.** Each team has its own folder.

## Before you start

Check these items once:

1. Run your agent session inside Herdr. The check is
   `test "$HERDR_ENV" = 1`.
2. Install the CLIs that the template uses. The `develop` template uses
   `codex` and `claude`.
3. Install `python3` with PyYAML. The skill needs it to draw the Role
   Tree. Without it, the skill stops before it creates any pane.
4. Set up the team in your knowledge base: the folder with your plans,
   progress, and decisions. Know the path of each code repository. The
   `develop` template uses shared mode: it creates no git worktrees, and
   all members work in your own checkout of each code repository.

## The develop template

| Role | Kind | Model | Effort | Job |
|---|---|---|---|---|
| Lead (suggested) | codex | gpt-6-astra | medium | Design, bug analysis, review, orchestration |
| implementor | codex | gpt-5.6-sol | medium | The only role that edits source code. Implements the plan and makes code changes that other members ask for |
| tester | codex | gpt-5.6-luna | xhigh | Builds the test environment and runs the tests |
| writer | claude | opus | medium | Writes documents and diagrams, answers questions |

The Lead line is a suggestion. It is used only when the skill starts a
separate Lead pane.

In shared mode the tester and the writer never edit source code. When they
need a code change, they ask the implementor, or they ask the Lead to pass
the request on. The tester runs tests only after the Lead accepts the
implementor's work. The tester writes only build, cache, and test output
paths. The [user guide](user-guide.md) explains shared mode in full.

## Example: a team for a login feature

You work on a web app. You want a team to add a login page. You call the
team `login`.

### Step 1. Ask for the team

In your agent session, type:

> Use the herdr agent team skill to create a develop team called login.

The skill does these things before it creates anything:

1. It lists the live agents and panes. It does not touch panes that are
   not part of this team.
2. It finds or creates the team folder `.herdr-agent-team-login` at the
   project root. `login` is the Team ID.
3. It checks that no `team.yaml` exists in that folder yet. If one exists,
   the skill keeps it and does not copy the template over it.
4. It finds the code repository paths in your knowledge base, or asks you
   for them. It shows the list in the configuration.
5. It asks you one question:

   > Should this session be the Lead?

Answer **yes** for this example. Step 7 shows the **no** path.

### Step 2. The skill builds the team

The skill copies the template into the team folder and fills in your
project paths. The agent names use the Team ID as a prefix:

- `login-lead-opus` (this session)
- `login-implementor-sol`
- `login-tester-luna`
- `login-writer-opus`

Your session may not use the template's Lead model. Then the skill tells
you once and continues, for example:

> Template suggests codex gpt-6-astra medium. This session is claude
> Opus 5. Continuing with this session.

Then the skill creates the panes, one at a time:

1. It splits a pane to the right of your session and starts the
   implementor. Its pane opens in the main code repository.
2. It splits down from the implementor and starts the tester. The tester
   and the writer open in the knowledge base.
3. It splits down from the tester and starts the writer.

After each start, the skill reads the pane header. It checks that the
model and effort match `team.yaml`. If one does not match, the skill
stops and tells you. It sends no work to an agent it could not verify.

**Answer the trust prompts.** The first time Codex or Claude Code opens
a new repository, it asks "Do you trust this folder?". Answer it in that
pane. In Claude Code the cursor starts on "No, exit", so move to "Yes, I
trust this folder" before you press Enter. Codex asks once per
folder, so it can ask once in the knowledge base and once in the code
repository.

### Step 3. Read the Role Tree

When the team is ready, the skill prints the tree and saves it as
`.herdr-agent-team-login/role-tree.md`:

```text
login-lead-opus  [this session]
|  claude · Opus 5 · unknown
|  Design, bug analysis, review, and orchestration.
|
+-- login-implementor-sol
|     codex · gpt-5.6-sol · medium · writer
|     The only source code writer. Implements the plan and makes code changes other members request by message.
|
+-- login-tester-luna
|     codex · gpt-5.6-luna · xhigh · writer
|     Builds the test environment and runs the tests.
|
`-- login-writer-opus
      claude · opus · medium · writer
      Writes documents, draws visual diagrams, explains and answers questions.
```

```text
+-----------------+------------------------+
|                 | login-implementor-sol  |
|                 +------------------------+
| login-lead-opus |   login-tester-luna    |
|                 +------------------------+
|                 |   login-writer-opus    |
+-----------------+------------------------+
```

How to read it:

- `[this session]` means your session is the Lead. `[spawned]` means the
  skill started a separate Lead pane.
- `unknown` means Herdr could not show that value. The skill never
  guesses a model or effort level.
- Each Sub-Agent line shows kind, model, effort, and access. `writer`
  means the role can change the files that its Assignment grants. In the
  develop template only the implementor may change source code.

### Step 4. Give the team work

Talk to the Lead as usual:

> Add a login page with email and password. The implementor builds it
> and writes the tests, the tester runs the tests, and the writer
> documents the login flow.

The Lead writes one Assignment per role, sends it, and waits for each
report. Then it checks the results and reports to you. The
[user guide](user-guide.md) explains Assignments, reports, and acceptance
in full.

**Nothing goes into git without you.** The implementor edits the code but
does not commit. After the Lead accepts the work, it shows you the files
to commit and marks files that already held your own uncommitted changes.
You say yes, and the implementor commits exactly those files. If you say
no, the changes stay uncommitted and the team goes on with other work.

To skip the question, say so in your own words, for example "commit
accepted work without asking me". Files that held your uncommitted
changes still come to you. Say "ask me again before commits" to turn it
off. Push, merge, and branch changes always need you.

To see the team at any time, ask:

> Check the status of the login team.

Status only reads. It shows the team folder, the Role Tree path, the
Lead, and each role's state. It never changes anything.

### Step 5. Change a role while the team runs

Use the Adjust workflow.

**Change an effort level:**

> Change the login tester's effort to high.

1. The skill checks that the tester is idle. A busy role is refused. The
   skill tells you which work must finish first.
2. It checks the new settings before it stops anything. If a check
   fails, the old tester keeps running.
3. It restarts the tester pane with the new flags and verifies the header.
4. It updates `team.yaml` and draws the Role Tree again.

A new model can change the model word in the name. For example,
`login-tester-luna` becomes `login-tester-sol`. The skill keeps the old
name in the role's history. It also moves queued work and the next
role's pane anchor to the new name.

**Add a role:**

> Add a DeepSeek reviewer to the login team.

The skill adds `login-reviewer-deepseek` at the bottom of the
right-hand stack as a reader.
The login team runs in shared mode, so the skill refuses a second role
that may edit source code. To use DeepSeek for code, replace the
implementor's model instead. It starts Codex with your DeepSeek profile:

```bash
codex -p deepseek-v4-flash -m deepseek-v4-flash -c 'model_reasoning_effort="high"'
```

Codex reads that profile from `~/.codex/deepseek-v4-flash.config.toml`.
If the file is missing or selects another model, the skill stops.

**Remove a role:**

> Remove the writer from the login team.

The skill refuses a busy role. For an idle role, it closes the pane and
removes the role from `team.yaml`. It keeps any queued work for that
role and lists it for you.

### Step 6. Close the team

> Disband the login team.

The skill lists the panes it will close and waits for you to confirm.
Then it checks each pane again and closes only the Sub-Agent panes it
created. It keeps the Lead pane. It turns the auto-commit switch off. A
shared-mode team has no worktrees. For an isolated team, Disband does not
delete worktrees; it tells you which ones remain.

## Step 7. Use a separate Lead pane

Ask for the team again, and answer **no** to "Should this session be the
Lead?". This session becomes the **Launcher**:

1. The Launcher starts a Lead pane to its right with the template's Lead
   settings (codex gpt-6-astra, medium) and verifies the header.
2. It creates the three Sub-Agents to the right of the new Lead.
3. It writes the team files, then tells the new Lead to take over.
4. It steps back. From now on, talk to the Lead pane.

```text
+-----------+------------------+------------------------+
|           |                  | login-implementor-sol  |
|           |                  +------------------------+
| Launcher  | login-lead-astra |   login-tester-luna    |
| (you)     |                  +------------------------+
|           |                  |   login-writer-opus    |
+-----------+------------------+------------------------+
```

After the handoff, the Launcher never writes team files and never
relays messages. If you ask the Launcher to run the team, it names the
Lead pane and stops.

## Build a team with no template

> Use the herdr agent team skill to create a research team.

No `research` template exists, so the skill interviews you. It asks one
question at a time, and each question shows a default:

1. How many Sub-Agents? (default: 1)
2. The Lead's kind, model, and effort, only if the skill starts a Lead
   pane.
3. For each Sub-Agent: a role word, a one-line job, the kind, the model,
   the effort, and writer or reader access.

The skill does not ask about pane positions, because the layout is
fixed. It also does not ask about the checkout mode: a team with no
template uses shared mode, so no member gets a worktree. Say "use
isolated mode" only when two members must edit one code repository at the
same time; then each writer gets its own worktree.

For one or two helpers, you do not need a team type at all:

> Use Herdr to complete this task: fix the login timeout. Use one Codex
> gpt-5.6-sol Sub-Agent.

The skill then uses the smallest team, one Sub-Agent by default. It shows the Role Tree and asks you to confirm once. After a
good start, it offers to save the team as a new template in
`assets/teams/research/team.yaml`. Next time, "create a research team"
uses that template.

## Several teams in one project

Each team has its own folder at the project root:

```text
my-app/
  .herdr-agent-team-login/
  .herdr-agent-team-billing/
```

- Name the team in every request when more than one folder exists, for
  example "check the status of the billing team". If you do not name
  one, the skill lists the teams and asks. It never guesses.
- Agent names must be unique across all teams. The Team ID prefix keeps
  them apart: `login-tester-luna` and `billing-tester-luna`.
- A team with no suffix uses the default folder `.herdr-agent-team`.

## Reference

### Files in the team folder

| File | Owner | Purpose |
|---|---|---|
| `team.yaml` | Lead | The team definition, and the only source of truth |
| `team-state.yaml` | Lead | Live state: panes, sessions, Assignments, monitors |
| `state-archive.yaml` | Lead | Settled Assignments and old history, moved out by `assets/archive-state.py` |
| `role-tree.md` | Lead | The drawn tree; the skill makes it from `team.yaml` |
| `assignments/<id>/` | Lead and one Sub-Agent | One folder per piece of work |

To draw the tree yourself:

```bash
python3 skill/assets/render-role-tree.py .herdr-agent-team-login/team.yaml
```

The script fails with exit code 2 if the layout is not the fixed chain,
or if an effort level is not valid for its kind.

### Effort levels

| Kind | Valid effort levels |
|---|---|
| claude | low, medium, high, xhigh, max |
| codex | low, medium, high, xhigh |

Codex has no `max`. If you ask for `max` on a Codex role, preflight
stops. The skill does not change it to `xhigh` for you.

### Permissions

`team.yaml` has one `permissions` field:

- **`inherit` (default).** The skill adds no sandbox or approval flags.
  Each agent uses your own CLI config, for example `approval_policy` and
  `sandbox_mode` in `~/.codex/config.toml`.
- **`scoped`.** The skill adds sandbox flags such as
  `-s workspace-write -a on-request`. These flags override your config.
  They also block the Herdr socket, so a Codex Lead must approve every
  `herdr` command. Use `scoped` only if you want that.

### Prompt files for a role

A template role can name a `prompt_file`. The skill adds that file's
text to the role's first instruction. A role can also list `skills` by
name. For now, the skill only mentions them in the first instruction.
Put prompt files in the template's `prompts/` folder. The skill stores
their absolute paths when it creates a team.

### Local context for a role

Add `context_roots` to a real team's role when its tasks need a local
repository or documentation directory. Use absolute paths; leave the
built-in template defaults as `[]`. For example, set a tester role to:

```yaml
context_roots:
  - /absolute/path/to/test-framework
```

The Lead validates the directory before launch. After the role's READY
reply, it asks for a small first read, starting with README.md when
available. A related Assignment records the root and version in Inputs,
then lists only the needed files in Related Docs. The role reads those
files before relevant commands. An unrelated Assignment can omit the
root. `context_roots` grants no extra write or device access. A missing
path blocks only new work that needs it; active work stays intact.

## Known limits

These limits were found in live tests on 2026-09-11. See
[reports/role-tree-runtime-results.md](reports/role-tree-runtime-results.md)
and [reports/shared-mode-runtime-results.md](reports/shared-mode-runtime-results.md).

- **Trust prompts.** You must answer the first "Do you trust this
  folder?" prompt in each new repository yourself.
- **A CLI can change its own model.** In one test Codex switched a
  member from gpt-5.6-sol to gpt-5.6-luna with no agent action. The Lead
  now checks the model shown in the pane before every work prompt and
  asks you when it has changed.
- **Uneven pane heights.** The first Sub-Agent gets half of the
  right-hand column. The others get a quarter each. You can resize the
  panes in Herdr.
- **Layout after changes.** Removing or replacing a role does not move
  the other panes. The skill reports the layout it sees.
- **Untested cases.** The interview, Adjust, several teams, and Lead
  replacement follow the written workflow, but live tests for them have
  not run yet.

## Quick reference

| You want to | Say |
|---|---|
| Create a team from a template | "Use the herdr agent team skill to create a develop team called login." |
| See the team | "Check the status of the login team." |
| Change an effort level | "Change the login tester's effort to high." |
| Change a model | "Replace the login tester's model with gpt-5.6-sol." |
| Add a role | "Add a DeepSeek reviewer to the login team." |
| Remove a role | "Remove the writer from the login team." |
| Recover after a restart | "Resume the login team." |
| Commit without being asked | "Commit accepted work without asking me." |
| Be asked again before commits | "Ask me again before commits." |
| Close the team | "Disband the login team." |
