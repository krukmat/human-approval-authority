# Workflow authority — extraction baseline and design (2026-11-27)

Status: **candidate only; activation NO_GO**. This is a new, owner-approved development workstream, not a reopening of HAA W0–W9 certification or DubBridge-specific deployment.

## W1 freeze and provenance

- DubBridge: `bdae32e1e9167a18b12b8911df71d5982d25998c`, branch `feature/haa-hitl-w3-request-verify`. Preserve the source branch and audit artifacts unchanged. No further DubBridge-specific feature development or activation in this workstream.
- HAA main starting point: `29326c4a2c9057abd76c0ff7467edafc556c1ee9`.
- Existing HAA profile prototype: `11ad3962b857dcf9d17bab63ad45df25f576a7c4` (`feature/dubbridge-action-profiles`), not main.
- Inventory: `source-inventory.json` records each exact source blob. Previous physical HAA smoke is historical evidence only. Protected host/supervisor composition and remote enforcement are not certified by that evidence.
- ADR-049 rejects same-UID sealed ACTIVE lease restoration: retain volatile authority and protected transactional terminal records. Preserve the owner decision suspending RRI recomputation for the old integration; do not extend it to other workflows.

## W2 architecture decision

Use this existing HAA repository as the **source-code distribution location** for a standalone Python companion at `integrations/workflow-runtime/`, not as an import dependency of HAA core/server or any product. No new repository, model, reviewer, CI pipeline, or orchestrator. Agnostic AI Pipeline is a different orchestration system and is not required by the existing Fénix/DubBridge guides. The companion may be distributed independently of the HAA service; only documented HTTP/key metadata cross the authority boundary. HAA v1 remains frozen. New generic action profiles, if registered, are additive, typed/versioned and tested separately. Do not silently repurpose the old profiles.

| Owner | Contract |
|---|---|
| Repository workflow policy | Decide HITL, RRI, delegation, reviews, QA, exceptions, and allowed operation |
| Trusted policy adapter | Resolve policy/version and pin the exact task card, approval decision and scope from protected inputs; never take these from worker claims |
| HAA | Human verification and exact-action atomic consume; receipt is evidence only |
| Protected runtime | Reconstruct live state, verify grant, activate one volatile lease, serialize mediated operation, revoke on completion/drift/restart |
| Worker | Untrusted typed proposals in scratch; no grant, owner control, secrets, or protected write access |
| Git/host adapter | Protected target and OS isolation; remote writes require separately protected credentials and branch controls |
| Evidence | Protected terminal records; no bearer authority; VEL optional, outside critical path |

### Authorization contract

Generic profile names proposed: `workflow.task.start.v1` and `workflow.plan.close.v1` (the latter only where existing policy requires a closure ceremony). Exact payload preserves old task envelope: repository, planId, taskId, sessionId, branch, baseCommitSha, allowedPaths, scopeDigest, capabilities, leaseTtlSeconds. Bind card digest and policy decision/version to the session; trusted preconditions re-read independently before consume and after verification under exclusive target control. Task lease capabilities: edit/test/review/commit only when independently allowed by the governing policy. Existing task-start lease cannot authorize merge, push, deploy, secrets, deletion or a plan close; unknown or unsupported operation blocks. Git merge uses existing exact profile if implemented; no generic privileged shell profile. Scope must not expand; policy changes or expiration/revocation invalidate authority. No automatic HAA bypass on error. Existing low-risk read/analysis stays outside additional ceremonies. No mandatory new closing prompt for ordinary plans absent policy decision.

Policy decision is separate from RRI; no global threshold hardcoded into new generic boundary. Existing project-specific rules remain authoritative (including independent peer review and QA). Owner approval of this workstream is not a signed HAA grant. A waiver cannot be fabricated from a model verdict or file. Runtime is not to change real policies or credentials until W6 and explicit activation decision.

### Threat model

Untrusted worker, task cards from repository, stale/replayed requests, symlinks/hardlinks, hostile Git configuration/hooks, rollback of agent-writable bytes, role confusion, replaced verifier and ambiguous consume/crash. Protected non-root service and credentials, trusted interpreter and dependencies, distinct worker UID, protected target/store, typed IPC with kernel peer identity, monotonic lease expiry, generation reset and durable transaction records. Tests run only as unprivileged worker against exact tree. Administrator intentionally elevating, kernel compromise, privileged snapshot rollback and unmediated cloud/GitHub credentials are outside certified scope. Do not claim arbitrary agent shell containment. Verify host constraints on macOS, not from portable tests.

## W3 migration sequence and acceptance

Copy the portable client/contracts/verification/checkpoint/lease code with source pins; isolate legacy sealed LeaseStore from the production path (VolatileLeaseStore required). Extract protected commit/broker/session/supervisor without widening the one-existing-file prototype. Remove product-specific profile IDs, task-card parser path, session prefix, fixture repository defaults, and hardcoded policy gates deliberately rather than blind rename. Replace repository parser/policy with explicit trusted adapters. Preserve tests and run them against candidate; add profile cross-language parity, live state, role, replay, recovery and negative cases. Host packaging and credentials must remain disabled and synthetic-only before certification. W4 requires actual adapters for Fénix and DubBridge and route parity; W5 requires executable tests/benchmark and W6 a real protected host + Touch ID gate. No production claim from a source extraction.
