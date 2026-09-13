# Future DubBridge task-authority integration

Status: **FUTURE / NOT STARTED**

This integration is intentionally deferred until HAA software productization and the W7 final security/architecture review are complete. DubBridge-specific workflow semantics remain outside the universal HAA core.

## Integration thesis

HAA acts as the human authorization authority over two meaningful DubBridge task-state transitions:

```text
READY_FOR_APPROVAL
        │
        ▼
 HAA task-start.v1
        │
        ▼
    IN_PROGRESS
        │
        ▼
 agents / tests / review / reflection / coverage
        │
        ▼
READY_FOR_ACCEPTANCE
        │
        ▼
 HAA task-close.v1
        │
        ▼
       DONE
```

The authority boundary is strict:

```text
DubBridge = workflow authority
HAA       = human authorization authority
```

DubBridge owns task definition, RRI, scope, allowed paths, implementation routing, reviewers, tests, behavioral evidence, task state and requested transition. HAA does not recompute or reinterpret any of those decisions. HAA answers only whether the exact typed transition intent received an acceptable human ceremony outcome.

The previous `dubbridge.ai-execution.v1` provider/model authorization concept is no longer the primary W8 path. It may return later as a fine-grained action-authorization extension after task authority is proven useful.

## Ceremony outcome model

W8 uses three terminal ceremony outcomes:

```text
APPROVE = explicit positive human authorization
REJECT  = explicit negative human decision
UNKNOWN = no conclusive human decision
```

Initial macOS interaction mapping:

```text
successful Touch ID  -> APPROVE
Esc                   -> REJECT
window close          -> UNKNOWN
timeout               -> UNKNOWN
challenge expiry      -> UNKNOWN
technical interruption-> UNKNOWN
```

Only `APPROVE` can produce `ApprovalEvidence`, pass `authorizeAndConsume`, and yield an `ExecutionGrant`.

`REJECT` and `UNKNOWN` are fail-closed audit outcomes and **never** produce execution capability.

The semantic distinction is deliberate:

- `REJECT` means the human explicitly refused the requested transition.
- `UNKNOWN` means the system cannot truthfully claim either human approval or human rejection.

### State effects

At task start:

```text
READY_FOR_APPROVAL
   ├─ APPROVE -> IN_PROGRESS
   ├─ REJECT  -> CHANGES_REQUESTED
   └─ UNKNOWN -> READY_FOR_APPROVAL
```

At task close:

```text
READY_FOR_ACCEPTANCE
   ├─ APPROVE -> DONE
   ├─ REJECT  -> CHANGES_REQUESTED
   └─ UNKNOWN -> READY_FOR_ACCEPTANCE
```

`UNKNOWN` never advances or rewinds workflow state. It leaves the task at the same human gate so the ceremony can be retried against the same manifest if it is still fresh and valid.

`REJECT` never deletes, reverts or mutates implementation output. It records refusal and routes the task to `CHANGES_REQUESTED`; subsequent revision produces a new manifest/digest and therefore requires a new ceremony.

## Cross-manifest trust chain

Two immutable, versioned manifests define what the human is authorizing.

### TaskAuthorizationManifest

Created after task definition, RRI, scope, acceptance criteria and routing are frozen, before implementation begins.

Minimum fields:

```yaml
schema: dubbridge.task-authorization.v1
repository: krukmat/dubbridge
task_id: P2.T3c-S3
branch: feature/p2p-mvp-core
scope:
  allowed_paths: []
  scope_digest: sha256:...
rri:
  score: 37
  band: Moderate
acceptance_digest: sha256:...
implementation_route_digest: sha256:...
review_route_digest: sha256:...
transition:
  from: READY_FOR_APPROVAL
  to: IN_PROGRESS
```

The manifest is canonicalized and digested. Scope, acceptance, RRI, routing or task identity mutation invalidates the authorization.

### TaskClosureManifest

Created only after DubBridge's existing closure gates have completed.

Minimum fields:

