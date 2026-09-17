# W9 — Reference Integration / Adoption Gate

Status: **CLOSED / PASS_WITH_FOLLOWUPS**

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

Delivered:

- immutable W9 starting baseline `e68b6ad8b8b3901f095e47111aa5545c132cf964`;
- product/package version map;
- `CHANGELOG.md`;
- `docs/RELEASE-BASELINE.md`;
- signing-neutral Xcode project baseline.

### W9-T02 — Minimal external integration contract

Status: **DONE**

Delivered: `docs/EXTERNAL-INTEGRATION.md`.

Public integration surfaces, actor separation, authorization flow, detached verification, failure handling and idempotency boundaries are explicit.

### W9-T03 — Reference external consumer

Status: **DONE**

Reference consumer: `krukmat/verifiable-event-ledger`.

The consumer lives outside the HAA monorepo, uses public HTTP contracts only, has separate requester/executor credentials, and cannot execute from APPROVED state alone.

### W9-T04 — Real ActionProfile

Status: **DONE**

The existing `git.merge.v1` profile was validated as sufficient for the reference consumer. No new profile or protocol-v1 change was required.

See `docs/W9-GIT-MERGE-PROFILE-REVIEW.md`.

### W9-T05 — External executor integration

Status: **DONE_WITH_FOLLOWUP**

The external Python executor:

- reads actual Git state;
- reconstructs the exact `git.merge.v1` action;
- calls `authorizeAndConsume` before mutation;
- detached-verifies the returned ExecutionGrant against ACTIVE authority metadata;
- rechecks local Git state before mutation;
- restricts the side effect to `git merge --ff-only`.

A P2 adoption follow-up remains: automate post-merge same-execution reconciliation. Current behavior is fail-closed and cannot duplicate execution.

### W9-T06 — External integration E2E

Status: **DONE**

Physical macOS run on 2026-09-17 proved:

```text
external VEL requester
  -> HAA PENDING
  -> executor denied before approval
  -> trusted Git merge display
  -> human Touch ID approval
  -> ApprovalReceipt
  -> external authorizeAndConsume
  -> detached grant verification
  -> exact temporary-clone fast-forward merge
  -> CONSUMED
  -> exactly one consumption audit event
```

Physical external VEL baseline:

`faa3561a0796c088ad4d7a8b6f9eeb79b22d8565`

The required deterministic negative invariants remain covered by the automated HAA service/core gates and external executor tests rather than duplicating already-closed W8 physical ceremony cases.

### W9-T07 — Adoption-gap review

Status: **DONE**

See `docs/W9-ADOPTION-REVIEW.md`.

No BLOCKING or P1 adoption findings remain. Concrete integration friction was classified without expanding HAA core speculatively.

### W9-T08 — Integration-readiness gate

Status: **DONE / PASS_WITH_FOLLOWUPS**

Final acceptance:

- external E2E green;
- no private HAA dependency in the consumer;
- no open BLOCKING/P1 adoption finding;
- real ActionProfile trusted display complete;
- execution requires detached-valid grant;
- failure/rejection paths fail closed;
- deployment and credential assumptions documented;
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
W9-T03 External consumer       DONE
    |
    v
W9-T04 Real ActionProfile      DONE
    |
    v
W9-T05 External executor       DONE_WITH_FOLLOWUP
    |
    v
W9-T06 External E2E            DONE
    |
    v
W9-T07 Adoption review         DONE
    |
    v
W9-T08 Readiness gate          DONE / PASS_WITH_FOLLOWUPS
```

## Outcome

W9 demonstrated that HAA can be adopted from another repository and language without private implementation coupling or a new HAA core feature.

The remaining P2 follow-ups are adoption/developer-experience improvements, not security gate failures. Hardware W5/W6 remains deferred/blocked and WebAuthn W7-T04 remains optional/deferred.
