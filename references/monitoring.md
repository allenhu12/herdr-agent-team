# Monitoring

## State is a wake-up signal, not proof of completion

Herdr's agent states — `working` / `idle` / `done` / `blocked` / `unknown` —
describe lifecycle, not a specific turn. Two traps to avoid:

- `done` is really just "`idle`, and nobody's looked yet." The moment a
  client focuses the tab, it reverts to plain `idle`. It says nothing about
  whether *this* Assignment is finished.
- `agent wait` tracks the lifecycle state, not an individual round of work.
  If the Sub-Agent was already working when you started waiting, the wait
  can resolve when its *current* turn ends — which may or may not be the
  turn that finished your Assignment.

So: **Herdr state only ever means "go check now."** The one real completion
signal is a `report.md` on disk in the Assignment's workspace dir, belonging
to the current `attempt`. Every acceptance decision starts there, never from
`agent get` alone. A `handoff` outcome signals rotation, not completion.

## Background-wait mechanism

Always run through the host's own background-task facility (in Claude Code:
a background Bash task) rather than a raw shell `&` — a shell `&` backgrounds
the process from the shell's point of view but does not register it with the
host's notification mechanism, so the Lead Agent would never be told it
finished. Capture the **host facility's** task handle/ID (not a shell PID)
and register it in `team-state.yaml`'s `monitors` list along with the
Assignment id, `attempt`, and assignee. On wake-up, check that registration
first — confirm you're reacting to the monitor for the assignment you think
you are, so a stale monitor from a superseded attempt can't trigger
acceptance of the wrong work.

### Why a bare `agent wait` costs too much

A bare backgrounded `herdr agent wait` settles on every `blocked` state, not
just a genuinely finished Assignment — and a routine in-scope permission
prompt inside the Sub-Agent (approve this edit, approve this rename) is
`blocked` too. Evidence from the smoke tests: a one-line file edit produced
four Lead wake-ups, three of them permission prompts already inside the
Assignment's granted scope. Each wake-up cost a full `agent read` of a TUI
screen (the single largest token cost in the whole cycle) plus a decision,
an answer, a re-armed wait, and a `team-state.yaml` rewrite — for
information the Lead didn't actually need.

Herdr itself has no push/event/file-wait primitive to fix this from the
outside (checked `herdr api schema`, `herdr notification`; neither exposes
one). The fix is a small watcher that filters *before* the Lead is woken,
not a change to Herdr.

### Run the watcher, not a bare wait

Background `skill/assets/watch-assignment.sh <role> <workspace-dir>
<attempt> <deadline-s> [prompt]` through the host facility instead of a raw
`agent prompt --wait` / `agent wait` call. It still uses those same Herdr
primitives internally — nothing about Herdr's contract changes — but it
loops inside the background process and only exits (one host notification)
on an outcome the Lead must actually act on:

| Outcome | Meaning | Lead's required action |
|---|---|---|
| `report` | `report.md` exists for the current `attempt` | acceptance protocol, **no** `agent read` |
| `handoff` | current-attempt `handoff.md` or attempt-tagged `HANDOFF READY` marker | validate handoff, then run Rotate |
| `blocked` | `blocked` continuously for >= 20s, no report | `agent read --source detection --lines 40`, blocked branch below |
| `unknown` | `unknown` continuously for >= 60s | `agent read`, escalate if still unclear |
| `gone` | the agent name no longer resolves | Resume's "gone" branch |
| `stalled` | the opening prompt returned `agent_prompt_stalled` | `agent read` to see why it didn't land |
| `no_report` | idle/done seen twice; the script already sent one automatic nudge ("write report.md") and it still didn't appear | treat as stuck, `agent read` |
| `timeout` | the hard deadline passed with no other outcome | extend, nudge, or escalate, same as before |

The script swallows `working`, a *first* idle/done without a report (it
sends the one nudge itself and keeps waiting), and short `blocked`/`unknown`
blips under their hold times — these never reach the Lead. This is strictly
a pre-filter: **the only completion signal remains `report.md` matching the
current `attempt`**, checked by the script the same way the Lead would
check it, never by the script's own judgment about what the Sub-Agent said.

