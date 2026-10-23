# herdr-agent-team

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Status: early](https://img.shields.io/badge/status-early-orange.svg)

**Turn one coding-agent session into a team lead.** The lead plans the work,
sends each task to a Sub-Agent in its own pane, watches for results, checks
them, and reports back to you.

It is an agent skill for [Herdr](https://herdr.dev), a terminal multiplexer
for coding agents. It works with Claude Code and Codex CLI panes.

```text
+---------------------------+-----------------------------------+
| login-lead-opus           | login-implementor-sol             |
| role: Lead (this session) | role: implementor                 |
|                           | state: working                    |
| - wrote the assignment    |                                   |
| - waiting for report.md   +-----------------------------------+
|                           | login-tester-luna                 |
| state: waiting            | role: tester                      |
|                           | state: idle                       |
+---------------------------+-----------------------------------+
```

## Features

- **Team in plain words.** Say "Use Herdr to complete this task: ..." and
  the skill builds the team. It uses one Sub-Agent when one is enough.
- **Choose models and effort per role.** Each Sub-Agent gets its own model
  and effort. Your explicit choice overrides the defaults.
- **Team templates and a Role Tree.** Start from a template such as
  `develop`. The skill draws the team as a text tree and a pane layout.
- **Launch checks.** After each start, the Lead reads the pane header and
  checks the name, model, and effort. A wrong value stops the work.
- **Written Assignments and reports.** Every task has a file with one
  outcome, allowed paths, and checks. Every result comes back as a report
  with a frozen commit or artifact.
- **Background monitoring.** A watcher script wakes the Lead only when a
  decision is needed, so the Lead does not poll the screen.
- **No two writers in one checkout.** Each writer has its own checkout, or
  the team runs in shared mode with a single source-code writer.
- **Nothing goes into git without you.** The Lead shows the files to commit
  and waits for your answer. Push, merge, and branch changes always need you.
- **Recover and change a live team.** Status, Resume, Adjust, Rotate, and
  Disband cover the rest of the team's life.

## Requirements

- [Herdr](https://herdr.dev) and its CLI, with `HERDR_ENV=1` set in the
  session. The skill stops if it does not run inside Herdr.
- The agent CLIs you plan to use, for example Claude Code or Codex.
- Python 3 with PyYAML, to draw the Role Tree and to run the package checks.

## Installation

Clone the repository, then copy it to the skills directory your agent reads.

```bash
git clone https://github.com/allenhu12/herdr-agent-team.git herdr-agent-team
mkdir -p ~/.claude/skills
cp -r herdr-agent-team ~/.claude/skills/herdr-agent-team
```

Claude Code reads `~/.claude/skills`. Codex CLI reads `~/.codex/skills`. Use
the folder that matches your agent. You can also use a skill installer such
as `npx openskills install https://github.com/allenhu12/herdr-agent-team.git --global`.

## Quick start

1. Start your agent inside a Herdr pane.
2. Ask for a team in plain words:

   > Use Herdr to complete this task: improve the internal parser and its tests.
   > Use Codex with my deepseek-v4-flash profile.

   Or ask for a team by type:

   > Use the herdr agent team skill to create a develop team called login.

3. Answer the one question the skill asks, then give the Lead your task.

Frontend work goes to Opus by default. Backend, architecture, debugging, and
testing go to Codex by default.

## What you can ask for

| Workflow | What it does |
|---|---|
| **Assemble** | Start a team of Sub-Agents, each in its own pane, with a chosen model and effort. |
| **Dispatch** | Write an Assignment, send it to a Sub-Agent, and monitor it in the background. |
| **Acceptance** | Read the reports, verify the frozen results, and integrate accepted commits. |
| **Status** and **Resume** | Check the team state and recover after a restart. |
| **Adjust** | Add or remove a role, or change a role's model or effort. |
| **Rotate** | Replace one role's session while its Assignment keeps running. |
| **Disband** | Close the panes after you confirm. |

Each team keeps its state in a `.herdr-agent-team/` folder at the project
root.

## Documentation

- [User guide](user-guide.md): the full manual, with a worked example and a
  diagram of a develop team at work.
- [Team Templates Guide](team-templates-guide.md): templates, the Role Tree,
  the Launcher, and Adjust, from the first request to Disband.
- [`SKILL.md`](SKILL.md): the entry point the agent loads.

## Repository layout

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

## Status and roadmap

This skill is early work. The Rotate workflow and the handoff templates
have static checks only. Their live runtime cases (V4-01 to V4-07) have not
run. Check `reports/v4-session-handoff-rotate-results.md` before you rely on
Rotate.

The current version is in SKILL.md (`metadata.version`). Changes per
version are in [CHANGELOG.md](CHANGELOG.md). Run
`python3 assets/skill-version.py` to see the version you have installed.

Ideas for later versions are in [TODO.md](TODO.md).

## Contributing

Bug reports and ideas are welcome. Open an issue and describe what you ran,
what you expected, and what happened. Run `python3 evals/check_package.py`
before you send a change.

## License

MIT. See [LICENSE](LICENSE).

Author: HBO (hubo12@gmail.com)
