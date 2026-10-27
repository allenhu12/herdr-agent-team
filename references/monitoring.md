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

## Team monitor (`monitor: team`)

team.yaml's top-level `monitor` field picks how the Lead learns about
work: `watcher` (the default, everything from "Background-wait mechanism"
on) or `team`. A `team` team runs one `assets/team-monitor.py run` per
team in its own Herdr tab instead of one watcher per Assignment. It needs
no host background-task facility and no agent-specific hook, so a Claude
Code, Codex CLI, or cursor-agent Lead works the same way.

**What it is.** A plain script, not an agent; it costs no tokens. It is
not a child of the Lead's process, so it keeps running while the Lead
restarts. `team-monitor.py start` creates the tab and runs it; a lock
keeps one monitor per team; `heartbeat.json` shows it is alive.

**What it watches**, every loop (read-only on the team files, one `herdr
agent list`): for each dispatched Assignment at its current attempt the
same outcomes as the watcher — `report`, `handoff` (a new handoff.md hash
or `HANDOFF READY` marker count compared with the latest dispatch
baseline, so successive Rotates in one attempt each wake once),
`stalled` / `prompt_uncertain` (from the dispatch record), `blocked` held
20s, `unknown` held 60s, `gone`, `no_report`, `inbox_unacked`, `timeout`
(`deadline_s`, default 2700) — plus `role_gone` for an idle role that
vanished, `identity_fault`, `nudge_uncertain`, and `monitor_error`.
It treats an idle role as having finished a turn only when the latest
dispatch record for that attempt is `landed` and it saw the role working
after that, or the landed record has settled for 30s (work seen before the
prompt landed never counts);
then it sends the one report nudge by the role's `steering` (an inbox
nudge carries the key `<id>:<attempt>:nudge`). It rings every inbox role,
with or without an Assignment, so `inbox.py wait-ack` is not used.

**What it never does.** It never accepts work, answers a question,
changes an Assignment, writes team.yaml, team-state.yaml or
assignment.md, or kills anything. The only completion signal is still
the current attempt's `report.md`; a wake only says "go check".

**Identity before every prompt.** Before each nudge, inbox ring, or Lead
doorbell it compares the target's live pane, kind, cwd, and process
identity with the recorded ones. A mismatch queues one `identity_fault`
and the target is quarantined (no more prompts). The quarantine lifts only
when the recorded identity or its verification time changes — Resume
re-verified the agent and updated team-state, including
`launch_verification.verified_at` (a role) or `identity_verified_at` (the
Lead), even for the same process — and the live agent matches the record.

**The wake queue.** Each event is one `<team_dir>/wake-queue/NNNNNN.wake`
file, published by rename; the files are the truth, and
`monitor/seen.json` is only a cache rebuilt at startup. A typed nudge
interrupted mid-send is never resent: its recorded intent stays the
authority and the Lead gets `nudge_uncertain`.

**Locks.** `team-monitor.py hold`, `unhold`, `dispatch-prompt`, and every
monitor prompt about an Assignment share `monitor/.prompt.lock` and
recheck the Assignment (still dispatched, same attempt and assignee, no
hold) under it. `start` serializes on `monitor/.start.lock` and binds the
new monitor's pane in `monitor/binding.json` by a launch token; `stop`
interrupts only that bound pane.

