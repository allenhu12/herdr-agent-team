# V4 session handoff and Rotate results

Date: 2026-09-23

## Local verification

- `python3 skill/evals/check_package.py`: PASS, 47/47 static package checks.
- `bash -n skill/assets/watch-assignment.sh`: PASS.
- `git diff --check`: PASS.
- A temporary mock-Herdr harness with a current-attempt `HANDOFF READY`
  marker emitted one JSON line with `outcome: handoff` and `state: idle`.
  This checks the watcher branch only; it is not live Herdr evidence.
- Follow-up: direct execution, `bash`, and `sh` all emitted the same outcome.
  The reported `has_handoff: command not found` error did not reproduce.
  `new_handoff` now performs the current-attempt checks inline, so it no
  longer depends on resolving `has_handoff` as a shell function.

## Live runtime cases

| ID | Result | Evidence / limit |
|---|---|---|
| V4-01 | INSUFFICIENT_EVIDENCE | Not run in a disposable live team. |
| V4-02 | INSUFFICIENT_EVIDENCE | Not run in a disposable live team. |
| V4-03 | INSUFFICIENT_EVIDENCE | Not run in a disposable live team. |
| V4-04 | INSUFFICIENT_EVIDENCE | Not run in a disposable live team. |
| V4-05 | INSUFFICIENT_EVIDENCE | Not run in a disposable live team. |
| V4-06 | INSUFFICIENT_EVIDENCE | No task-relay fixture was prepared. |
| V4-07 | INSUFFICIENT_EVIDENCE | Mock watcher check passed; live Herdr watcher case remains unrun. |

The Herdr CLI and `HERDR_ENV=1` are available, but this change did not create
or launch a disposable team. No agent panes or runtime resources were
started. The live cases need a frozen skill package and a fresh disposable
project as specified in `evals/runtime-cases.md`.

The 25% Sub-Agent and 30% Lead context thresholds remain starting values.
The old pane stays open read-only until the replacement's first action is
confirmed.
