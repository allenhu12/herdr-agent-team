# herdr-agent-team

An agent skill that turns one coding session into a team lead. The lead
plans the work, sends each task to a Sub-Agent in its own Herdr pane,
watches for results, checks them, and reports back.

The skill runs inside [Herdr](https://herdr.dev), a terminal multiplexer
for coding agents. It works with Claude Code and Codex CLI panes.

## What it does

- **Assemble:** start a team of Sub-Agents, each in its own pane, with a chosen model and effort.
- **Dispatch:** write an Assignment, send it to a Sub-Agent, and monitor it in the background.
- **Acceptance:** read the reports, verify the frozen results, and integrate accepted commits.
- **Status and Resume:** check the team state and recover after a restart.
- **Adjust:** add or remove a role, or change a role's model or effort.
- **Rotate:** replace one role's session while its Assignment keeps running.
- **Disband:** close the panes after the User confirms.

Each team keeps its state in a `.herdr-agent-team/` folder at the project
root. Each writer agent gets its own checkout, so two agents do not edit the
same files.

## Requirements

- Herdr, with the `HERDR_ENV=1` variable set in the session.
- The Herdr CLI.
- The agent CLIs you plan to use, for example Claude Code or Codex.

The skill stops if it does not run inside Herdr.

## Install

Copy this folder to the skills directory your agent reads, for example:

```bash
cp -r herdr-agent-team ~/.claude/skills/herdr-agent-team
```

## Use

Ask for a team in plain words:

> Use Herdr to complete this task: improve the internal parser and its tests.
> Use Codex with my deepseek-v4-flash profile.

The skill uses one Sub-Agent when one is enough. Frontend work goes to
Opus by default. Backend, architecture, debugging, and testing go to Codex by
default. Your explicit model choice overrides these defaults.

The [user guide](user-guide.md) has a worked example. The
[Team Templates Guide](team-templates-guide.md) covers templates, the Role
Tree, the Launcher, and Adjust.

## Folder layout

| Path | Contents |
|---|---|
| `SKILL.md` | The entry point the agent loads. |
| `references/` | One file per workflow, plus rules for writers, state files, and monitoring. |
| `assets/` | Templates for team, state, and Assignment files, a watcher script, and a Role Tree renderer. |
| `evals/` | Static package checks (`check_package.py`), trigger cases, and runtime cases. |
| `reports/` | Recorded test results, including the limits of each test. |
| `agents/` | Interface metadata for package compatibility. |

## Testing

Run the static package checks:

```bash
python3 evals/check_package.py
```

These checks do not start Herdr or test agent behavior. The runtime cases in
`evals/runtime-cases.md` need a live Herdr session. Some runtime cases are
not yet run. The reports in `reports/` list which ones.

## Status

This skill is early work. The Rotate workflow and the handoff templates
have static checks only. Their live runtime cases (V4-01 to V4-07) have not
run. Check `reports/v4-session-handoff-rotate-results.md` before you rely on
Rotate.

## License

MIT. See [LICENSE](LICENSE).

Author: HBO (hubo12@gmail.com)
