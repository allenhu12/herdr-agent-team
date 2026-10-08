# Runtime results: team templates, Role Tree, Launcher

Date: 2026-09-11. Branch: `feature/agent-role-tree`.
Environment: Herdr 0.9.0, codex-cli 0.154.0, Claude Code 2.1.268.
Run by the Claude Code session in pane w7:p1, on throwaway git repos in
that session's scratch folder. The User confirmed the V2-22 layout on
screen.

| ID | Result | Evidence |
|---|---|---|
| V2-22 | PASS | Lead w7:p1 (this session, Opus 5 observed, effort unknown). Sub-Agents w7:p3 developer `gpt-5.6-sol medium`, w7:p4 tester `gpt-5.6-luna xhigh`, w7:p5 writer `Opus 5 with medium effort`, stacked right of the Lead. All replied READY to the opening prompt. role-tree.md rendered with the observed Lead, not the template suggestion. Disbanded after User confirmation; Lead retained. |
| V2-23 | PASS with finding | Launcher w7:p1 spawned Lead w7:p6 `gpt-6-astra medium`, then Sub-Agents w7:p7, w7:p8, w7:p9 right of it. Team files unchanged by the Launcher after handoff_at 04:21:19Z (hashes kept). The Lead wrote team-state.yaml at 04:24:28Z with its own session id. Assignments and monitors empty. Sub-Agent state_change_seq unchanged (140/142/144): no continuation prompts. |

Not run: V2-24 to V2-32.

## Findings

1. **Permission flags overrode the User's CLI config (fixed).** The skill
   passed `-s workspace-write -a on-request` to every Codex agent. Flags
   beat config, so the User's `approval_policy = "never"` and
   `sandbox_mode = "danger-full-access"` were replaced. The sandbox
   blocked the Herdr socket, and the spawned Lead needed approval for
   every `herdr` command. Fix: team.yaml `permissions: inherit` (default)
   passes no permission flags; `scoped` keeps the old flags.
2. **First-launch trust prompts (open).** Codex and Claude Code each ask
   "Do you trust this folder?" the first time they open a new repo. Codex
   trusts the repo root once, so later worktrees did not ask. Claude Code
   starts with the cursor on "No, exit", and Herdr reports the agent as
   blocked during startup. Codex `-c projects."<path>".trust_level=
   "trusted"` did not suppress the prompt. The skill needs a documented
   step: show the prompt to the User, or accept it only for a repo the
   skill created.
3. **Uneven pane heights (open).** Each down split halves the pane above,
   so three Sub-Agents get 1/2, 1/4, 1/4 of the column. The skill should
   even out heights after splitting.
4. **Late Codex session ids (open).** Codex shows no agent_session id until
   its first prompt. Record process_identity after the opening prompt.
5. **Extra control file (open, minor).** The spawned Lead wrote
   `resume-verification.json` into team_dir. The layout in
   state-files.md does not list it. Either allow a named evidence file or
   tell the Lead to keep evidence outside team_dir.

## Cleanup

- V2-22: Sub-Agent panes w7:p3, w7:p4, w7:p5 closed after User
  confirmation; archive written by the Lead (this session).
- V2-23: Sub-Agent panes w7:p7, w7:p8, w7:p9 closed after User
  confirmation, after re-validating name, pane, kind, cwd, and session id.
  The Launcher wrote no team file after handoff, so the v23 archive
  record is not in team-state.yaml. Lead pane w7:p6 retained under the
  Disband rule.
- Throwaway repos and worktrees remain in the session scratch folder.