**The Lead doorbell.** When unacknowledged wakes exist and the Lead has
been idle for 30s (`HAT_LEAD_IDLE_HOLD_S`), the monitor types one fixed
line into the Lead's pane: `WAKE: run python3 <skill>/assets/team-monitor.py
drain --team-dir <team_dir>`. It does not ring a working or blocked Lead,
and it only re-rings after 120s or when a newer wake arrives (backing off
after three rings). With no Lead pane it only queues.

**Handling a wake (Lead).** On the doorbell or any User message:

1. `team-monitor.py drain` — a read-only snapshot of every unacknowledged
   wake, plus `WAKE_ACK_REQUIRED=<seq>`. If it says the monitor is not
   healthy, run `team-monitor.py start`.
2. Reconcile the User first: apply the arriving User message and
   `pending_user` through dispatch.md 5b and 5c before acting on any wake.
3. Handle wakes in sequence with the outcome table and exception routing
   below. A wake whose Assignment is no longer dispatched, or whose attempt
   differs, is stale: skip it. A report that an open question blocks is
   recorded as `deferred` (5c). Every branch must be safe to repeat.
4. `team-monitor.py ack --handled <seqs>` (or `--through <seq>`): it
   acknowledges only the contiguous prefix of wakes that are handled,
   deferred, or stale. A wake whose handling was interrupted stays
   unacknowledged and is shown again.

**Dispatch prompts.** In team mode the Lead sends dispatch, rework,
Resume, and Rotate prompts with `team-monitor.py dispatch-prompt`. It
waits only for the first lifecycle change
(`--until working --until blocked`, 15s). It reserves the dispatch record as `sending` first, then
records `landed`, `landed_blocked`, `rejected_blocked` (nothing sent),
`stalled`, or `uncertain` with the handoff baseline; a `sending` record
left for 60s becomes `prompt_uncertain`. After `sending` or `uncertain`,
`agent read` first; pass `--resend-after-check` only if the prompt did not
land. It refuses an Assignment that is not dispatched or is on hold.

**Cancel / redirect in team mode.** Run `team-monitor.py hold
--assignment <id> --attempt <n> --reason <text>` first; when it returns,
no monitor prompt for that Assignment can start and none is in flight.
Then interrupt and prove the stop exactly as in the handshake below. Only
then write the new state (cancelled, or the next attempt), revoke the
lease, `inbox.py retire`, and `team-monitor.py unhold`. Until then the Assignment's state, attempt, and lease stay as
they were, so the precheck still refuses an overlapping dispatch.

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
| `inbox_unacked` | inbox role only: the nudge was rung `HAT_INBOX_RING_MAX` times and never moved to `handled/` | `agent read`, then the stuck branch |
| `superseded` | inbox role only: the nudge was refused or retired because this attempt is no longer current | nothing to accept; the Lead already moved on |
| `role_gone` | team monitor: an idle role vanished | Resume's gone branch for that role |
| `identity_fault` | team monitor: a prompt target's identity no longer matches | Resume's quarantine branch; no prompt until re-verified |
| `prompt_uncertain` / `nudge_uncertain` | team monitor: delivery of a dispatch prompt or typed nudge is unknown | `agent read`; resend only if it did not land |
| `monitor_error` | team monitor: it could not read the team files | fix the file; the monitor keeps running |

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

## Steering: how mid-task messages reach a role

A role's `steering` field in team.yaml (default `prompt`) decides how the
Lead sends it a mid-task message: the watcher's report nudge, "Write your
handoff now, then stop.", "Tester window open/closed", or an answer to a
question the role asked in text while idle.

- **`prompt`**: type the message with `herdr agent prompt`, as before.
- **`inbox`**: write it with `assets/inbox.py send` into
  `<team_dir>/inbox/<role>/NNNN.msg`; the role's pane receives only a
  fixed doorbell line naming that folder. The role reads each message in
  number order, acts on it, and moves it into `handled/`; that move is the
  acknowledgement. After every `send`, run `inbox.py wait-ack --role <role>`
  through the host background facility and register it in `monitors` with
  `kind: inbox` and the role as `assignee` (one per role is enough). It
  rings an idle role again after a grace period and exits once:
  `inbox_acked`, `inbox_unacked` (agent read, then the stuck branch),
  `gone` (Resume's gone branch), or `timeout`.

`send` and every later ring re-read team-state.yaml. A message naming an
Assignment is valid only while that Assignment is dispatched at the same
attempt; a tester-window `open` message only while that tester Assignment
is dispatched. `send` refuses a stale message, and a ring moves one to
`retired/` with a reason instead of ringing. On every state transition
that makes messages stale (rework, cancel, redirect, tester window
closing, Rotate) the order is: stop the watcher, write the new state,
then `inbox.py retire` the role's matching messages. At every wake-up,
run `inbox.py status` before anything else, so a message still pending
after its watcher exited stays visible.

Messages never replace these: dispatch, rework, Resume, and Rotate
prompts ("Read assignment.md ..."), which go through the watcher; `esc` /
`ctrl+c` interrupts; key presses that answer a CLI permission prompt; and
the opening identity instruction. Peer messages between Sub-Agents keep
writer-rules.md's rules. Only the Lead writes a role's inbox folder.

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
  - An open `pending_user` entry blocks this Assignment → hold the report
    (dispatch.md, "5c. Waiting on the User"); do not accept yet.
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
- **`inbox_unacked`** — the role never moved the nudge to `handled/`.
  `agent read` to see why (doorbell lost, protocol not understood, context
  trouble), then follow the stuck branch. Do not resend the same message.
- **`superseded`** — the nudge belonged to an attempt that is no longer
  current. Do not accept or rework from this wake-up.
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
   Write the new state, then for an inbox role run `inbox.py retire
   --role <role> --assignment <id> --before-attempt <new attempt>` (or
   `--all` for a cancellation) so no queued message from the stopped
   attempt is acted on later.
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
