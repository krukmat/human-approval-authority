# @haa/sdk

Typed requester/executor/ceremony client for Human Approval Authority.

## Install

```bash
npm install @haa/sdk @haa/protocol
```

## Request approval

```ts
import { HaaClient, type ActionSpec } from '@haa/sdk';

const haa = new HaaClient('https://haa.internal.example', process.env.HAA_API_KEY!);

const action: ActionSpec = {
  schema: 'haa.action.v1',
  type: 'demo.action.v1',
  payload: {
    resource: 'release-service',
    operation: 'deploy',
  },
  preconditions: {
    version: 'v42',
  },
};

const request = await haa.requestApproval({
  action,
  approverPrincipalId: 'human-prod',
  executorAudience: 'executor-prod',
});
```

## Ceremony outcomes

A terminal HAA ceremony has exactly two operational outcomes:

```text
APPROVE  successful verified positive authenticator evidence
REJECT   every other terminal ceremony outcome
```

Only APPROVE can eventually produce an `ExecutionGrant`.

The supported rejection reasons are:

```text
USER_ESCAPE
WINDOW_CLOSED
TIMEOUT
CHALLENGE_EXPIRED
INTERACTION_ERROR
```

They do not all make the same human-intent claim. `USER_ESCAPE` is an explicit negative human action. The other reasons are fail-closed terminal outcomes and must not be described as biometric or explicit human rejection.

An approver-side client submits the terminal result against the exact challenge:

```ts
const result = await approverClient.rejectApproval({
  requestId: request.id,
  challengeDigest,
  reason: 'TIMEOUT',
});

// {
//   outcome: 'REJECT',
//   state: 'REJECTED',
//   reason: 'TIMEOUT',
//   assurance: 'fail-closed-terminal',
//   ...
// }
```

`rejectApproval` must use the configured approver principal's `APPROVER` credential. Requester/executor credentials cannot create a trusted rejection merely because they know the request ID or challenge digest.

A real request TTL expiry remains the lifecycle state `EXPIRED`; it is not rewritten as ceremony `REJECTED`.

## Authorize exact execution

```ts
const grant = await haa.authorize({
  requestId: request.id,
  executionId: crypto.randomUUID(),
  actualAction: action,
  actualState: { version: 'v42' },
});
```

The executor must treat `ExecutionGrant` as the execution authority. `ApprovalReceipt` is audit evidence and is not a bearer capability.

## Detached grant verification

When a grant is transported through an intermediary, verify it independently before execution:

```ts
import { verifyExecutionGrant } from '@haa/sdk';

const authorityKeys = await haa.getAuthorityKeys();

verifyExecutionGrant({
  grant,
  authorityKeys,
  expectedRequestId: request.id,
  expectedExecutionId: grant.executionId,
  expectedActionDigest: request.actionDigest,
  expectedExecutorAudience: 'executor-prod',
});
```

`authorityKeys` is trusted verification-policy input. Obtain it from the authenticated/TLS-protected HAA authority endpoint or from pinned operator configuration; do not accept authority-key status metadata from the same untrusted intermediary that transports the grant.

Live execution authority is stricter than historical signature verification. `verifyExecutionGrant(...)` accepts only the **currently ACTIVE** authority key. A RETIRED key remains useful for historical verification of artifacts such as receipts/audit evidence, but it cannot authorize a live detached `ExecutionGrant`.

The verifier also checks:

- strict object shape and supported schema/algorithm;
- signature and exact request/action/execution/audience bindings;
- `issuedAt < expiresAt`;
- grant issuance is not unreasonably in the future;
- issuance is not before the ACTIVE key's creation time when that metadata is present;
- the grant TTL does not exceed the v1 default execution policy (30 seconds unless the executor explicitly supplies another trusted local policy);
- the grant has not expired.

This prevents a retained/compromised RETIRED private key from minting fresh execution authority after key rotation.

## Errors

HTTP failures throw `HaaApiError`:

```ts
import { HaaApiError } from '@haa/sdk';

try {
  await haa.getApproval('missing-id');
} catch (error) {
  if (error instanceof HaaApiError) {
    console.error(error.status, error.code);
  }
}
```

`code` preserves HAA's machine-readable failure string such as `UNAUTHORIZED`, `ACTION_DIGEST_MISMATCH`, `CHALLENGE_EXPIRED`, `STALE_APPROVAL` or `REQUEST_NOT_APPROVED:REJECTED`.

Detached verification failures throw `HaaGrantVerificationError` with a bounded verification code such as `INVALID_GRANT_SIGNATURE`, `AUTHORITY_KEY_NOT_ACTIVE`, `GRANT_TTL_EXCEEDS_POLICY`, `GRANT_EXPIRED` or a binding mismatch.

## Compatibility

The SDK consumes `@haa/protocol` v1. W8's two-outcome ceremony contract does not modify frozen approval-bearing v1 schemas. See `docs/PROTOCOL-V1.md` and `docs/W8-CEREMONY-OUTCOMES.md`.
