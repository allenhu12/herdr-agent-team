#!/usr/bin/env bash
# watch-assignment.sh — background watcher for one Assignment.
#
# Runs through the host's own background-task facility (never a raw shell
# `&`). Exits exactly once, on an actionable outcome, printing one JSON
# line to stdout. The Lead Agent reads that line on wake-up instead of
# scraping the Sub-Agent's terminal. See monitoring.md "Background-wait
# mechanism" for the outcome table and the rationale.
#
# Usage:
#   watch-assignment.sh <role> <workspace-dir> <attempt> <deadline-s> [prompt-text]
#
# <role>          Herdr agent name (unique live agent, per identity-and-launch.md)
# <workspace-dir> Absolute Assignment Workspace Dir (holds assignment.md/log.md/report.md)
# <attempt>       Current attempt number (must match report.md's Attempt: line)
# <deadline-s>    Hard timeout in seconds (default 45 min = 2700 if omitted)
# <prompt-text>   Optional. If given, sent via `agent prompt --wait` as the
#                 opening move (fresh dispatch or a rework continuation).
#                 Omit for a bare re-arm on an already-working role (Resume).
#
# Outcomes (see monitoring.md for the Lead's required action on each):
#   report     report.md exists for <attempt>              -> acceptance, no agent read
#   handoff    current-attempt handoff.md/log marker         -> Lead runs Rotate
#   blocked    blocked continuously for >= BLOCKED_HOLD_S   -> agent read (detection, small), blocked branch
#   unknown    unknown continuously for >= UNKNOWN_HOLD_S   -> agent read, escalate if still unclear
#   gone       agent name no longer resolves                -> Resume "gone" branch
#   stalled    agent_prompt_stalled on the opening prompt    -> agent read, see why prompt didn't land
#   no_report  idle/done twice, one nudge sent, still no report -> stuck branch
#   timeout    hard deadline reached with no other outcome   -> extend/nudge/escalate
#
# Never treats a state alone as completion. The only completion signal is
# report.md matching the current attempt (monitoring.md's "state is a
# wake-up signal, not proof").

set -u

role=${1:?role required}
ws=${2:?workspace-dir required}
attempt=${3:?attempt required}
deadline=${4:-2700}
prompt=${5:-}

BLOCKED_HOLD_S=20
UNKNOWN_HOLD_S=60
POLL_S=5

start=$(date +%s)
nudged=0
blocked_since=0
unknown_since=0
initial_handoff_hash=""
if [ -f "$ws/handoff.md" ]; then
  initial_handoff_hash=$(shasum "$ws/handoff.md" 2>/dev/null | awk '{print $1}')
fi
initial_handoff_markers=0
if [ -f "$ws/log.md" ]; then
  initial_handoff_markers=$(grep -cF "HANDOFF READY attempt=$attempt" "$ws/log.md" 2>/dev/null || true)
fi

emit() {
  # emit <outcome> <state>
  now=$(date +%s)
  printf '{"assignment":"%s","attempt":%s,"outcome":"%s","state":"%s","elapsed_s":%s}\n' \
    "$(basename "$ws")" "$attempt" "$1" "$2" "$((now - start))"
  exit 0
}

has_report() {
  # Bold is optional: agents often drop it (runtime V3, finding 6).
  [ -f "$ws/report.md" ] && grep -qE "^(\*\*)?Attempt:(\*\*)? *${attempt}([^0-9]|$)" "$ws/report.md"
}

new_handoff() {
  handoff_found=0
  if [ -f "$ws/handoff.md" ] && grep -qE "^\\*\\*Attempt:\\*\\* *${attempt}([^0-9]|$)" "$ws/handoff.md"; then
    handoff_found=1
  elif [ -f "$ws/log.md" ] && grep -qE "HANDOFF READY.*attempt[ =:]?${attempt}([^0-9]|$)" "$ws/log.md"; then
    handoff_found=1
  fi
  [ "$handoff_found" -eq 1 ] || return 1
  # A Rotate continuation starts with the existing handoff in place. Do not
  # emit it again; wait for a new handoff written by the replacement session.
  [ -z "$prompt" ] && return 0
  current_hash=""
  [ -f "$ws/handoff.md" ] && current_hash=$(shasum "$ws/handoff.md" 2>/dev/null | awk '{print $1}')
  current_markers=0
  [ -f "$ws/log.md" ] && current_markers=$(grep -cF "HANDOFF READY attempt=$attempt" "$ws/log.md" 2>/dev/null || true)
  [ "$current_hash" != "$initial_handoff_hash" ] || [ "$current_markers" -gt "$initial_handoff_markers" ]
}

# Prints one of: idle working blocked done unknown gone
state() {
  out=$(herdr agent get "$role" 2>/dev/null) || { echo gone; return; }
  printf '%s' "$out" | python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
    print(d["result"]["agent"]["agent_status"])
except Exception:
    print("gone")
' 2>/dev/null || echo gone
}

# Opening move: send the prompt and wait for the first lifecycle change,
# combined in one call so a bare wait can never observe pre-existing idle
# state and report false completion (see monitoring.md, dispatch.md step 3).
if [ -n "$prompt" ]; then
  out=$(herdr agent prompt "$role" "$prompt" --wait --timeout 60000 2>&1)
  case "$out" in
    *agent_prompt_stalled*) emit stalled unknown ;;
  esac
fi

while :; do
  if [ -n "$prompt" ]; then
    new_handoff && emit handoff "$(state)"
  fi
  has_report && emit report "$(state)"
  if [ -z "$prompt" ]; then
    new_handoff && emit handoff "$(state)"
  fi

  s=$(state)
  now=$(date +%s)

  case "$s" in
    gone)
      emit gone gone
      ;;
    blocked)
      [ "$blocked_since" -eq 0 ] && blocked_since=$now
      unknown_since=0
      [ $((now - blocked_since)) -ge "$BLOCKED_HOLD_S" ] && emit blocked blocked
      ;;
    unknown)
      [ "$unknown_since" -eq 0 ] && unknown_since=$now
      blocked_since=0
      [ $((now - unknown_since)) -ge "$UNKNOWN_HOLD_S" ] && emit unknown unknown
      ;;
    idle|done)
      blocked_since=0
      unknown_since=0
      if [ "$nudged" -eq 0 ]; then
        nudged=1
        herdr agent prompt "$role" "Write '$ws/report.md' for attempt $attempt now, following the six-section template, then stop." \
          --wait --timeout 60000 >/dev/null 2>&1
      else
        has_report || emit no_report "$s"
      fi
      ;;
    working)
      blocked_since=0
      unknown_since=0
      ;;
  esac

  if [ $((now - start)) -ge "$deadline" ]; then
    emit timeout "$s"
  fi

  # This is the sleep: a short bounded wait, not a busy poll. A real
  # lifecycle change is seen within POLL_S seconds either way.
  herdr agent wait "$role" --timeout $((POLL_S * 1000)) >/dev/null 2>&1 || true
done
