# W8 universal ceremony outcomes

Status: FROZEN FOR HAA-ONLY IMPLEMENTATION

This document defines product-independent human ceremony outcomes for HAA. It does not introduce product workflow state, external integration contracts, or new approval-bearing protocol-v1 schemas.

## Outcome model

A terminal HAA ceremony has exactly two operational outcomes:

```text
APPROVE
REJECT
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

`REJECT` means the requested transition did not complete through a successful positive ceremony. It never grants authority.

Supported terminal reasons:

```text
USER_ESCAPE
WINDOW_CLOSED
TIMEOUT
CHALLENGE_EXPIRED
INTERACTION_ERROR
```

The assurance claim depends on the reason:

```text
USER_ESCAPE       -> explicit-human-negative-action
all other reasons -> fail-closed-terminal
```

Only `USER_ESCAPE` claims that the human explicitly performed the negative UI action. `WINDOW_CLOSED`, `TIMEOUT`, `CHALLENGE_EXPIRED` and `INTERACTION_ERROR` are negative fail-closed outcomes; they must not be described as biometric rejection, Touch ID rejection or proof that the human consciously chose Reject.

Server-side acceptance of a terminal rejection requires all of the following:

- authenticated client with `APPROVER` role;
- client identity equals `request.intent.approverPrincipalId`;
- request is still `PENDING` and its request TTL has not elapsed;
- supplied challenge digest resolves to the exact unconsumed challenge;
- HAA authority signature and request/action/intent bindings verify;
- bound authenticator still belongs to the approver principal and is ACTIVE;
- rejection reason is typed and allowed;
- `CHALLENGE_EXPIRED` is accepted only when the bound challenge is actually expired;
- non-expiry reasons cannot be used after challenge expiry.

A valid reject consumes the challenge, transitions `PENDING -> REJECTED`, records reason/provenance/assurance, and never creates `ApprovalReceipt` or `ExecutionGrant`.

## State effects

```text
PENDING
  |
  +-- APPROVE -> APPROVED
  |
  +-- REJECT  -> REJECTED
```

The request lifecycle separately supports:

```text
PENDING  -> EXPIRED
APPROVED -> EXPIRED
```

when the request TTL itself expires.

`CHALLENGE_EXPIRED` and request `EXPIRED` are therefore different concepts:

- challenge expiry can terminate a still-valid request ceremony as REJECT;
- request TTL expiry terminates the request lifecycle as EXPIRED.

## Fail-closed invariant

```text
Only verified APPROVE evidence can create execution authority.
Every other terminal ceremony outcome is REJECT.
```

## Compatibility rule

HAA protocol v1 already contains `REJECTED` and `EXPIRED`. No existing signed v1 object is extended or reinterpreted by W8.

W8 adds service/SDK response metadata outside the frozen authorization-bearing schema set, but it does not silently add fields to:

- `haa.intent.v1`
- `haa.request.v1`
- `haa.challenge-payload.v1`
- `haa.challenge.v1`
- `haa.evidence.v1`
- `haa.receipt.v1`
- `haa.execution-grant.v1`

## Caller contract

```ts
type CeremonyOutcome = 'APPROVE' | 'REJECT'

type RejectionReason =
  | 'USER_ESCAPE'
  | 'WINDOW_CLOSED'
  | 'TIMEOUT'
  | 'CHALLENGE_EXPIRED'
  | 'INTERACTION_ERROR'
```

A rejection record includes exact request/challenge binding, typed reason, timestamp, authenticated approver-channel provenance, and assurance classification.

## Non-goals

W8 does not define:

- external product workflow transitions;
- task start/close semantics;
- deployment/merge/provider-call policy;
- WebAuthn;
- hardware terminal behavior;
- a generic policy engine.
