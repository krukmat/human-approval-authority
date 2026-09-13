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
- **W7-T05 Final independent/cross-model security review:** AWAITING_EXTERNAL_RERUN after initial FAIL and remediation
- **W7-T06 Runtime schemas/bounds:** DONE
- **W7-T07 Deterministic dependency/build chain:** DONE
- **W7-T08 Client credential lifecycle/roles:** DONE
- **W7-T09 Authority key ring/rotation:** DONE
- **W7-T10 Network edge production profile:** DONE
- **W7-T11 Audit tamper-evidence:** DONE
- **W7-T12 Authenticator assurance model:** DONE
- **W7-T13 Detached ExecutionGrant verification:** DONE, hardened after W7-T05 finding
- **W7-T14 Backup/recovery contract:** DONE
- **W7-T15 Software production-readiness gate:** BLOCKED only by W7-T05 rerun
- **W8-T01..T08 Universal ceremony outcomes:** DONE / HAA-ONLY
- **W8-T09 Physical macOS ceremony compatibility gate:** BLOCKED by W7-T15
- **Product integrations:** PARKED

The canonical task/dependency source is `tasks/manifest.yaml`. The active roadmap is `docs/HAA-ACTIVE-ROADMAP.md`.

The first independent W7-T05 review is recorded in `docs/W7-T05-REVIEW-2026-09-13.md`.

## Current quality gates

Current `main` validates:

- committed npm lockfile v3;
- `npm ci` in CI and `npm ci --omit=dev` in Docker;
- production dependency audit;
- CodeQL JavaScript/TypeScript analysis;
- publishable `@haa/protocol` and `@haa/sdk` package builds / `npm pack --dry-run`;
- TypeScript security/adversarial tests and strict `tsc --noEmit`;
- Docker build/start/health smoke;
- Swift package tests and app-wrapper compilation on macOS CI;
- prior physical Secure Enclave / Touch ID / bounded-executor gate;
- HAA-only automated APPROVE / REJECT terminal ceremony matrix;
- request-TTL `EXPIRED` semantics remain distinct from challenge-level terminal rejection.

## W7 engineering hardening delivered

### Runtime boundary

HTTP input is validated before domain execution using strict, bounded runtime schemas. Request body size, identifiers, strings, JSON depth/key/array counts, action/evidence shapes and unknown fields fail closed.

Built-in `ActionProfile`s also enforce semantic allowlists. Unknown payload/precondition fields are rejected by the core profile boundary, not merely the HTTP layer. Accepted authorization-significant fields are displayed or explicitly constrained by the profile.

### Deterministic build chain

`package-lock.json` is committed. CI and Docker resolve the committed dependency graph through `npm ci`. See `docs/BUILD-REPRODUCIBILITY.md`.

### Client identity and credential lifecycle

HAA clients have explicit `REQUESTER`, `APPROVER` and `EXECUTOR` roles. Credentials support expiry, rotation, disable/revoke, non-secret version history and administrative lifecycle audit. API keys are stored only as hashes. See `docs/SELF-HOSTING.md`.

### Authenticator revocation and outstanding approval authority

An approval receipt remains historical evidence that valid approval occurred, but an unconsumed approval does not survive authenticator revocation. `authorizeAndConsume(...)` re-resolves the receipt's authenticator and requires it to remain `ACTIVE` before minting a new grant.

If the authenticator has been revoked or removed, HAA materializes:

```text
APPROVED -> REVOKED
```

records a `REVOKED` audit event with `reason=AUTHENTICATOR_REVOKED`, and denies execution authority.

Already-consumed execution keeps the existing idempotent retry contract.

### Authority key lifecycle

The authority uses one ACTIVE signing key and retains RETIRED public keys for historical verification. New signatures use only the ACTIVE key; old signed historical artifacts remain attributable by `authorityKeyId`. Rotation has a CLI and fail-closed recovery rules. See `docs/SELF-HOSTING.md`.

For **live detached `ExecutionGrant` verification**, the rule is intentionally stricter:

```text
ACTIVE key  -> eligible for live grant verification
RETIRED key -> historical verification only; never live execution authority
```

The SDK also validates grant timestamp ordering, bounded TTL, future issuance and key-created-at boundaries. This closes W7-T05 finding HAA-REV-001.

### Network edge

`local` profile requires loopback. `edge` explicitly permits non-loopback binding only behind an operator-controlled TLS/rate-limit/network edge. Forwarded headers are not identity inputs.

