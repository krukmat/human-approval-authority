# HAA integration release baseline

Status: **FROZEN FOR W9 ADOPTION**

## Identity

```text
Product baseline:      HAA 0.1.0
Protocol package:      @haa/protocol 1.0.0
SDK package:           @haa/sdk 0.2.0
Immutable code SHA:    e68b6ad8b8b3901f095e47111aa5545c132cf964
Physical gate SHA:     1bec7bb76f0bb7119045bea6d59ed896364e2895
W7 accepted code SHA:  7720ac04e5b35637dcc56952925af15386cdc226
```

The immutable W9 starting point is the code at `e68b6ad8b8b3901f095e47111aa5545c132cf964`. Later documentation commits do not redefine the frozen code baseline.

## Why this SHA

The W8 physical ceremony gate was executed on `1bec7bb76f0bb7119045bea6d59ed896364e2895`. Subsequent commits closed W8 documentation/status only. A later local Xcode save introduced a machine-specific `DEVELOPMENT_TEAM` value; that value was removed before freezing W9 and the Xcode project was restored to the signing-neutral file used at the physical gate.

A compare from the physical SHA to the frozen integration SHA therefore contains only closure/document-control files. No HAA runtime, protocol, SDK, server, persistence, authenticator source or execution semantics changed after the physical validation.

## Frozen compatibility contract

W9 integrations must preserve:

- protocol schema/version `v1` semantics;
- `ApprovalReceipt` as audit evidence only;
- `ExecutionGrant` as the only execution authority artifact;
- exact canonical action digest binding;
- authenticated REQUESTER / APPROVER / EXECUTOR separation;
- requester and approver principal separation;
- executor-audience binding;
- precondition validation against executor-observed state;
- atomic one-shot `authorizeAndConsume(...)`;
- same-`executionId` idempotent grant retrieval and different-`executionId` denial after consumption;
- ACTIVE authority key requirement for live detached grant verification;
- APPROVE as the only positive authority-producing ceremony result;
- all terminal non-approval ceremony results as typed REJECT outcomes;
- request TTL `EXPIRED` remaining distinct from ceremony `REJECTED / CHALLENGE_EXPIRED`.

## External adoption rule

A W9 consumer may depend only on public HAA surfaces:

```text
HTTP API
@haa/protocol
@haa/sdk
published/documented authenticator ceremony contract
```

It must not import or copy implementation from:

```text
packages/core
packages/persistence-sqlite
apps/haa-server internals
macOS approver internals
```

If a real consumer cannot integrate without a private import or core workaround, that is a W9 adoption gap and must be classified before changing HAA.

## Reproduction gates

Before accepting an integration-sensitive HAA change, preserve at minimum:

```bash
npm ci
npm run pack:check
npm test
npx tsc --noEmit
```

Deployment-sensitive changes also require Docker build/start/health. macOS authenticator/ceremony changes require the relevant Swift/Xcode and physical gate according to scope.

## Release object / tag

The repository SHA is the canonical immutable baseline for W9. A GitHub release/tag can be added later as distribution metadata, but it must point to this exact baseline or to a documentation-only descendant explicitly mapped back to it; it must not silently redefine the accepted code.
