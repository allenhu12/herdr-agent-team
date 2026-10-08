# Identity and launch

Read before Assemble and before any new, reused, or rebuilt Sub-Agent gets
work. Status only observes these fields; it never repairs them.

## Inventory and ownership

Use `herdr agent list`, `herdr pane list`, and `herdr pane current --current`
with the installed CLI's scope options. Read existing team files first.
Inventory is read-only. Obtain the Lead's current pane from Herdr, not from
the focused pane in another window or a remembered ID.

Reuse only a role with matching recorded name, pane, kind, cwd, and process
identity (agent session ID when available, otherwise a verified PID plus
start time). Check live state before sending anything. Do not adopt an
unrelated pane because it has a familiar name or cwd. Quarantine collisions
and report them. Track whether this team created each Sub-Agent pane.

## Lead Agent identity

For a new team, choose a unique `<task>-lead-<model-label>`, for example
`login-lead-codex`. Keep it separate from the Sub-Agent `roles` collection.
When this session is the Lead (`lead.mode: session`), it is already
running: never use `agent start` to create a replacement merely to give
it a name. Starting a Lead is allowed only for `lead.mode: spawned`,
through the Launcher flow or the quiet-team Lead replacement in
adjust.md.

After verifying the current pane belongs to this Lead and the name is free,
use the installed rename primitives (check help before mutation):

```bash
herdr agent rename <lead-pane-id> login-lead-codex
herdr pane rename <lead-pane-id> login-lead-codex
```

Verify the registered agent name and visible pane label. Record the result
in `team-state.yaml.lead`: name, pane_id, kind, cwd, process_identity, and
identity_verified_at. Model/effort are observed separately when available;
use null and report unavailable values rather than infer them from a label.
The strict explicit-launch rule applies to Sub-Agents launched by this
skill, not retroactively to the already-running Lead.

If detection or naming fails, stop new dispatch and report the missing
identity; do not forge agent lifecycle/session metadata to make it pass.
Only rename this session's verified pane. Preserve an already-established
Lead name during ordinary reuse. Include `Lead Agent: <name> → <pane-id>`
in roster, Status, Resume, and final reports, and in opening instructions.

Keep `up_agent: lead` and `position.from: lead` as schema aliases. Resolve
them through `team-state.yaml.lead`, not a guessed literal agent called
`lead`. Give Sub-Agents the absolute state-file path; they re-read it to
locate the Lead after a move. Identity is not messaging permission: use
report/log handoff and the existing monitor; do not inject prompts into a
working Lead.

On Resume, verify the current Lead's ownership and the old record. A moved
Lead may update the mapping atomically only after confirming the prior Lead
is gone or an explicit handoff identifies this session as its successor.
Two live Leads must not write one team's state. If succession is ambiguous,
report the conflict and do not take ownership. Keep the old identity in
`lead_history`. Never close the Lead during Disband.

## Sub-Agent selection and naming

Use one Sub-Agent for a task it can complete. Add one only for independent
work or an independent review. Preserve a roster explicitly requested by
the User. Defaults: frontend → `kind: claude`, `model: opus`; backend,
architecture, debugging, testing → `kind: codex`. Codex is a CLI kind, not
an exact model. Resolve its model from explicit User/team configuration;
ask only when it remains unspecified. User model/kind/effort choices win.

New names follow `<task>-<role>-<model-label>`, short lowercase words with
hyphens, at most 32 characters, unique across live agents including Lead.
Examples: `login-ui-opus`, `login-review-codex`, `login-api-deepseek`.
Shorten task/role words and check collisions; never silently truncate.
`model_label` is a readable suffix, not evidence of the exact model. It
may be a CLI word (`codex`, `opus`) or a model word (`astra`, `sol`,
`luna`, `deepseek`), for example `dev-tester-luna`.
Legacy names remain readable; see migration in `state-files.md`.

## Resolve launch arguments before splitting any pane