```yaml
schema: dubbridge.task-closure.v1
task_id: P2.T3c-S3
authorization_digest: sha256:...
repository:
  branch: feature/p2p-mvp-core
  head_sha: abc123...
  change_digest: sha256:...
verification:
  tests_digest: sha256:...
  review_digest: sha256:...
  reflection_digest: sha256:...
  behavioral_coverage_digest: sha256:...
transition:
  from: READY_FOR_ACCEPTANCE
  to: DONE
```

A closure manifest MUST reference the exact `TaskAuthorizationManifest` digest under which the work was authorized. This creates the audit chain:

```text
human-authorized task definition
          │
          ▼
TaskAuthorizationManifest
          │
          ▼
agents implement within that envelope
          │
          ▼
verification / review / evidence
          │
          ▼
TaskClosureManifest
          │
          ▼
human accepts exact result
          │
          ▼
DONE
```

## W8 plan and tasks

### W8A — Contract and lifecycle freeze

#### W8-T01 — Integration ADR and authority boundaries

Dependencies: `W7-T05`

Freeze:

- DubBridge vs HAA responsibility boundary;
- HAA placement at task start and task close only;
- no provider/model/routing logic inside HAA;
- no task-management authority inside HAA;
- threat model for a compromised/buggy agent attempting to self-advance task state.

Acceptance: architecture explicitly proves that an agent can propose/request a transition but cannot create the human authority required to advance it.

#### W8-T02 — Task lifecycle and ceremony outcome semantics

Dependencies: `W8-T01`

Freeze task states and transitions, including:

- `READY_FOR_APPROVAL -> IN_PROGRESS` through APPROVE only;
- start REJECT -> `CHANGES_REQUESTED`;
- start UNKNOWN -> remain `READY_FOR_APPROVAL`;
- `READY_FOR_ACCEPTANCE -> DONE` through APPROVE only;
- close REJECT -> `CHANGES_REQUESTED`;
- close UNKNOWN -> remain `READY_FOR_ACCEPTANCE`.

Freeze ceremony mapping:

- Touch ID success -> APPROVE;
- Esc -> REJECT;
- close/timeout/expiry/interruption -> UNKNOWN.

Acceptance: tests/specification demonstrate that only APPROVE is state-advancing and that UNKNOWN never claims human intent.

#### W8-T03 — `TaskAuthorizationManifest v1`

Dependencies: `W8-T01`, `W8-T02`

Define canonical fields, digest rules, trusted display claims and mutation semantics for the pre-implementation contract.

Acceptance: changing task ID, scope, RRI, acceptance contract, route or transition changes the canonical digest and invalidates a prior authorization.

#### W8-T04 — `TaskClosureManifest v1`

Dependencies: `W8-T01`, `W8-T02`, `W8-T03`

Define canonical closure fields and mandatory `authorization_digest` linkage.

Acceptance: changing repository snapshot, implementation diff/evidence, review/coverage evidence, authorization link or requested transition invalidates a prior closure authorization.

### W8B — HAA ceremony and ActionProfiles

#### W8-T05 — Decision outcome records and fail-closed semantics

Dependencies: `W8-T02`, `W7-T01`

Add a backward-compatible audit model for non-approval outcomes without weakening the existing approval protocol.

Initial concepts:

```text
ApprovalEvidence / ApprovalReceipt -> APPROVE path
RejectionRecord                    -> REJECT audit only
IndeterminateRecord                -> UNKNOWN audit only
```

Minimum non-approval record bindings:

- request ID;
- challenge digest or request digest as appropriate;
- authenticator/session identity when known;
- terminal outcome;
- typed reason;
- timestamp.

Suggested typed reasons:

```text
REJECT:
  USER_ESCAPE

UNKNOWN:
  WINDOW_CLOSED
  TIMEOUT
  CHALLENGE_EXPIRED
  APP_TERMINATED
  INTERACTION_ERROR
  AUTHENTICATOR_UNAVAILABLE
```

No `RejectionRecord` or `IndeterminateRecord` may be accepted by `authorizeAndConsume` or converted into an `ExecutionGrant`.

