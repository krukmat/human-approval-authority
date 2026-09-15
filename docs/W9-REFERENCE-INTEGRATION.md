# W9 — Reference Integration / Adoption Gate

Status: **ACTIVE**

Goal: prove that HAA can be consumed as an independent product from outside its own monorepo, using only public contracts and without weakening the HAA-only baseline closed in W8.

W9 is deliberately an adoption wave, not another core-hardening wave.

## Guardrails

- HAA core changes require evidence from a real external consumer.
- No private imports from HAA implementation packages are allowed in the reference consumer.
- Protocol v1 remains frozen.
- `ApprovalReceipt` remains audit evidence only.
- Only a verified `ExecutionGrant` authorizes the external side effect.
- Hardware W5/W6 and WebAuthn W7-T04 remain outside W9 unless separately reprioritized.
- A consumer-specific convenience must not silently become a generic core feature.

## Task map

### W9-T01 — Release baseline

Status: **DONE**

Depends on: `W8-T09`.

Delivered:

- immutable W9 code baseline `e68b6ad8b8b3901f095e47111aa5545c132cf964`;
- product/package version map;
- `CHANGELOG.md`;
- `docs/RELEASE-BASELINE.md`;
- machine-specific Apple Development Team removed before freeze;
- Xcode project restored to the signing-neutral form used by the physical W8 gate.

Acceptance: the starting product state is identified by immutable SHA and its protocol/SDK versions are explicit.

### W9-T02 — Minimal external integration contract

Status: **DONE**

Depends on: `W9-T01`.

Delivered: `docs/EXTERNAL-INTEGRATION.md`.

Acceptance:

- public integration surfaces are explicit;
- REQUESTER / APPROVER / EXECUTOR responsibilities are explicit;
- minimal request → ceremony → authorize → detached verify → execute path is documented;
- crash/idempotency and authority-key trust boundaries are explicit;
- no private HAA implementation import is part of the contract.

### W9-T03 — Reference external consumer

Status: **READY**

Depends on: `W9-T02`.

Create or adapt one repository outside `human-approval-authority` that consumes HAA as if it were a third-party product.

First slice may use `demo.action.v1` strictly to prove package/API separation.

Acceptance:

- consumer lives outside the HAA monorepo;
- uses only HTTP / `@haa/protocol` / `@haa/sdk` and documented operator/authenticator surfaces;
- no source copy/private import/workspace dependency into HAA;
- separate requester/executor credentials are used;
- APPROVED request state alone cannot trigger the side effect.

### W9-T04 — Real ActionProfile

Status: **BLOCKED**

Depends on: `W9-T03`.

Replace the integration-smoke profile with one real consumer action.

Acceptance:

- typed and versioned profile;
- strict payload/precondition allowlists;
- all authorization-relevant semantics are digest-bound;
- trusted display exposes the human-significant fields;
- unknown fields fail closed.

### W9-T05 — External executor integration

Status: **BLOCKED**

Depends on: `W9-T03`, `W9-T04`.

Implement the actual executor boundary outside HAA.

Acceptance:

- reads actual target state from the external source of truth;
- uses durable/fresh execution ID according to retry semantics;
- calls `authorizeAndConsume` before mutation;
- detached-verifies `ExecutionGrant` with trusted ACTIVE authority metadata;
- performs the side effect only after verification;
- side effect has an explicit idempotency/recovery strategy.

### W9-T06 — External integration E2E

Status: **BLOCKED**

Depends on: `W9-T05`.

Prove the complete external path:

```text
external requester
  -> HAA
  -> human ceremony
  -> exact ExecutionGrant
  -> external executor
  -> real bounded side effect
```

Required negative cases:

- REJECT;
- mutated action;
- stale precondition;
- wrong executor audience;
- replay / different execution ID after consumption;
- same execution ID recovery/idempotency.

Acceptance: only the exact approved action can execute under the intended executor audience and current preconditions.

### W9-T07 — Adoption-gap review

Status: **BLOCKED**

Depends on: `W9-T06`.

Classify each friction discovered by real integration as:

```text
CORE_FIX
INTEGRATION_FIX
DOCS
ACCEPTED_RISK
NO_ACTION
```

Acceptance: no core change is justified only by convenience or speculation; every proposed HAA change has concrete integration evidence.

### W9-T08 — Integration-readiness gate

Status: **BLOCKED**

Depends on: `W9-T07`.

Final acceptance:

- external E2E green;
- no private HAA dependency in the consumer;
- no open BLOCKING/P1 adoption finding;
- real ActionProfile trusted display is complete;
- execution requires detached-valid grant;
- failure/rejection paths fail closed;
- deployment and credential assumptions are documented;
- HAA remains consumer-agnostic.

## Dependency view

```text
W8-T09 DONE
    |
    v
W9-T01 Release baseline        DONE
    |
    v
W9-T02 Integration contract    DONE
    |
    v
W9-T03 External consumer       READY
    |
    v
W9-T04 Real ActionProfile
    |
    v
W9-T05 External executor
    |
    v
W9-T06 External E2E
    |
    v
W9-T07 Adoption-gap review
    |
    v
W9-T08 Integration-readiness gate
```

## Current decision point

The next action is W9-T03: select the first external consumer repository. That selection should optimize for a small, auditable real side effect rather than breadth of features.
