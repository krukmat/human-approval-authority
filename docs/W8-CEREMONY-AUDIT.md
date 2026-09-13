# W8 ceremony audit and observability semantics

Status: FROZEN FOR HAA-ONLY IMPLEMENTATION

## Goal

Audit must distinguish what HAA can prove from what merely happened in a local UI process.

## Authoritative request audit

### APPROVE

The existing positive path records `APPROVED` only after authenticator evidence has been verified and the request transitioned to `APPROVED`.

The event may identify the verified authenticator. Positive authority remains represented by the existing receipt/grant chain rather than by the audit event alone.

### REJECT

An explicit rejection records `REJECTED` only after the HAA service verifies:

- authenticated `APPROVER` identity;
- exact configured approver principal;
- active challenge and exact challenge digest;
- signed challenge binding to request/action/intent;
- active authenticator ownership;
- supported explicit rejection reason.

The event details are:

```text
challengeDigest
authenticatorId
reason=USER_ESCAPE
provenance=authenticated-approver-channel
```

This event is included in the W7 `audit_events` hash chain and therefore participates in signed audit checkpoints.

The audit wording must not imply Touch ID, biometric proof, or Secure Enclave signature for REJECT.

### UNKNOWN

UNKNOWN is deliberately **not** written as `APPROVED`, `REJECTED` or another human-decision `AuditEvent`.

Typical UNKNOWN causes:

```text
WINDOW_CLOSED
LOCAL_TIMEOUT
APP_TERMINATED
INTERACTION_ERROR
AUTHENTICATOR_UNAVAILABLE
```

These are local ceremony observations. If the request is still valid, HAA remains `PENDING` and its authoritative audit history still shows only the server-side events that really occurred, such as `REQUESTED` and `CHALLENGE_ISSUED`.

Deployments may collect separate operational telemetry for app crashes/timeouts, but that telemetry is not human authorization evidence and must not be promoted into the request audit as a human decision.

### EXPIRED

True lifecycle expiry is distinct from UNKNOWN. A caller observing a local timeout does not have authority to rewrite a request as `EXPIRED`; expiry is determined by HAA lifecycle timestamps and server-side validation.

## Reconstruction rule

An auditor should be able to interpret a request as:

```text
APPROVED  -> HAA verified positive evidence
REJECTED  -> authenticated approver explicitly refused an exact active challenge
PENDING   -> no terminal human decision has been accepted yet
EXPIRED   -> authorization lifetime ended
CONSUMED  -> approved authority was used exactly once
```

UNKNOWN does not appear in this state reconstruction because it is not an `ApprovalState`.

## Security invariant

No audit record by itself creates execution authority.

```text
AuditEvent != ApprovalReceipt != ExecutionGrant
```

Only the existing positive `authorizeAndConsume(...)` path can produce an `ExecutionGrant`.