#### W8-T06 — `dubbridge.task-start.v1` ActionProfile

Dependencies: `W8-T03`, `W8-T05`

Implement typed action/profile semantics for authorizing task execution.

Trusted display should expose at minimum:

```text
AUTHORIZE DUBBRIDGE TASK
Task       P2.T3c-S3
RRI        37 / Moderate
Scope      <bounded summary>
Acceptance <bounded summary>
Route      <resolved route>
READY_FOR_APPROVAL -> IN_PROGRESS

Esc: Reject
Approve: Touch ID
```

Window close/timeout are UNKNOWN, not rejection.

#### W8-T07 — `dubbridge.task-close.v1` ActionProfile

Dependencies: `W8-T04`, `W8-T05`

Implement typed action/profile semantics for accepting the exact result.

Trusted display should expose at minimum:

```text
ACCEPT DUBBRIDGE TASK RESULT
Task       P2.T3c-S3
HEAD       abc1234
Tests      PASS
Review     PASS
Coverage   PASS
READY_FOR_ACCEPTANCE -> DONE

Esc: Reject
Approve: Touch ID
```

The profile must bind the closure to its `authorization_digest` even when that digest is not fully displayed.

#### W8-T08 — Profile and decision security gate

Dependencies: `W8-T06`, `W8-T07`

Test at minimum:

- changed task -> deny;
- changed scope -> deny;
- changed authorization digest -> deny;
- changed repository HEAD/change digest -> deny;
- changed evidence -> deny;
- wrong executor audience -> deny;
- expired approval -> deny;
- replay with a new execution ID -> deny;
- retry with the same execution ID -> idempotent;
- REJECT -> no grant;
- UNKNOWN -> no grant;
- close/timeout -> UNKNOWN rather than REJECT;
- Esc -> REJECT rather than UNKNOWN.

### W8C — DubBridge adapters

#### W8-T09 — Thin HAA client and configuration adapter

Dependencies: `W8-T08`, `W7-T02`, `W7-T03`

Create a narrow DubBridge-side adapter against HAA's public HTTP/protocol surface. It must not import HAA core internals.

Because DubBridge's workflow tooling already uses Python, the initial adapter may be Python/HTTP rather than introducing Node into the repository solely for HAA. A future Python SDK can replace the thin HTTP adapter without changing the integration contracts.

#### W8-T10 — Task Start Gate

Dependencies: `W8-T03`, `W8-T06`, `W8-T09`

Flow:

```text
frozen task definition
      │
      ▼
TaskAuthorizationManifest
      │
      ▼
HAA ceremony
  ├─ APPROVE -> ExecutionGrant -> IN_PROGRESS
  ├─ REJECT  -> CHANGES_REQUESTED
  └─ UNKNOWN -> READY_FOR_APPROVAL
```

The implementation route cannot begin before a valid start grant where the DubBridge policy requires human approval.

#### W8-T11 — Task Closure Gate

Dependencies: `W8-T04`, `W8-T07`, `W8-T09`, `W8-T10`

Flow:

```text
implementation complete
      │
verification / review / reflection / coverage
      │
      ▼
TaskClosureManifest
      │
      ▼
HAA ceremony
  ├─ APPROVE -> ExecutionGrant -> DONE
  ├─ REJECT  -> CHANGES_REQUESTED
  └─ UNKNOWN -> READY_FOR_ACCEPTANCE
```

The closure executor records the HAA attestation and synchronizes the existing DubBridge owner-verification/status artifacts only after APPROVE. REJECT and UNKNOWN never mark the task Done.

### W8D — Dual-gate validation

#### W8-T12 — Automated dual-gate end-to-end gate

Dependencies: `W8-T10`, `W8-T11`

Demonstrate without physical Touch ID dependency:

