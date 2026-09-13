# W8 ceremony audit and observability semantics

Status: FROZEN FOR HAA-ONLY IMPLEMENTATION

## Goal

Audit must distinguish strong positive authorization from negative fail-closed outcomes without overstating what HAA can prove about human intent.

## Authoritative request audit

### APPROVE

The existing positive path records `APPROVED` only after authenticator evidence has been verified and the request transitioned to `APPROVED`.

The event may identify the verified authenticator. Positive authority remains represented by the existing receipt/grant chain rather than by the audit event alone.

### REJECT

A terminal rejection records `REJECTED` only after HAA verifies:

- authenticated `APPROVER` identity;
- exact configured approver principal;
- exact request/challenge binding;
- HAA-signed challenge payload and action/intent digests;
- active authenticator ownership;
- supported typed rejection reason;
- reason-specific expiry semantics.

Event details include:

```text
challengeDigest
authenticatorId
reason
provenance=authenticated-approver-channel
assurance
```

Supported reasons:

```text
USER_ESCAPE
WINDOW_CLOSED
TIMEOUT
CHALLENGE_EXPIRED
INTERACTION_ERROR
```

Assurance interpretation:

```text
USER_ESCAPE
  assurance=explicit-human-negative-action

WINDOW_CLOSED / TIMEOUT / CHALLENGE_EXPIRED / INTERACTION_ERROR
  assurance=fail-closed-terminal
```

All are operational REJECT outcomes and all block execution. Only `USER_ESCAPE` means the trusted UI observed the explicit negative key action. The others do not prove the human consciously chose Reject.

`REJECTED` participates in the W7 `audit_events` hash chain and signed checkpoints.

### EXPIRED

Request lifecycle expiry is separate from ceremony rejection.

```text
reason=REQUEST_TTL -> request state EXPIRED
```

A challenge may expire before the request TTL. In that case a terminal ceremony can be recorded as `REJECTED` with `reason=CHALLENGE_EXPIRED`, while actual request-TTL expiry remains `EXPIRED`.

## Reconstruction rule

An auditor interprets a request as:

```text
APPROVED  -> HAA verified positive authenticator evidence
REJECTED  -> ceremony terminated without positive authorization; inspect reason + assurance
PENDING   -> no terminal ceremony/lifecycle transition accepted yet
EXPIRED   -> request authorization lifetime ended
CONSUMED  -> approved authority was used exactly once
```

For any `REJECTED` record, reason and assurance are mandatory for understanding provenance. The state alone must not be translated into “the human explicitly rejected”.

## Security invariant

No audit record by itself creates execution authority.

```text
AuditEvent != ApprovalReceipt != ExecutionGrant
```

Only the verified positive `authorizeAndConsume(...)` path can produce an `ExecutionGrant`.
