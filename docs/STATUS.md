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
- **W7-T05 Final independent/cross-model security review:** DONE — PASS_WITH_FOLLOWUPS, BLOCKING=0, P1=0
- **W7-T06 Runtime schemas/bounds:** DONE
- **W7-T07 Deterministic dependency/build chain:** DONE
- **W7-T08 Client credential lifecycle/roles:** DONE
- **W7-T09 Authority key ring/rotation:** DONE
- **W7-T10 Network edge production profile:** DONE
- **W7-T11 Audit tamper-evidence:** DONE
- **W7-T12 Authenticator assurance model:** DONE
- **W7-T13 Detached ExecutionGrant verification:** DONE, hardened after W7-T05 finding
- **W7-T14 Backup/recovery contract:** DONE
- **W7-T15 Software production-readiness gate:** DONE — accepted code SHA `7720ac04e5b35637dcc56952925af15386cdc226`
- **W8-T01..T08 Universal ceremony outcomes:** DONE / HAA-ONLY
- **W8-T09 Physical macOS ceremony compatibility gate:** DONE — validated SHA `1bec7bb76f0bb7119045bea6d59ed896364e2895`
- **HAA-only software/ceremony phase:** CLOSED
- **Product integrations:** PARKED

The canonical task/dependency source is `tasks/manifest.yaml`. The roadmap is `docs/HAA-ACTIVE-ROADMAP.md`.

The independent W7-T05 review and rerun are recorded in `docs/W7-T05-REVIEW-2026-09-13.md`; W7-T15 closure evidence is in `docs/W7-PRODUCTION-READINESS.md`; W8-T09 physical closure evidence and operator-confirmed final rerun are recorded in `docs/W8-PHYSICAL-CEREMONY-GATE.md`.

## Current quality gates

The accepted HAA-only baseline validates:

- committed npm lockfile v3;
- `npm ci` in CI and `npm ci --omit=dev` in Docker;
- publishable `@haa/protocol` and `@haa/sdk` package builds / `npm pack --dry-run`;
- TypeScript security/adversarial tests and strict `tsc --noEmit`;
- Docker build/start/health smoke;
- Swift package tests and app-wrapper compilation on macOS CI;
- CodeQL JavaScript/TypeScript analysis;
- physical Secure Enclave / Touch ID approval path;
- real MCP requester → human Touch ID → bounded executor path;
- HAA-only automated APPROVE / REJECT terminal ceremony matrix;
- physical APPROVE / Esc / window-close / timeout / challenge-expiry ceremony validation;
- request-TTL `EXPIRED` semantics remain distinct from challenge-level terminal rejection;
- only positive verified approval can produce an `ExecutionGrant`.

## W7 engineering hardening delivered

### Runtime boundary

HTTP input is validated before domain execution using strict, bounded runtime schemas. Request body size, identifiers, strings, JSON depth/key/array counts, action/evidence shapes and unknown fields fail closed.

### Deterministic build chain

`package-lock.json` is committed. CI and Docker resolve the committed dependency graph through `npm ci`. See `docs/BUILD-REPRODUCIBILITY.md`.

### Client identity and credential lifecycle

HAA clients have explicit `REQUESTER`, `APPROVER` and `EXECUTOR` roles. Credentials support expiry, rotation, disable/revoke, non-secret version history and administrative lifecycle audit. API keys are stored only as hashes. See `docs/SELF-HOSTING.md`.

### Authority key lifecycle

The authority uses one ACTIVE signing key and retains RETIRED public keys for historical verification. New signatures use only the ACTIVE key; old challenges/artifacts can still be verified by `authorityKeyId`. Live detached `ExecutionGrant` verification requires an ACTIVE key. Rotation has a CLI and fail-closed recovery rules. See `docs/SELF-HOSTING.md`.

### Network edge

`local` profile requires loopback. `edge` explicitly permits non-loopback binding only behind an operator-controlled TLS/rate-limit/network edge. Forwarded headers are not identity inputs. Development bootstrap is refused in edge mode unless an explicit unsafe override is supplied. See `docs/NETWORK-EDGE.md`.

### Tamper-evident audit

Protocol request audit events are protected by a transactional hash chain. Signed `haa.audit-checkpoint.v1` checkpoints anchor the chain against a DBA recomputing hashes after modification. Offline verification is available through `npm run verify:audit`. See `docs/AUDIT-INTEGRITY.md`.

The current cryptographic chain covers `audit_events`; administrative credential lifecycle events remain a separate operational audit stream and are not represented as request-audit checkpoint evidence.

### Authenticator assurance

HAA distinguishes enrollment trust, enrolled-key possession, user verification, device-bound user verification and hardware attestation. Apple Secure Enclave-backed signing is not described as platform attestation because HAA v1 does not prove that property.

### Detached ExecutionGrant verification

The public TypeScript SDK verifies an `ExecutionGrant` received through an untrusted intermediary against trusted ACTIVE authority public-key metadata, exact request/action/execution/audience bindings, strict time policy and expiry. Invalid shape/signature/key/algorithm/binding/time fails closed. The post-review follow-up rejects an invalid local verification clock with `INVALID_VERIFICATION_TIME`.

### Backup and recovery

HAA remains an explicit single-node/single-writer SQLite product. Backup bundles contain a transactional SQLite snapshot, authority private key, authority key ring and a manifest binding file checksums, active key ID and audit head. Backup verification and restore re-check authority/audit consistency. See `docs/BACKUP-RECOVERY.md`.

## W7 independent review outcome

The independent Codex/GPT-5 rerun reported:

