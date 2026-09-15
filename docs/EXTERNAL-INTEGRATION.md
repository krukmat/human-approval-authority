# External integration contract

Status: **W9-T02 COMPLETE**

This document defines the minimum contract for consuming Human Approval Authority from outside the HAA monorepo.

The integration goal is not "call an approval API". It is:

```text
external requester
    -> exact typed ActionSpec
    -> HAA request/challenge
    -> trusted human ceremony
    -> APPROVE or REJECT
    -> atomic authorizeAndConsume(actualAction, executionId)
    -> short-lived ExecutionGrant
    -> detached verification
    -> external side effect
```

Only the final verified `ExecutionGrant` authorizes execution. `ApprovalReceipt` is audit evidence and must never be treated as a bearer capability.

---

## 1. Public surfaces only

An external consumer may use:

- HAA HTTP API;
- `@haa/protocol`;
- `@haa/sdk`;
- the documented macOS/authenticator ceremony boundary;
- documented self-host/operator provisioning commands.

It must not import private implementation from:

- `packages/core`;
- `packages/persistence-sqlite`;
- `apps/haa-server/src/*`;
- macOS approver source internals.

A need for a private import is an adoption gap, not an invitation to couple the consumer to HAA internals.

---

## 2. Actor and credential separation

Use separate HAA principals/credentials for the three authority roles.

```text
REQUESTER
  creates/observes approval requests
  cannot approve/reject on behalf of the human
  cannot obtain execution authority

APPROVER
  owns the human approval channel/authenticator
  obtains challenge packages
  submits positive ApprovalEvidence or typed REJECT
  must not be the requester principal

EXECUTOR
  reconstructs the actual action/state at execution time
  calls authorizeAndConsume
  verifies the returned ExecutionGrant
  performs the side effect only after verification
```

Do not reuse one API key across these roles in a real integration.

---

## 3. Minimum API contract

The HTTP service exposes the following integration-relevant routes.

| Route | Typical role | Purpose |
| --- | --- | --- |
| `POST /v1/approval-requests` | REQUESTER | Create approval request for one exact action |
| `GET /v1/approval-requests/:id` | authorized participant | Observe lifecycle state |
| `POST /v1/approval-requests/:id/challenges` | APPROVER | Bind request to one enrolled authenticator and create signed challenge |
| `POST /v1/approval-evidence` | APPROVER | Submit positive authenticator evidence and obtain receipt |
| `POST /v1/approval-requests/:id/reject` | APPROVER | Submit typed terminal REJECT for the exact challenge |
| `POST /v1/approval-requests/:id/authorize` | EXECUTOR | Atomically authorize/consume against actual action/state and obtain `ExecutionGrant` |
| `GET /v1/authority-keys` | verifier | Obtain authority verification metadata |
| `GET /v1/approval-requests/:id/audit` | authorized participant | Retrieve request audit history |

All authenticated calls use `x-api-key`. Production network exposure must follow the documented edge/TLS boundary rather than treating the API key as a substitute for transport security.

---

## 4. Requester flow

The requester constructs one typed `ActionSpec` and submits it to HAA.

```ts
import { HaaClient, type ActionSpec } from '@haa/sdk';

const requester = new HaaClient(
  process.env.HAA_BASE_URL!,
  process.env.HAA_REQUESTER_API_KEY!,
);

const action: ActionSpec = {
  schema: 'haa.action.v1',
  type: 'demo.action.v1', // W9 smoke only; replace with the real profile in W9-T04
  payload: {
    resource: 'external-consumer',
    operation: 'change',
  },
  preconditions: {
    version: 'v17',
  },
};

const request = await requester.requestApproval({
  action,
  approverPrincipalId: 'human-prod',
  executorAudience: 'external-executor-prod',
  ttlMs: 10 * 60_000,
});
```

The requester may present/request status, but must not execute because the request becomes `APPROVED`. Approval state is not execution authority.

### Requester requirements

- The action must use a supported, typed/versioned ActionProfile.
- Fields with authorization meaning must not be hidden in arbitrary opaque payloads.
- `executorAudience` must identify the intended executor boundary.
- Requester and approver principal must remain distinct.
- The requester must not invent the executor's later `actualState`.

---

## 5. Human ceremony

The approver side obtains the signed HAA challenge for the enrolled authenticator and performs the trusted ceremony.

Positive path:

```text
signed challenge
  -> trusted display of exact action claims
  -> positive human verification
  -> authenticator signs challenge digest
  -> haa.evidence.v1
  -> HAA verifies evidence
  -> ApprovalReceipt
```

Negative terminal path:

