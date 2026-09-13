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

HAA distinguishes three caller-visible ceremony outcomes:

```text
APPROVE  verified positive authenticator evidence
REJECT   explicit authenticated refusal
UNKNOWN  no attributable human decision
```

Only APPROVE can eventually produce an `ExecutionGrant`.

An approver-side client may submit the explicit Esc rejection for the exact active challenge:

```ts
const result = await approverClient.rejectApproval({
  requestId: request.id,
  challengeDigest,
  reason: 'USER_ESCAPE',
});

// { outcome: 'REJECT', state: 'REJECTED', ... }
```

`rejectApproval` must be called with the configured approver principal's `APPROVER` credential. A requester/executor credential cannot use the endpoint merely because it knows the request ID or challenge digest.

Window close, local timeout, app termination or similar indeterminate outcomes are local results and do not assert a server-side human decision:

```ts
import { unknownCeremonyResult } from '@haa/sdk';

const result = unknownCeremonyResult(request.id, 'LOCAL_TIMEOUT');
// { outcome: 'UNKNOWN', requestId: ..., reason: 'LOCAL_TIMEOUT' }
```

If the underlying request is still valid, UNKNOWN leaves it `PENDING`. Actual lifecycle expiry remains `EXPIRED`, not `REJECTED` or UNKNOWN.

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

The verifier checks strict object shape, the retained HAA authority key, signature algorithm/signature, expiry and exact request/action/execution/audience bindings. ACTIVE and RETIRED authority public keys may verify artifacts that were legitimately signed while that key was active.

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

Detached verification failures throw `HaaGrantVerificationError` with a bounded verification code such as `INVALID_GRANT_SIGNATURE`, `UNKNOWN_AUTHORITY_KEY`, `GRANT_EXPIRED` or a binding mismatch.

## Compatibility

This SDK consumes `@haa/protocol` v1. W8 ceremony outcomes do not add `UNKNOWN` to `ApprovalState` and do not mutate frozen approval-bearing v1 schemas. See `docs/PROTOCOL-V1.md` and `docs/W8-CEREMONY-OUTCOMES.md`.
