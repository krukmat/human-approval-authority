# W8 universal ceremony outcomes

Status: FROZEN FOR HAA-ONLY IMPLEMENTATION

This document defines product-independent human ceremony outcomes for HAA. It does not introduce product workflow state, external integration contracts, or new approval-bearing protocol-v1 schemas.

## Outcome model

A human-facing HAA ceremony has exactly three caller-visible outcomes:

```text
APPROVE
REJECT
UNKNOWN
```

They do not have equal authority.

### APPROVE

`APPROVE` means HAA received and verified positive authenticator evidence for the exact signed challenge.

For the Apple path this means the Secure Enclave-backed approval signature was released after successful user verification through Touch ID.

Only APPROVE may lead to:

```text
ApprovalEvidence
  -> VerifiedEvidence
  -> ApprovalReceipt
  -> authorizeAndConsume(...)
  -> ExecutionGrant
```

### REJECT

`REJECT` means the active approver explicitly refused the currently displayed challenge.

Initial macOS UX mapping:

```text
Esc -> REJECT
```

REJECT is deliberately lower-assurance than APPROVE. It is not represented as biometric/Secure Enclave approval evidence and must never be described as such.

Server-side acceptance of REJECT requires all of the following:

- an authenticated client with the `APPROVER` role;
- the client identity equals the request `approverPrincipalId`;
- the request is still `PENDING`;
- the supplied challenge digest resolves to an active, unconsumed challenge;
- the challenge is bound to the same request and approver authenticator;
- the challenge payload still binds the request action/intent digests;
- the rejection reason is an allowed typed value.

A valid explicit reject consumes that challenge, transitions `PENDING -> REJECTED`, and records a `REJECTED` audit event.

REJECT never creates `ApprovalReceipt` or `ExecutionGrant`.

### UNKNOWN

`UNKNOWN` means HAA cannot truthfully attribute a positive or negative decision to the human.

Initial causes include:

```text
WINDOW_CLOSED
LOCAL_TIMEOUT
APP_TERMINATED
INTERACTION_ERROR
AUTHENTICATOR_UNAVAILABLE
```

UNKNOWN is a ceremony/caller outcome only. It is **not** added to frozen `ApprovalState` and it is not persisted as a human decision.

If the underlying request remains valid, an UNKNOWN ceremony leaves the request `PENDING` and another challenge/ceremony may be attempted.

A real request/challenge expiry remains expiry semantics; it must not be rewritten as human rejection.

## State effects

```text
PENDING
  |
  +-- APPROVE -> APPROVED
  |
  +-- REJECT  -> REJECTED
  |
  +-- UNKNOWN -> PENDING (if still valid)
```

Terminal technical/request expiry remains:

```text
PENDING -> EXPIRED
```

when the request lifecycle actually expires.

## Fail-closed invariant

```text
Only verified APPROVE evidence can create execution authority.
```

Therefore both REJECT and UNKNOWN are fail-closed with respect to execution.

## Compatibility rule

HAA protocol v1 already contains `REJECTED` and `EXPIRED`. No existing signed v1 object is extended or reinterpreted by W8.

W8 may add service/SDK response types and local ceremony records outside the frozen authorization-bearing schema set, but it must not silently add fields to:

- `haa.intent.v1`
- `haa.request.v1`
- `haa.challenge-payload.v1`
- `haa.challenge.v1`
- `haa.evidence.v1`
- `haa.receipt.v1`
- `haa.execution-grant.v1`

## Caller contract

The generic caller-facing shape is:

```ts
type CeremonyOutcome = 'APPROVE' | 'REJECT' | 'UNKNOWN'

interface CeremonyResult {
  outcome: CeremonyOutcome
  requestId: string
  reason?: string
  state?: ApprovalState
}
```

`state` is server state when known. `UNKNOWN` may be produced locally without a server mutation.

## Non-goals

W8 does not define:

- external product workflow transitions;
- task start/close semantics;
- deployment/merge/provider-call policy;
- WebAuthn;
- hardware terminal behavior;
- a generic policy engine.