Record `kind`, `model`, optional `profile`, `effort` (default `high`), and
the argument array in the team definition. Check each installed CLI's help
for flag syntax. Help need not enumerate all supported model IDs; use an
explicit configured ID or documented alias and verify it at runtime.
Revalidate mappings when CLI version, configuration, or desired model changes.

Examples of application arguments after Herdr's `--`:

| Kind/selection | Arguments |
|---|---|
| Claude Code / Opus | `--model opus --effort high` |
| Codex / explicit model | `-m <exact-model> -c 'model_reasoning_effort="high"'` |
| Codex / DeepSeek Flash profile | `-p deepseek-v4-flash -m deepseek-v4-flash -c 'model_reasoning_effort="high"'` |

DeepSeek must start through `codex -p deepseek-v4-flash`; retain `-p` when
adding explicit model/effort. Find the profile where the installed Codex
reads it; check `codex --help` for `-p`. codex-cli 0.154.0 layers a
separate file, `$CODEX_HOME/<name>.config.toml` (usually
`~/.codex/deepseek-v4-flash.config.toml`), over the base config. Older
versions used a `[profiles.<name>]` block in `config.toml`; do not
report a profile as missing only because that block is absent. Validate
that the profile selects the intended model/provider, reading only
necessary non-secret keys (`model`, `model_provider`). A missing
or conflicting profile fails preflight. Do not edit credentials or substitute
another provider. For other kinds, use their documented explicit flags; an
unsupported effort needs a User decision, not an inherited default.

## Effort levels

Effort must be valid for the kind. Check the installed CLI's help when
its version changes; this table records what the help showed on
2026-09-11 (Claude Code 2.1.268, codex-cli 0.154.0):

| Kind | Valid effort values | Flag |
|---|---|---|
| claude | low, medium, high, xhigh, max | `--effort <level>` |
| codex | low, medium, high, xhigh | `-c 'model_reasoning_effort="<level>"'` |

A value outside the list fails preflight with the kind and level named.
Never map it to a nearby level (for example `max` to `xhigh`) without the
User choosing that. `assets/render-role-tree.py` enforces the same table.

Pass arguments as separate safely quoted tokens. Do not execute a model,
profile, name, or path as shell text. Record CLI versions and non-secret
resolved arguments; do not persist environment dumps or credentials.

## Permission arguments: `permissions: inherit | scoped`

team.yaml has one top-level `permissions` field. It applies to every
agent the skill launches, including a spawned Lead.

- **`inherit` (default).** Pass no sandbox, approval, or permission-mode
  flags. Each agent follows the User's own CLI configuration, for example
  `approval_policy` and `sandbox_mode` in `~/.codex/config.toml`, or the
  permission settings of Claude Code. Model, profile, and effort flags
  stay explicit. Command-line flags override CLI config, so adding a
  sandbox flag here would silently replace the User's chosen defaults.
  If the User's config runs agents without a sandbox, that is the User's
  decision; the skill does not narrow or widen it. If the config makes an
  agent prompt, those prompts reach the Lead as `blocked` and follow the
  normal escalation rules.
- **`scoped`.** Use the arguments below. Choose this only when the User
  asks for it. Known limit (runtime case V2-23, 2026-09-11): Codex's
  `workspace-write` sandbox blocks the Herdr socket, so a Codex Lead under
  `scoped` needs approval for every `herdr` command. Do not use `scoped`
  for a spawned Codex Lead until an allow rule for the socket is verified.

### Scoped arguments (`permissions: scoped` only)

Add these to every writer Sub-Agent's launch arguments, alongside the
model/effort flags above. They pre-authorize ordinary in-scope file edits so
the CLI stops prompting for them — no change to what a Sub-Agent is allowed
to touch, only to whether touching it interrupts the Lead. The write scope
itself is still governed entirely by `writer-rules.md`'s role ceiling and
Assignment lease; these flags never widen it.

