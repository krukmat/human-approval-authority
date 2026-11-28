# HAA + Agent Workflow — minimal HITL checkpoint

**Active plan: simplified scope approved by owner.** The previous protected
runtime workstream is frozen at `ed7ecdd33bce8486a04146785d4ccea975342a2b`. Preserve the code, tests and
historical evidence, but do not provision macOS identities, protected targets,
leases, IPC, or verifiers for this plan. No additional repository, model,
reviewer, daemon, or CI pipeline. Production rollout remains NO_GO pending
functional acceptance.

## Active contract

The existing Workflow Guide owns RRI, HITL, model routing, readiness,
implementation, QA, independent review and closure. HAA is used only when
the existing policy requires a task-start HITL checkpoint **and** the owner has
selected HAA as its approval channel. Other existing approval checkpoints and
ordinary tasks retain their current behavior. No change to RRI thresholds,
autonomy, reviewer rules, plan closure or push/merge policy.

```text
existing Task Card + final prompt + existing policy decision
    -> required task-start HITL? (existing workflow)
       no  -> ordinary route, no HAA call
       yes + HAA selected -> existing adapter checkpoint
          -> one exact request -> existing owner ceremony
          -> APPROVED -> consume + detached verify against live input
          -> CHECKPOINT_PASS -> dispatch unchanged prompt via existing route
          -> any other result -> BLOCKED, no automatic fallback/retry
    -> existing QA/review/closure
```

Reuse `scripts/haa/adapter.py`, `client.py`, `authority.py`,
`contracts.py`, `grants.py`, the existing policy hash helper and
`workflow.task.start.v1`. Reuse the native approver and test harness.
No HAA core/protocol/profile changes. The session binds the exact Task Card
and prompt digests, measured RRI, policy sources, repository/branch/base
and permitted paths/capabilities. HAA receives no prompt text or credentials
from the prompt. The inherited profile requires a leaseTtlSeconds field;
this checkpoint sets 60 but **does not create or activate a lease**.
The grant is verified and consumed once for task start; its expiry is not a
claim that later model operations are technically confined.

## Minimal Workflow Guide insertion (contract, not installed)

At the existing required task-start approval step, after readiness and RRI:
if the owner selected HAA, invoke the existing adapter checkpoint below.
The trusted workflow/controller supplies the already resolved fields,
including the exact card and prompt files and allowed paths. Do not let the
implementation model decide whether approval is required or invent scope.
For Fénix/DubBridge, the adapter automatically fingerprints the existing
governing policy files; other projects explicitly supply their policy files.
Any additional task-specific governing file can be included with --policy-file.
The caller is responsible for matching the arguments to the approved card
and including all applicable policy sources; the adapter does not parse
arbitrary Markdown or recalculate RRI.

```sh
python ~/human-approval-authority/integrations/workflow-runtime/scripts/haa/adapter.py checkpoint \
  --repository krukmat/fenix --repo-root ~/fenix \
  --plan-id example-plan --task-id example-task --rri 42 \
  --task-card /path/to/final-card.md --prompt-file /path/to/final-prompt.txt \
  --allow-path 'scripts/example.py' --capability edit --capability test
```

Illustrative arguments, not an authorization or real project task.
Use the existing configured HAA endpoint (trusted local loopback or
authenticated TLS) with separate requester and executor credentials from the
existing controller environment. Keep APPROVER credentials and authenticator
in the existing human channel. The checkpoint prints HAA_REQUEST plus its
request ID on stderr and waits for that exact request; the existing HAA
operator/approver flow obtains the challenge, presents the trusted claims,
and submits evidence or rejection. It does not launch a new approval UI,
server, model, or project runner. If the owner channel is not available,
the checkpoint blocks/times out; no silent fallback to ordinary approval.

Only exit 0 plus CHECKPOINT_PASS allows the caller to dispatch the unchanged
prompt immediately; check the returned card/prompt SHA-256 against the bytes
actually dispatched, and honor expiresAt before starting. Never use a
previous JSON result, chat text, receipt or grant as a reusable approval.
On drift, rejection, expiry, unavailability or ambiguous consume, stop.
A fresh attempt needs a new explicit decision; never auto-retry. Keep
only non-secret audit identifiers in the existing task ledger. Do not
put grants or API keys into the prompt.

The checkpoint is **cooperative**, not system-level enforcement: a model or
human with direct Git/shell access may bypass it. It does not attest a
controller's policy judgement, parse the task card, constrain tool calls,
authorize commit/push/merge, or change QA. Cloud and local routing remain
unchanged; existing terminal/controller must call this checkpoint before
dispatch. ChatGPT web does not acquire a new local execution connection from
this code. No Fénix or DubBridge files were modified; the common guide
insertion is prepared here for later adoption under each project's own
rules. Do not claim installed hooks or automatic interception of prompts.

## Final local validation

Use the existing clean main checkout and venv, without sudo or worktrees:

```sh
cd ~/human-approval-authority &&
git pull --ff-only &&
source ~/haa-workflow-venv/bin/activate &&
python integrations/workflow-runtime/certify.py &&
npm test &&
./node_modules/.bin/tsc --noEmit &&
node --check scripts/validate-workflow-macos-e2e.mjs &&
node scripts/validate-workflow-macos-e2e.mjs --synthetic-touch-id --checkpoint
```

The existing physical harness uses a disposable loopback HAA server and
synthetic repository, one positive Touch ID for the exact task-start
checkpoint, no actual model invocation or product modification. It checks
waiting before approval, verified consumed grant, checkpoint result and
unchanged target, then cleans its temporary state. It does not require the
frozen host gate or a plan-close ceremony. A failed stage blocks subsequent
stages. Existing Node dependencies/signing and native approver prerequisites
must be available; do not silently install additional infrastructure.
Expected final status PASS_COOPERATIVE_CHECKPOINT_PHYSICAL. No production
activation or rollout follows automatically.

## Historical protected runtime plan (frozen, not active)

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