Default hard deadline is 45 minutes (2700s) unless the Assignment calls for
something shorter or longer — short deadlines used only to test timeout
handling itself produce a wake-up carrying no information and should be
avoided in normal dispatch.

Two call shapes, matching the two cases that used to need separate
primitives:

- **At dispatch** (see `dispatch.md`) or a **rework continuation**, pass the
  prompt text as the fifth argument — the script sends it via
  `agent prompt --wait` as its first move, so a stale pre-existing idle
  state still can't be mistaken for the prompt having already been acted on
  (same reasoning as before: an observed lifecycle change is required
  within 5 seconds or Herdr returns `agent_prompt_stalled`, which the
  script surfaces as its own `stalled` outcome).
- **At resume**, for a role already mid-Assignment with nothing new to say,
  omit the prompt argument — the script starts straight into its polling
  loop with a bare `agent wait` internally.

Background monitors don't survive a Lead Agent restart — that's expected.
`resume.md` re-arms one watcher per active Assignment as part of
reattaching, and always **replaces** `team-state.yaml`'s `monitors` list
rather than appending to it — every previously recorded handle belonged to
a process that's gone, and leaving stale entries in place risks a dead
handle being mistaken for a live one later.

Use a foreground call to the script only for a simple, single-Sub-Agent
case where there's nothing else to do meanwhile — it still exits on the
same outcome table, just without a host background handle to register.

## Result handoff: report files, not screen scraping

A Sub-Agent finishing an Assignment writes `report.md` into its own
workspace dir (temp file, then atomic rename — see `state-files.md`),
using assets/report.md.template: id/attempt/status metadata and the six
compact result/artifact/files/tests/screenshots/issues sections. Use the
recorded absolute report_path in the canonical Workspace Dir, regardless
of the writer's cwd. The Lead Agent reads that file. It does not scrape the
pane's terminal output for results.

Why: agents commonly run in the terminal's alternate screen, and content
that scrolls off the alternate screen never reaches Herdr's host scrollback —
`agent read --lines N` cannot recover it no matter how large `N` is. Reading
a file is also strictly cheaper in tokens than reconstructing a transcript.

## Exception routing

On wake-up, read the watcher's one JSON line first, then branch on its
`outcome` — never accept the outcome alone as the answer for anything but
`report`, which is itself only a signal to go check the file, not proof:

- **`report`** — check `report.md` matches the current `attempt` (the
  script already checked this before exiting, but re-verify against the
  recorded `report_path` before acting on it).
  - Confirmed → run acceptance (criteria in `dispatch.md`): pass → mark
    `succeeded`, summarize to the User; fail → append the gap to
    `assignment.md`, bump `attempt`, re-dispatch (cap `max_attempts: 3`,
    escalate to the User once exhausted).
- **`handoff`** — confirm the handoff names the current attempt and has all
seven sections. Confirm the role is idle and checkpointed, then run Rotate.
  Do not accept the Assignment or mark it complete.
- **`no_report`** — treat as stuck, not done, even though the underlying
  Herdr state is idle/done. The script already sent one nudge and it
  produced no report. `agent read` to see what's actually on screen before
  deciding next steps.