```text
Remaining BLOCKING findings: 0
Remaining P1 findings:       0
New BLOCKING findings:       0
New P1 findings:             0
W7-T05 verdict:              PASS_WITH_FOLLOWUPS
W7-T15 recommendation:       PROCEED
```

The rerun's only new finding was P2 `HAA-REV-007` (invalid verifier `Date` could yield `NaN`). It was remediated with fail-closed `INVALID_VERIFICATION_TIME` handling and regression coverage. During that follow-up an accidental private source-path import temporarily broke SDK packaging; CI detected it, the publishable `@haa/protocol` boundary was restored, and the corrected accepted SHA passed pack, tests, strict TypeScript, Docker, Swift/Xcode and CodeQL gates.

W7-T15 is closed. Residual risks remain the explicitly documented audit-checkpoint boundary, trusted provisioning/no platform-attestation boundary, and operator-managed edge controls.

## W8 HAA-only ceremony semantics delivered

W8 is product-independent and does not touch any external repository.

The terminal ceremony contract is:

```text
successful Touch ID   -> APPROVE
Esc                    -> REJECT / USER_ESCAPE
window close / ⌘W     -> REJECT / WINDOW_CLOSED
local timeout          -> REJECT / TIMEOUT
challenge expiry       -> REJECT / CHALLENGE_EXPIRED
interaction failure    -> REJECT / INTERACTION_ERROR
real request TTL       -> EXPIRED
```

### APPROVE

APPROVE preserves the existing strong path: trusted signed display → Touch ID → Secure Enclave-backed evidence → verified `ApprovalEvidence` → `ApprovalReceipt` → bounded `authorizeAndConsume(...)` → `ExecutionGrant`.

Only APPROVE can create execution authority.

### REJECT

Every non-approved terminal ceremony is REJECT and transitions the still-valid request `PENDING -> REJECTED` through the authenticated approver channel.

All rejects are challenge-bound, consume that challenge, and produce no `ApprovalEvidence`, `ApprovalReceipt` or `ExecutionGrant`.

The audit deliberately distinguishes assurance:

```text
USER_ESCAPE
  assurance=explicit-human-negative-action

WINDOW_CLOSED / TIMEOUT / CHALLENGE_EXPIRED / INTERACTION_ERROR
  assurance=fail-closed-terminal
```

Therefore operational REJECT does not imply that a human explicitly chose Reject unless the reason is `USER_ESCAPE`; none of the negative paths claim Touch ID or biometric proof.

### EXPIRED

Request TTL remains a separate lifecycle condition. When an active PENDING/APPROVED request crosses its actual TTL at an authorization-sensitive operation boundary, HAA materializes `EXPIRED`, records an `EXPIRED` audit event with `reason=REQUEST_TTL`, and refuses further approval/execution authority.

Challenge expiry can instead terminate a still-valid ceremony as `REJECTED / CHALLENGE_EXPIRED`.

### macOS UX

The trusted alert retains one positive button: `Approve with Touch ID`. `Esc` provides explicit negative action and `⌘W` provides a deterministic window-close gesture even when `NSAlert` does not expose a reliable close control. Local timeout, challenge expiry or terminal interaction failure emit challenge-bound REJECT results with typed reasons.

The existing positive stdout contract remains `haa.evidence.v1`. Terminal rejection output uses a distinct non-zero exit path and never emits positive evidence.

### SDK / CLI

`@haa/sdk` exposes the two-outcome `CeremonyOutcome`, typed `RejectionReason`, `RejectionRecord` and `rejectApproval(...)`. The CLI exposes `reject` with an optional typed reason. There is no third terminal `UNKNOWN` outcome.

### Audit / E2E

REJECT uses the existing `REJECTED` request state/audit event and participates in W7 tamper-evident audit protection. Automated HAA-only tests cover positive grant issuance; Escape, close, timeout and interaction-error rejection; challenge-expiry reason validation; request TTL expiry; replay; wrong challenge; and rejection forgery attempts.

See:

- `docs/W8-CEREMONY-OUTCOMES.md`
- `docs/W8-NEGATIVE-DECISION-THREAT-MODEL.md`
- `docs/W8-CEREMONY-AUDIT.md`
- `docs/W8-PHYSICAL-CEREMONY-GATE.md`

## W8 physical gate outcome

`W8-T09` is DONE on validated SHA `1bec7bb76f0bb7119045bea6d59ed896364e2895`.

Physical validation confirms:

1. Touch ID -> APPROVE -> verified evidence / receipt / usable exact `ExecutionGrant`;
2. Esc -> REJECT / USER_ESCAPE -> no grant;
3. `⌘W` / window close -> REJECT / WINDOW_CLOSED -> no grant;
4. timeout -> REJECT / TIMEOUT -> no grant;
5. challenge expiry -> REJECT / CHALLENGE_EXPIRED -> no grant;
6. interaction-error remains physical N/A where forcing it would weaken/disturb the local trust environment; automated coverage remains green;
7. only APPROVE yields execution authority;
8. W3/W4 physical positive-path behavior remains regression-safe.

The first aggregate physical log had operator-input mismatches for Escape versus window-close and ended while waiting for challenge expiry. The affected rows were rerun after the macOS UX was made deterministic, and the operator confirmed the final rerun succeeded. The closure record explicitly relies on that operator-confirmed final rerun rather than treating the earlier incomplete aggregate log as final evidence.

## Scope boundaries

The HAA-only software/ceremony phase is closed. Hardware remains deliberately deferred. No external product repository is part of the completed HAA core baseline, and parked integration notes do not define HAA core dependencies. Any future DubBridge/product integration or hardware work requires deliberate reprioritization.