Development bootstrap is now fail-closed in `edge` mode. `HAA_DEV_BOOTSTRAP=1` with `HAA_NETWORK_PROFILE=edge` refuses startup unless the operator additionally sets the explicitly unsafe `HAA_ALLOW_UNSAFE_DEV_BOOTSTRAP_EDGE=1` override. See `docs/NETWORK-EDGE.md`.

### Tamper-evident audit

Protocol request audit events are protected by a transactional hash chain. Signed `haa.audit-checkpoint.v1` checkpoints anchor the chain against a DBA recomputing hashes after modification. Offline verification is available through `npm run verify:audit`. See `docs/AUDIT-INTEGRITY.md`.

The current cryptographic chain covers `audit_events`; administrative credential lifecycle events remain a separate operational audit stream and are not represented as request-audit checkpoint evidence. The uncheckpointed tail / admin-audit boundary remains an explicitly accepted risk from W7-T05.

### Authenticator assurance

HAA distinguishes enrollment trust, enrolled-key possession, user verification, device-bound user verification and hardware attestation. Apple Secure Enclave-backed signing is not described as platform attestation because HAA v1 does not prove that property. Trusted provisioning and lack of platform attestation remain explicitly accepted W7-T05 risks.

### Detached ExecutionGrant verification

The public TypeScript SDK can verify an `ExecutionGrant` received through an untrusted intermediary against the ACTIVE authority public key, exact request/action/execution/audience bindings, time ordering, bounded TTL and expiry. Invalid shape/signature/key/status/algorithm/time/binding fails closed.

RETIRED authority keys are retained for historical cryptographic verification, not live grant authority.

### Backup and recovery

HAA remains an explicit single-node/single-writer SQLite product. Backup bundles contain a transactional SQLite snapshot, authority private key, authority key ring and a manifest binding file checksums, active key ID and audit head. Backup verification and restore re-check authority/audit consistency. See `docs/BACKUP-RECOVERY.md`.

## W7-T05 independent review state

The first independent Codex review of commit `9bc3f9ec110c141b1a92ef30c9a55948bf77fa79` returned:

```text
BLOCKING      1
P1            1
P2            1
ACCEPTED-RISK 3
verdict       FAIL
```

The implementation has since remediated:

- HAA-REV-001 — retired authority key could mint fresh detached grants;
- HAA-REV-002 — authenticator revocation did not invalidate an APPROVED/unconsumed request;
- HAA-REV-003 — built-in profiles accepted signed-but-undisplayed fields;
- HAA-REV-006 bootstrap portion — predictable dev bootstrap is now rejected in edge profile by default.

HAA-REV-004 and HAA-REV-005 remain explicitly accepted trust-boundary risks. The residual external-ingress portion of HAA-REV-006 remains documented and accepted.

W7-T05 is **not DONE** until an independent reviewer re-checks the remediation delta and returns `BLOCKING = 0`.

Only after that result may W7-T15 be changed from `BLOCKED` to `DONE`.

## W8 HAA-only ceremony semantics delivered

W8 is product-independent and does not touch any external repository.

The terminal ceremony contract is:

```text
successful Touch ID   -> APPROVE
Esc                    -> REJECT / USER_ESCAPE
window close           -> REJECT / WINDOW_CLOSED
local timeout          -> REJECT / TIMEOUT
challenge expiry       -> REJECT / CHALLENGE_EXPIRED
interaction failure    -> REJECT / INTERACTION_ERROR
real request TTL       -> EXPIRED
```

Only APPROVE can create positive authorization evidence and an `ExecutionGrant`. Negative terminal outcomes remain challenge-bound and fail closed, with audit assurance distinguishing explicit `USER_ESCAPE` from non-affirmative terminal failures.

See:

- `docs/W8-CEREMONY-OUTCOMES.md`
- `docs/W8-NEGATIVE-DECISION-THREAT-MODEL.md`
- `docs/W8-CEREMONY-AUDIT.md`

## Remaining W8 gate

`W8-T09` is deliberately not closed yet. It requires W7-T15, then the real provisioned Apple Silicon ceremony matrix defined in `docs/W8-PHYSICAL-CEREMONY-GATE.md`.

## Scope boundaries

Hardware remains deliberately deferred. No external product repository is part of the active HAA roadmap, and parked integration notes do not define HAA core dependencies.
