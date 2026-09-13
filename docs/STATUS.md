# Implementation status

## Functional status

- **W0 Foundation:** DONE
- **W1 Universal core:** DONE
- **W2 Service/enforcement:** DONE
- **W3 Apple authenticator:** DONE and physically validated on a real Apple Silicon Mac with Touch ID / Secure Enclave
- **W4 Agent integration:** DONE; real MCP requester → human Touch ID → bounded executor scenario validated
- **W5 Hardware POC:** DEFERRED by product priority
- **W6 Hardware hardening:** BLOCKED until W5 is deliberately resumed
- **W7-T01..T03 Productization baseline:** DONE
- **W7-T04 WebAuthn spike:** DEFERRED_OPTIONAL
- **W7-T05 Final independent/cross-model security review:** READY_FOR_EXTERNAL_REVIEW
- **W7-T06 Runtime schemas/bounds:** DONE
- **W7-T07 Deterministic dependency/build chain:** DONE
- **W7-T08 Client credential lifecycle/roles:** DONE
- **W7-T09 Authority key ring/rotation:** DONE
- **W7-T10 Network edge production profile:** DONE
- **W7-T11 Audit tamper-evidence:** DONE
- **W7-T12 Authenticator assurance model:** DONE
- **W7-T13 Detached ExecutionGrant verification:** DONE
- **W7-T14 Backup/recovery contract:** DONE
- **W7-T15 Software production-readiness gate:** BLOCKED only by W7-T05
- **W8-T01..T08 Universal ceremony outcomes:** DONE / HAA-ONLY
- **W8-T09 Physical macOS ceremony compatibility gate:** BLOCKED by W7-T15
- **Product integrations:** PARKED

The canonical task/dependency source is `tasks/manifest.yaml`. The active roadmap is `docs/HAA-ACTIVE-ROADMAP.md`.

## Current quality gates

Current `main` validates:

- committed npm lockfile v3;
- `npm ci` in CI and `npm ci --omit=dev` in Docker;
- publishable `@haa/protocol` and `@haa/sdk` package builds / `npm pack --dry-run`;
- TypeScript security/adversarial tests and strict `tsc --noEmit`;
- Docker build/start/health smoke;
- Swift package tests and app-wrapper compilation on macOS CI;
- prior physical Secure Enclave / Touch ID / bounded-executor gate;
- HAA-only automated APPROVE / REJECT / UNKNOWN ceremony matrix;
- request-expiry semantics remain distinct from local UNKNOWN semantics.

## W7 engineering hardening delivered

### Runtime boundary

HTTP input is validated before domain execution using strict, bounded runtime schemas. Request body size, identifiers, strings, JSON depth/key/array counts, action/evidence shapes and unknown fields fail closed.

### Deterministic build chain

`package-lock.json` is committed. CI and Docker resolve the committed dependency graph through `npm ci`. See `docs/BUILD-REPRODUCIBILITY.md`.

### Client identity and credential lifecycle

HAA clients have explicit `REQUESTER`, `APPROVER` and `EXECUTOR` roles. Credentials support expiry, rotation, disable/revoke, non-secret version history and administrative lifecycle audit. API keys are stored only as hashes. See `docs/SELF-HOSTING.md`.

### Authority key lifecycle

The authority uses one ACTIVE signing key and retains RETIRED public keys for historical verification. New signatures use only the ACTIVE key; old challenges/artifacts can still be verified by `authorityKeyId`. Rotation has a CLI and fail-closed recovery rules. See `docs/SELF-HOSTING.md`.

### Network edge

`local` profile requires loopback. `edge` explicitly permits non-loopback binding only behind an operator-controlled TLS/rate-limit/network edge. Forwarded headers are not identity inputs. See `docs/NETWORK-EDGE.md`.

### Tamper-evident audit

Protocol request audit events are protected by a transactional hash chain. Signed `haa.audit-checkpoint.v1` checkpoints anchor the chain against a DBA recomputing hashes after modification. Offline verification is available through `npm run verify:audit`. See `docs/AUDIT-INTEGRITY.md`.

The current cryptographic chain covers `audit_events`; administrative credential lifecycle events remain a separate operational audit stream and are not represented as request-audit checkpoint evidence.

### Authenticator assurance

HAA distinguishes enrollment trust, enrolled-key possession, user verification, device-bound user verification and hardware attestation. Apple Secure Enclave-backed signing is not described as platform attestation because HAA v1 does not prove that property.

### Detached ExecutionGrant verification

The public TypeScript SDK can verify an `ExecutionGrant` received through an untrusted intermediary against ACTIVE/RETIRED authority public keys, exact request/action/execution/audience bindings and expiry. Invalid shape/signature/key/algorithm/binding fails closed.