```text
Esc                 -> REJECT / USER_ESCAPE
window close / ⌘W   -> REJECT / WINDOW_CLOSED
local timeout       -> REJECT / TIMEOUT
challenge expiry    -> REJECT / CHALLENGE_EXPIRED
interaction failure -> REJECT / INTERACTION_ERROR
```

Only `USER_ESCAPE` means explicit negative human action. The other reasons are fail-closed terminal outcomes.

The external requester does not forge or synthesize these outcomes. Trusted rejection is submitted through the authenticated approver channel and is challenge-bound.

---

## 6. Executor flow

The executor must re-read the real target state immediately before authorization, reconstruct the action it is about to perform and use a fresh execution ID.

```ts
import {
  HaaClient,
  verifyExecutionGrant,
  type ActionSpec,
} from '@haa/sdk';
import crypto from 'node:crypto';

const executor = new HaaClient(
  process.env.HAA_BASE_URL!,
  process.env.HAA_EXECUTOR_API_KEY!,
);

const actualAction: ActionSpec = action; // reconstruct from the real pending operation
const actualState = { version: await readCurrentVersionFromSourceOfTruth() };
const executionId = crypto.randomUUID();

const grant = await executor.authorize({
  requestId: request.id,
  executionId,
  actualAction,
  actualState,
});

const authorityKeys = await executor.getAuthorityKeys();

verifyExecutionGrant({
  grant,
  authorityKeys,
  expectedRequestId: request.id,
  expectedExecutionId: executionId,
  expectedActionDigest: request.actionDigest,
  expectedExecutorAudience: 'external-executor-prod',
});

await applySideEffectExactlyOnce();
```

### Executor requirements

The executor must fail closed unless all of the following remain true:

- request ID matches;
- execution ID matches when locally bound;
- action digest matches the approved exact action;
- executor audience matches the local executor identity/policy;
- authority key is trusted and currently `ACTIVE` for live execution authority;
- grant signature is valid;
- grant issuance/expiry/TTL policy is valid;
- actual preconditions still match the executor-observed source of truth.

The side effect must happen only after `authorize(...)` succeeds and detached verification succeeds.

---

## 7. Idempotency and crash boundary

HAA guarantees authority consumption semantics, not arbitrary external side-effect transactions.

For a consumed request:

```text
same executionId      -> original grant can be returned idempotently
different executionId -> denied
```

The external executor must therefore persist or derive its execution ID consistently across retry/recovery and make the side effect itself idempotent where possible.

A recommended executor sequence is:

```text
1. resolve durable operation/executionId
2. read source-of-truth state
3. call HAA authorizeAndConsume
4. verify detached grant
5. execute side effect idempotently
6. persist completion marker
```

Do not generate a new execution ID after an ambiguous network failure unless the integration can prove the previous authorization did not consume the request.

---

## 8. Trust boundary for authority keys

`verifyExecutionGrant(...)` treats authority-key metadata as trusted verifier policy input.

Acceptable sources:

- authenticated/TLS-protected HAA `/v1/authority-keys` endpoint;
- operator-pinned authority-key configuration.

Do not accept authority-key status metadata from the same untrusted intermediary that delivered the grant and then use that metadata to validate the grant.

RETIRED keys may remain useful for historical artifact verification, but a live detached `ExecutionGrant` must verify against the current `ACTIVE` key.

---

## 9. Fail-closed outcomes the consumer must handle

A real integration must treat at least these as expected control-flow outcomes, not reasons to bypass HAA:

```text
PENDING / waiting for human
REJECTED
EXPIRED
ACTION_DIGEST_MISMATCH
EXECUTOR_AUDIENCE_MISMATCH
STALE_APPROVAL
REQUEST_NOT_APPROVED:REJECTED
REQUEST_NOT_APPROVED:CONSUMED
GRANT_EXPIRED
AUTHORITY_KEY_NOT_ACTIVE
INVALID_GRANT_SIGNATURE
```

Any fallback path that performs the side effect after one of these failures violates the HAA trust model.

---

## 10. W9 reference-integration acceptance

The first external consumer must prove, from outside this repository:

```text
REQUESTER creates exact action request
APPROVER performs real HAA ceremony
REJECT produces no receipt/grant/execution
APPROVE produces verified evidence/receipt
EXECUTOR re-checks actual state
EXECUTOR obtains one exact ExecutionGrant
EXECUTOR verifies grant through public SDK
side effect occurs only after grant verification
same executionId is safe to retry
different executionId after consume is denied
mutated action is denied
stale precondition is denied
wrong executor audience is denied
no private HAA source import is required
```

W9-T03 may initially use `demo.action.v1` only to prove the external package/API boundary. W9-T04 must replace that smoke profile with a real ActionProfile whose authorization-relevant fields are typed, allow-listed, digest-bound and fully represented in the trusted display.