1. task start is blocked before approval;
2. APPROVE advances to `IN_PROGRESS`;
3. REJECT routes to `CHANGES_REQUESTED`;
4. UNKNOWN leaves `READY_FOR_APPROVAL` unchanged;
5. closure is blocked before acceptance;
6. APPROVE advances to `DONE`;
7. REJECT routes to `CHANGES_REQUESTED` without deleting work;
8. UNKNOWN leaves `READY_FOR_ACCEPTANCE` unchanged;
9. scope drift and post-approval mutation fail closed;
10. the closure manifest is linked to the exact authorization manifest;
11. agent-facing status can be observed without exposing self-approval capability.

#### W8-T13 — Physical macOS/Touch ID dual-gate gate

Dependencies: `W8-T12`

Validate the real workflow:

```text
DubBridge task proposal
        ↓
HAA task-start
        ↓
Touch ID #1
        ↓
IN_PROGRESS
        ↓
agents / tests / review / reflection
        ↓
READY_FOR_ACCEPTANCE
        ↓
HAA task-close
        ↓
Touch ID #2
        ↓
DONE
```

Also physically validate:

- Esc produces REJECT;
- window close produces UNKNOWN;
- timeout produces UNKNOWN;
- no non-APPROVE path yields an ExecutionGrant.

### W8E — Controlled adoption

#### W8-T14 — Opt-in feature flag and workflow documentation

Dependencies: `W8-T13`

Introduce task authority as opt-in first, with explicit configuration and rollback to the current DubBridge human workflow.

#### W8-T15 — Pilot on one real DubBridge task

Dependencies: `W8-T14`

Evaluate:

- agent autonomy between the two human gates;
- ceremony UX burden;
- false/stale approval behavior;
- REJECT correction loop;
- UNKNOWN retry behavior;
- audit reconstruction across DubBridge and HAA.

#### W8-T16 — Adoption decision / default-on gate

Dependencies: `W8-T15`

Decide whether HAA task authority remains optional or becomes the default for selected DubBridge task classes. Do not make it globally mandatory without pilot evidence.

## Dependency graph

```text
                         W7-T05
                            │
                            ▼
                         W8-T01
                            │
                            ▼
                         W8-T02
                       /    │    \
                      ▼     ▼     ▼
                 W8-T03  W8-T05  W8-T04
                    │       │       │
                    └──┐    │    ┌──┘
                       ▼    ▼    ▼
                    W8-T06  W8-T07
                       \      /
                        \    /
                         ▼  ▼
                         W8-T08
                            │
                            ▼
                         W8-T09
                         /    \
                        ▼      ▼
                    W8-T10   W8-T11
                        \      /
                         ▼    ▼
                         W8-T12
                            │
                            ▼
                         W8-T13
                            │
                            ▼
                         W8-T14
                            │
                            ▼
                         W8-T15
                            │
                            ▼
                         W8-T16
```

`W8-T11` also depends logically on `W8-T10` because every valid `TaskClosureManifest` must reference a real authorization digest produced under the start-gate contract.

## Critical path

The minimum integration proving the architecture is:

```text
W8-T01
  ↓
W8-T02
  ↓
W8-T03 + W8-T04 + W8-T05
  ↓
W8-T06 + W8-T07
  ↓
W8-T08
  ↓
W8-T09
  ↓
W8-T10
  ↓
W8-T11
  ↓
W8-T12
  ↓
W8-T13
```

W8-T14 through W8-T16 are rollout/adoption, not architecture proof.

## Explicit non-goals for W8

- Hardware authenticator implementation is not a dependency.
- HAA does not replace RRI.
- HAA does not choose local/cloud/model/reviewer routes.
- HAA does not judge test sufficiency or review quality.
- HAA does not automatically commit, push, merge or deploy as part of task-close.
- REJECT does not revert or delete implementation work.
- UNKNOWN is never represented as a human rejection.
- No non-APPROVE ceremony outcome can produce execution authority.

## Future extension

After W8 proves task-level human authority, a later wave may add fine-grained profiles such as:

```text
dubbridge.ai-execution.v1
git.commit.v1
git.push.v1
git.merge.v1
deployment.execute.v1
```

Those are intentionally outside the W8 critical path.