# @haa/sdk

Typed requester/executor client for Human Approval Authority.

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

## Authorize exact execution

```ts
const executionId = crypto.randomUUID();
const grant = await haa.authorize({
  requestId: request.id,
  executionId,
  actualAction: action,
  actualState: { version: 'v42' },
});
```

The executor must treat `ExecutionGrant` as the execution authority. `ApprovalReceipt` is audit evidence and is not a bearer capability.

## Verify a detached ExecutionGrant

When a grant reaches the executor through an untrusted intermediary, verify it locally before treating it as authority:

```ts
import { verifyExecutionGrant } from '@haa/sdk';

const authorityKeys = await haa.getAuthorityKeys();

verifyExecutionGrant({
  grant,
  authorityKeys,
  expectedRequestId: request.id,
  expectedExecutionId: executionId,
  expectedActionDigest: request.actionDigest,
  expectedExecutorAudience: 'executor-prod',
});
```

Detached verification fails closed on:

- unsupported grant schema or signature algorithm;
- unknown `authorityKeyId`;
- key/algorithm mismatch;
- invalid signature or signed-field mutation;
- request, execution, action-digest or executor-audience mismatch;
- expired grant;
- unexpected fields in the frozen `haa.execution-grant.v1` shape.

`getAuthorityKeys()` returns the public authority key ring, including retained `RETIRED` public keys. This allows historical grants to remain cryptographically verifiable after HAA rotates to a new ACTIVE signing key.

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

`code` preserves HAA's machine-readable failure string such as `UNAUTHORIZED`, `ACTION_DIGEST_MISMATCH`, `STALE_APPROVAL` or `REQUEST_NOT_APPROVED:CONSUMED`.

Detached grant failures throw `HaaGrantVerificationError` with a stable verification error code.

## Compatibility

This SDK consumes `@haa/protocol` v1. See the repository's `docs/PROTOCOL-V1.md` for the frozen wire-contract and extension rules.
