# HAA Protocol v1 compatibility contract

Status: **FROZEN**

Wire protocol: **1**
Package release: **1.0.0**
Freeze date: **2026-09-13**

This document defines the compatibility boundary that downstream integrations may rely on. Product releases may remain pre-1.0 while the wire contract itself is frozen as v1.

## Frozen v1 schemas

The following schema identifiers and their current field semantics are frozen:

- `haa.action.v1`
- `haa.intent.v1`
- `haa.request.v1`
- `haa.challenge-payload.v1`
- `haa.challenge.v1`
- `haa.evidence.v1`
- `haa.verified-evidence.v1`
- `haa.receipt.v1`
- `haa.execution-grant.v1`
- `haa.authenticator.v1`
- `haa.audit.v1`

`haa.challenge-payload.v1.protocolVersion` is exactly `1`.

## Signed-object rule

HAA deliberately uses exact canonical bytes/digests for authorization. Therefore compatibility rules are stricter than ordinary JSON APIs.

For these authorization-bearing structures, adding/removing/renaming a field or changing its meaning is **breaking** and requires a new schema version:

- ActionSpec when the action digest changes semantically;
- ApprovalIntent;
- ApprovalChallengePayload / ApprovalChallengePackage;
- ApprovalEvidence;
- ApprovalReceipt;
- ExecutionGrant.

Do not add an "optional" field to a signed v1 structure merely because JSON decoders could ignore it. A new authorization-significant field must use a new schema/profile version so old participants cannot silently interpret a different action.

## Compatible extensions

The following are compatible with protocol v1 when they preserve the frozen primitives:

- new typed ActionProfiles, e.g. `deployment.execute.v1` or a future `dubbridge.ai-execution.v1`;
- new authenticator/evidence `type` values with a verifier adapter;
- new requester/executor adapters;
- new HTTP endpoints that do not alter existing endpoint semantics;
- new audit information placed under the existing `details` extension object;
- implementation/internal persistence changes invisible on the wire.

Unknown ActionProfiles, evidence types, signature algorithms or protocol versions must fail closed.

## Incompatible changes

These require a new schema/protocol generation and an explicit migration strategy:

- weakening exact-action binding;
- changing digest/canonicalization semantics;
- changing the meaning of requester, approver or executor audience binding;
- allowing ApprovalReceipt to act as execution authority;
- changing single-consumption/idempotency semantics;
- changing challenge freshness/nonce binding semantics;
- adding authorization-significant fields to a frozen signed v1 object;
- interpreting unknown profile/evidence data permissively.

## ActionProfile versioning

ActionProfiles are the primary product-extension mechanism.

Rules:

1. Profile names are immutable once used in an approval, e.g. `git.merge.v1`.
2. A semantic change to canonical fields, display claims or precondition rules creates a new profile version (`v2`), never an in-place reinterpretation.
3. Executors must validate the same profile version that was approved.
4. Unsupported profile versions fail closed.

This lets HAA add product integrations without coupling their semantics to the universal core.

## Package/API versioning

- `@haa/protocol` starts at `1.0.0` to represent the frozen v1 type contract.
- SDK/server packages may evolve independently under semantic versioning.
- Wire compatibility is determined by the `schema` / `protocolVersion` values, not only by npm package versions.
- A package major version change does not automatically imply a wire-protocol change, and vice versa; release notes must state both explicitly.

## Downgrade and mixed-version behavior

- HAA must never downgrade a challenge or signed object automatically.
- A participant that does not understand a schema/profile/version must reject it.
- Mixed-version deployments are supported only when every authorization-bearing object used by a transaction is understood by all participants in that transaction.

## Integration boundary

Future integrations such as DubBridge must live above this contract:

```text
Product workflow
   ↓
typed ActionProfile + requester adapter
   ↓
HAA protocol v1
   ↓
human authenticator
   ↓
ExecutionGrant
   ↓
bounded product executor
```

A product integration must not introduce product-specific branches into HAA's universal approval lifecycle, receipt semantics or execution-grant semantics.