### Backup and recovery

HAA remains an explicit single-node/single-writer SQLite product. Backup bundles contain a transactional SQLite snapshot, authority private key, authority key ring and a manifest binding file checksums, active key ID and audit head. Backup verification and restore re-check authority/audit consistency. See `docs/BACKUP-RECOVERY.md`.

## Remaining W7 gate

Engineering hardening T06-T14 is complete. W7 cannot be declared production-ready until **W7-T05** receives an actually independent/cross-model review with findings classified as BLOCKING / P1 / P2 / ACCEPTED-RISK and no blocking finding remains.

Only after that review may W7-T15 be changed from `BLOCKED` to `DONE`.

## W8 HAA-only ceremony semantics delivered

W8 is product-independent and does not touch any external repository.

The ceremony contract is:

```text
successful Touch ID   -> APPROVE
Esc                    -> REJECT
window close           -> UNKNOWN
local timeout          -> UNKNOWN
technical interruption -> UNKNOWN
real request TTL       -> EXPIRED
```

### APPROVE

APPROVE preserves the existing strong path: trusted signed display → Touch ID → Secure Enclave-backed evidence → verified `ApprovalEvidence` → `ApprovalReceipt` → bounded `authorizeAndConsume(...)` → `ExecutionGrant`.

Only APPROVE can create execution authority.

### REJECT

REJECT is an explicit refusal and intentionally has weaker assurance than APPROVE. Initial macOS UX uses Escape rather than requiring Touch ID.

A rejection is accepted server-side only when an authenticated `APPROVER` principal matches the configured human, the exact challenge remains active, its HAA signature/bindings verify, and the bound authenticator still belongs to that approver.

The request moves `PENDING -> REJECTED`, the exact challenge is consumed, and the request audit records `USER_ESCAPE` with provenance `authenticated-approver-channel`.

REJECT never produces `ApprovalEvidence`, `ApprovalReceipt` or `ExecutionGrant`. The audit intentionally does not claim biometric or Secure Enclave proof for rejection.

### UNKNOWN

UNKNOWN is a caller/local ceremony outcome, not an `ApprovalState` and not a human decision. Closing the UI, a local timeout or a technical interruption does not create a `REJECTED` audit entry and does not consume execution authority.

If the request TTL is still valid, the request remains `PENDING`. A later ceremony may be attempted.

### EXPIRED

A local timeout is not request expiry. When an active PENDING/APPROVED request crosses its actual TTL at an authorization-sensitive operation boundary, HAA materializes `EXPIRED`, records an `EXPIRED` audit event with `reason=REQUEST_TTL`, and refuses further approval/execution authority.

Challenge expiry alone does not falsely attribute a human decision and does not expire a still-valid request.

### macOS UX

The trusted alert retains one positive button: `Approve with Touch ID`. A discreet `Esc: Reject` instruction provides explicit negative action. Closing the ceremony or local timeout produces UNKNOWN.

The existing positive stdout contract remains `haa.evidence.v1`. REJECT/UNKNOWN are emitted as challenge-bound ceremony-result JSON with distinct exit codes for the approver-side orchestration layer.

### SDK / CLI

`@haa/sdk` exposes `CeremonyResult`, `rejectApproval(...)` and `unknownCeremonyResult(...)`. The CLI exposes `reject` and `unknown` without reinterpreting UNKNOWN as REJECT.

### Audit / E2E

REJECT is represented by the existing `REJECTED` request audit event and participates in W7 tamper-evident audit protection. UNKNOWN remains outside authoritative human-decision audit. Automated HAA-only tests cover positive grant issuance, explicit rejection with no grant, UNKNOWN with PENDING state, request TTL expiry, stale/wrong challenges, replay and rejection forgery attempts.

See:

- `docs/W8-CEREMONY-OUTCOMES.md`
- `docs/W8-NEGATIVE-DECISION-THREAT-MODEL.md`
- `docs/W8-CEREMONY-AUDIT.md`

## Remaining W8 gate

`W8-T09` is deliberately not closed yet. It requires both the completed automated W8 gate and `W7-T15`, then a real provisioned Apple Silicon ceremony validation of:

1. Touch ID -> APPROVE;
2. Esc -> REJECT;
3. window close -> UNKNOWN;
4. timeout/interruption -> UNKNOWN;
5. only APPROVE yields a usable `ExecutionGrant`;
6. existing W3/W4 physical positive-path behavior remains regression-safe.

## Scope boundaries

Hardware remains deliberately deferred. No external product repository is part of the active HAA roadmap, and parked integration notes do not define HAA core dependencies.
