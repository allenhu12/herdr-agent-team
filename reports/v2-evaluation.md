# V2 evaluation

Date: 2026-09-05. Source baseline: d52707d. Approved implementation is complete
in this repository; live acceptance remains unverified. No installation,
commit, push, pane creation, worktree creation, or provider-config edit was
performed. The evaluated operational/eval files are frozen by the hashes in
[v2-package.sha256](v2-package.sha256); reports are excluded to avoid a
self-referential manifest. Verify from the repository root with
`shasum -a 256 -c skill/reports/v2-package.sha256`.

## Implemented

- Visible Lead Agent name, agent/pane naming, separate lead state entry,
  lookup instructions, Status display, succession checks, and retained Lead
  during Disband. A label is not model/effort proof or messaging permission.
- Inventory/reuse and minimal-team defaults; Opus frontend, Codex backend/
  architecture/debug/testing, with explicit User choices taking precedence.
- Explicit model/profile/effort launch mappings, required DeepSeek -p profile,
  header verification before opening prompts, and evidence invalidation when
  process/session identity changes. Missing header fields block dispatch.
- Exclusive writer checkouts/indexes; logical file ownership and role/lease
  intersection preserved; absolute canonical control paths and non-git support.
- Expanded Assignment contract, six-section current-attempt reports, frozen
  artifacts, version-matched visual checks, different-model review, and final
  integration checks in one checkout.
- V1 readable-state migration; existing workflow boundaries and safeguards;
  guide, domain definitions, accepted ADR, and Yao package metadata.

## Checks actually run

| Check | Result |
|---|---|
| Yao validate_skill.py | PASS; previous missing interface metadata fixed |
| Yao resource_boundary_check.py, 1,000-token limit | PASS; 971 estimated initial-load tokens including interface, no warnings |
| evals/check_package.py | PASS: 16/16 static template, YAML, link, and interface checks |
| Yao trigger_eval.py with supplied cases/config | PASS: 19/19 configured phrase cases (9 positive, 5 negative, 5 neighbors) |
| git diff --check | PASS |
| Original smoke plan/results and ADR 0001 unchanged | PASS via git diff --exit-code |

Machine-readable results are in [v2-static-results.json](v2-static-results.json).
The Yao trigger tool is a phrase-scoring heuristic. Its generic explanation
mentions skill packaging concepts; this run instead uses the checked-in
Herdr operation/exclusion concepts. It is not an LLM routing test, blind
holdout, or proof that a live agent follows the instructions. The 16 contract
checks establish file/schema consistency, not operational safety by themselves.

## Review and revision

Reviewed the changed instructions against the approved requirement matrix
and original workflow invariants. Fixed two ambiguities: pending rework must
not reject itself as a busy Assignment, and the cancellation handshake must
preserve same-ID rework rather than mark every interrupted attempt cancelled.
Queued records without leases do not count as active work. Rework still
checks live busy state, releases old leases/monitors, preserves frozen prior
versions, and stops after attempt 3. Full-scope audits retain the original base.

The Lead's current running session is named without being relaunched. Strict
explicit launch flags apply to Sub-Agents this skill starts. Unknown Lead
model/effort is reported instead of inferred. Resume validates handoff before
changing the mapping; Status only reads it. No independent model review was
run during this skill-edit task.

## Runtime limitations

HERDR_ENV is unset in this session. Live tests in
[runtime-cases.md](../evals/runtime-cases.md) are BLOCKED_ENV, including the
21 new cases and historical ST-01–ST-10/ST-X1/ST-X2 regression coverage.
Historical v1 smoke results were not rerun and do not certify v2.

Installed CLI help previously confirmed Herdr 0.8.2 argument forwarding,
Codex 0.153.2 profile/model/config flags, and Claude Code 2.1.261 model/effort
flags. These are syntax observations, not provider/header launch success.
Actual header availability, profile/provider acceptance, pane naming, and
cross-checkout access must be exercised inside Herdr before calling runtime
integration verified. If the header cannot show model/effort, the implemented
rule stops and reports it; it does not add a synthetic proof label.

Remaining resources created by this work: none. The existing repository
checkout remains; no Herdr agents, panes, worktrees, monitors, or test servers
were started. Source changes are uncommitted for User review.