| Kind | Additional launch arguments |
|---|---|
| Claude Code | `--permission-mode acceptEdits --add-dir <workspace-dir>` |
| Codex | `-s workspace-write --add-dir <workspace-dir> -a on-request` |
| Other kinds | Use the kind's documented equivalent (edits inside a declared directory don't prompt; everything else still does). Missing an equivalent is a dispatch gate, not a reason to fall back to a wider bypass flag. |

`<workspace-dir>` is the Assignment's absolute Workspace Dir; a writer role
also needs its checkout directory listed the same way so edits there don't
prompt either. In a two-root team, also list each code repository or
knowledge directory its write_ceiling reaches (for a shared-mode tester, only
its declared output directories). Never use a full-bypass flag (Claude Code's
`--dangerously-skip-permissions` / `--allow-dangerously-skip-permissions`,
Codex's `--dangerously-bypass-approvals-and-sandbox`) to reach this —
those remove the sandbox and the approval boundary entirely, which
conflicts with the escalation rules in `monitoring.md`. A shell command with
a side effect, a path outside the declared directories, network access, or
anything the kind classifies as dangerous must still prompt and still
escalate to the User under the existing rules — nothing here relaxes that.

Under `inherit` there are no permission arguments to record; the
`permissions` field itself is the audit record. Under `scoped`, record the
resolved permission arguments in `team.yaml.launch_args`
alongside the model/effort arguments, so they're visible and auditable, not
hidden in a settings file. Reader roles (`access: reader`) get no edit
pre-authorization — they have no write scope to pre-authorize in the first
place.

## Launcher and spawned Lead

A team has exactly one Lead at any time. When the User says the current
session should not be the Lead, the current session acts as the Launcher
(assemble.md steps 4b and 6b):

- The Launcher starts the Lead pane with explicit arguments from the
  effective `lead` fields and verifies its header like any Sub-Agent.
  Its permission arguments follow the team's `permissions` field. Under
  `inherit` it gets none and follows the User's CLI config. Under
  `scoped` it would get the writer arguments limited to the project root
  and `team_dir`, but see the known Codex limit above.
- The Launcher creates the Sub-Agent panes anchored on the new Lead pane
  and writes the first team.yaml and team-state.yaml.
- Handoff order: finish every write, then send the Lead one prompt
  telling it to load the skill and run Resume. After handoff the Launcher
  never writes a team file, never dispatches, and never relays messages.
  It is not a proxy.
- The spawned Lead's Resume accepts ownership when its own pane equals
  `lead.pane_id` and `lead.launched_by_team` is true or a handoff record
  names it. A live Launcher pane is not a competing Lead.
- If the Launcher session later receives a team request, it reads
  team-state.yaml, sees a `launcher` record for its own pane with a later
  `handoff_at`, refuses Lead workflows, and points the User at the Lead
  pane.

## Verify before prompting

After each launch, verify name, actual model, and effort in the pane header
against the resolved arguments before even the opening identity prompt.
Check `agent get`, `pane get`, and available header inspection; a terminal
read may omit the host header. Use supported visual inspection if necessary.
A documented alias such as Opus must resolve to that family; record the
observed exact model so independent review can compare actual models.

Record timestamp, process identity, observed name/model/effort, and an
evidence path in `launch_verification`. These are historical observations,
not persisted live lifecycle state. A changed process/session invalidates
them. Recheck configuration before reuse, continuation, or new dispatch.

If any required field is absent, wrong, or unverifiable, stop further launch
and dispatch and tell the User. Leave prior agents and their monitors intact.
`pane report-metadata` is display-only: never set desired model/effort labels
and treat them as verification. An integration fix or explicitly approved
alternative is required when Herdr cannot expose the required header.

When first verified for a CLI version, record the exact footer text used to
read its remaining-context percentage. Do not treat the percentage as a
completion signal. Status and acceptance may read it only at the moments
listed in status.md and the handoff rules.