- **`blocked`** — `agent read --source detection --lines 40` to see what the
  Sub-Agent is asking (widen to `recent-unwrapped --lines 120` only if that
  's still unclear).
  - Answer directly only if the question falls inside what `assignment.md`
    already pre-authorized *and* has no external side effect.
  - Escalate to the User for anything touching tool/permission grants,
    deletions, publishing externally, credentials, or spend — no exceptions,
    matching the `herdr` skill's own safety posture.
  - After answering, re-arm the watcher (no prompt argument — same
    already-working case as Resume) before continuing.
- **`stalled`** — `agent read` to see why the opening prompt didn't land;
  do not treat it as a normal timeout.
- **`timeout`** — `agent read` to see where it's stuck, then pick one:
  extend the deadline and re-arm, send a nudge prompt and re-arm with a
  prompt, or escalate to the User.
- **`unknown`** — never treat as completion. Read the pane, and escalate to
  the User if it still can't be classified after that.
- **`gone`** — route through Resume's "gone" branch (rebuild the role); do
  not treat a vanished agent as any form of completion.

## Late signals for other Assignments

A wake-up, report, log entry, or message can also bear on an Assignment
that is already running, for example a new commit after the tester was
dispatched. Judge it with dispatch.md, "Late signals": a version or status
signal is compared mechanically with that Assignment's Inputs; a message
with new content gets a Lead decision against its Outcome, Write Scope, and
Acceptance Criteria. A change runs the handshake below.

## Cancel / redirect / re-dispatch handshake

Changing an Assignment mid-flight — cancelling, redirecting scope, or
re-dispatching after a failure — must follow this order, every time:

1. **Stop the background monitor** for that Assignment (kill the tracked
   host background task).
2. **Interrupt the Sub-Agent's current turn** (`herdr agent send-keys <role>
   esc`, or `ctrl+c`), and wait until it reaches a settled state.
   `esc`/`ctrl+c` interrupt the Sub-Agent's *foreground* turn, but do not
   reliably kill a shell process the Sub-Agent has already pushed into the
   background (e.g. a `sleep`/loop command run with its own background-task
   facility) — that process can keep mutating granted files after the
   keypress with no visible sign in `agent get`. If the granted file(s) are
   still changing a few seconds after `esc`/`ctrl+c`, treat the keypress as
   insufficient and use one of these fallbacks instead of re-sending it:
   - Send a new prompt explicitly asking the Sub-Agent to kill its own
     background process. A `kill`/process-termination command always
     requires an explicit User decision before it runs — same as any other
     permission grant, no exception for this being "your own process."
     Before asking the User, read the **full** pending command yourself and
     confirm it targets only a specific, verified PID or job ID that this
     Assignment's own background task actually produced (e.g. one it
     printed earlier, or one confirmed via a process listing) — a command
     line or process name is only acceptable for *finding* that PID, never
     as the kill target itself. Never let a broad or pattern-based kill
     (e.g. `pkill -f <generic-name>`) reach the User as if it were
     precisely scoped — if the Sub-Agent proposes one, ask it to identify
     the exact PID first instead of forwarding the pattern for approval.
   - If no such precisely-targeted kill is available or safe, fall back to
     simply **waiting for the background task to finish on its own** before
     proceeding — slower, but still a valid way to reach a settled,
     non-mutating state.
3. **Confirm it actually stopped.** For work that mutates a granted file,
   the real check is that the file stops changing (re-check after a few
   seconds; don't rely on `agent get` settling alone, since Herdr's state
   can settle while a background process keeps running). For background
   work that does **not** write to a file Herdr can observe, file stability
   isn't a signal at all — confirm the process itself is actually gone
   (e.g. ask the Sub-Agent to check and report, or use whatever
   process-listing capability is available) before treating it as stopped.
   Once confirmed, revoke its write-scope grant and remove its monitor.
   For cancellation, mark the Assignment `cancelled` with finished_at in
   `team-state.yaml`. For acceptance rework, record the stopped attempt;
   Dispatch transitions the same Assignment to pending with an incremented
   attempt. Do not reset its retry history.
4. **Only then**, if a replacement is needed, dispatch it as a fresh
   Assignment following the full `dispatch.md` flow.

Acceptance rework is not a replacement: retain the same Assignment ID and
increment attempt, keeping max_attempts: 3. Complete the stop/proof steps
before renewing that lease; preserve prior attempt artifacts. Never use a
fresh ID solely to reset exhausted retries.

Stopping only the monitor without interrupting the agent is a bug in
practice: the Sub-Agent keeps editing files under a grant you meant to
revoke. Steps 1–3 are not optional shortcuts, but step 2's exact mechanism
(keypress vs. kill-prompt vs. wait-it-out) is chosen based on what actually
stops the file changes, not fixed to a single method.
