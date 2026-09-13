# W7-T15 software production-readiness gate

Status: **PASS / DONE**

This checklist is the closure contract for W7-T15. It is HAA-only and deliberately does not depend on DubBridge, hardware, WebAuthn or any product integration.

## Gate identity

```text
Accepted code SHA: 7720ac04e5b35637dcc56952925af15386cdc226
W7-T05 independent rerun SHA: 7d3f7126f67e660147f7e0a9967c07deafa1564b
W7-T05 verdict: PASS_WITH_FOLLOWUPS
Readiness date: 2026-09-13
Reviewer: Codex (GPT-5), OpenAI Codex
Closure: HAA roadmap owner / automated gates
```

The accepted code SHA differs from the independent rerun SHA only by the bounded post-review P2 follow-up `HAA-REV-007` and its packaging-boundary correction:

- reject non-finite verifier clocks with `INVALID_VERIFICATION_TIME`;
- regression coverage for `new Date('invalid')`;
- preserve the public SDK boundary through `@haa/protocol` and SDK-local canonicalization.

This delta is narrow, non-architectural, covered by regression tests and the full automated gate. It does not alter signed protocol-v1 schemas or authority boundaries.

## G1 — Build / package / test chain

Required and passed on the accepted code SHA:

```bash
npm ci
npm run pack:check
npm test
npx tsc --noEmit
npm audit --omit=dev --audit-level=high
```

Evidence:

- deterministic committed lockfile;
- protocol/SDK packages build and dry-pack;
- TypeScript security/adversarial suite passes;
- strict type-check passes;
- no known high/critical production dependency advisory at gate time.

Result: `PASS`

## G2 — Container / self-host baseline

CI container build/start/health smoke passed on the accepted code SHA. Development bootstrap in `edge` mode requires the explicit unsafe override used only by the CI smoke; production edge bootstrap fails closed by default.

Result: `PASS`

## G3 — Client credential lifecycle

Evidence proves:

- role separation REQUESTER / APPROVER / EXECUTOR;
- API keys persisted only as hashes;
- expiry enforced;
- rotation invalidates old credential;
- disable/revoke works without deleting identity history;
- lifecycle actions are operationally auditable.

Result: `PASS`

## G4 — Authority key lifecycle

Evidence proves:

- exactly one ACTIVE signing key;
- RETIRED public keys remain usable for legitimate historical verification;
- new signatures use only ACTIVE key;
- live detached `ExecutionGrant` verification accepts only ACTIVE key status;
- unknown/mismatched algorithms fail closed;
- challenge issued before rotation remains verifiable under retained historical-key policy;
- rotation/recovery behavior is documented.

Result: `PASS`

## G5 — Audit integrity

Evidence proves deterministic hash chaining, mutation/removal/reordering detection, signed checkpoints and offline verification. The documented residual boundary remains that an uncheckpointed tail and the separate administrative audit stream are not protected to the same external-anchor level.

Result: `PASS / ACCEPTED-RISK HAA-REV-004`

## G6 — Backup / restore

Evidence proves transactional SQLite snapshot, authority-key/key-ring consistency, checksums, active-key binding, audit-head verification, tampered-bundle rejection and guarded restore behavior.

Result: `PASS`

## G7 — Detached execution grant verification

Evidence proves strict verification of:

- schema/shape;
- ACTIVE authority key ID/status and algorithm;
- authority signature;
- request ID;
- optional exact execution ID;
- action digest;
- executor audience;
- valid verification clock;
- issuedAt/expiresAt ordering;
- future issuance and key-created-at boundaries;
- maximum TTL policy;
- expiry;
- unknown key and extra-field fail-closed behavior.

Result: `PASS`

## G8 — Authenticator assurance

Documentation and code distinguish:

```text
authenticated enrollment
enrolled-key possession
user verification
device-bound user verification
hardware/platform attestation
```

HAA v1 does not claim Apple platform attestation. Trusted provisioning/enrollment remains an explicit administrative boundary.

Result: `PASS / ACCEPTED-RISK HAA-REV-005`

## G9 — W8 ceremony authority boundary

Automated evidence proves:

```text
successful positive evidence -> APPROVE -> receipt/grant possible
USER_ESCAPE                  -> REJECTED -> no receipt/grant
WINDOW_CLOSED                -> REJECTED -> no receipt/grant
TIMEOUT                      -> REJECTED -> no receipt/grant
CHALLENGE_EXPIRED            -> REJECTED -> no receipt/grant
INTERACTION_ERROR            -> REJECTED -> no receipt/grant
request TTL                  -> EXPIRED  -> no receipt/grant
```

Reason/assurance prevents close/timeout/error from being described as biometric or explicit human rejection.

Result: `PASS`

## G10 — Independent review

Independent Codex/GPT-5 rerun result:

```text
Remaining BLOCKING findings: 0
Remaining P1 findings:       0
New BLOCKING findings:       0
New P1 findings:             0
W7-T05 verdict:              PASS_WITH_FOLLOWUPS
W7-T15 recommendation:       PROCEED
```

The only new rerun finding, `HAA-REV-007` (`P2` invalid verifier clock), was remediated and regression-tested before this gate was closed.

Result: `PASS`

## Automated closure evidence

Accepted code SHA `7720ac04e5b35637dcc56952925af15386cdc226` passed:

```text
npm ci / production audit       PASS
package build / pack:check      PASS
npm test                        PASS
strict TypeScript               PASS
Docker build + health smoke     PASS
Swift package tests             PASS
Xcode approver wrapper compile  PASS
CodeQL JavaScript/TypeScript    PASS
```

## Residual accepted risks

- `HAA-REV-004`: signed audit checkpoints anchor only checkpointed history; administrative audit is a separate stream.
- `HAA-REV-005`: trusted provisioning/enrollment and no platform-attestation claim.
- `HAA-REV-006`: edge deployments depend on operator-controlled TLS, ACLs, rate limiting and secret isolation; unsafe development bootstrap requires an explicit override.

These are documented trust/deployment boundaries, not hidden execution-authority bypasses.

## Final closure statement

```text
W7-T15: PASS
Accepted code SHA: 7720ac04e5b35637dcc56952925af15386cdc226
Independent review: PASS_WITH_FOLLOWUPS, BLOCKING=0, P1=0
CI/package/Docker: PASS
CodeQL: PASS
Credential lifecycle: PASS
Authority rotation: PASS
Audit integrity: PASS with documented residual boundary
Backup/restore: PASS
Detached grants: PASS
Authenticator assurance: PASS with documented trust boundary
W8 automated authority boundary: PASS
```

W7 software production hardening is closed. The next active HAA-only gate is W8-T09, the physical macOS ceremony/compatibility validation.
