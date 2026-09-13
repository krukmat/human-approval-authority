# W7-T05 independent security / architecture review packet

Status: **READY_FOR EXTERNAL / CROSS-MODEL REVIEW**

This packet is the canonical handoff for W7-T05. It is intentionally self-contained and HAA-only. DubBridge, hardware, WebAuthn and product-specific adapters are outside this review.

## Independence requirement

W7-T05 is not satisfied by the model/agent that implemented the reviewed code reviewing its own work.

The reviewer must record:

```text
Reviewer / model:
Provider / runtime:
Review date:
Reviewed commit SHA:
Independence statement: I did not implement the reviewed change set in this review session.
```

A human may coordinate the review, but findings must come from an independent reviewer/model/tooling pass.

## Freeze the review target

Before reviewing:

```bash
git checkout main
git pull --ff-only
git rev-parse HEAD
git status --short
```

Record the exact SHA. Findings and acceptance apply to that SHA. If security-relevant code changes afterward, either review the delta explicitly or repeat the review.

## Product claim to challenge

HAA answers:

> Is there a valid, verifiable and still-usable human authorization for exactly this action?

The reviewer should attempt to falsify these invariants:

1. agents/requesters cannot self-approve;
2. approval is bound to exact canonical typed action intent;
3. displayed claims come from the signed challenge bytes;
4. positive authority requires verified authenticator evidence;
5. receipt is audit evidence, not a bearer execution capability;
6. only `authorizeAndConsume(...)` may produce an `ExecutionGrant`;
7. execution is exact-action, exact-audience, precondition-bound and one-shot/idempotent;
8. stale/foreign/replayed evidence fails closed;
9. authority/authenticator/client key lifecycles do not silently downgrade trust;
10. audit mutation/reordering/removal is detectable relative to a trusted signed checkpoint;
11. backup/restore preserves authority-key/database/audit consistency;
12. edge deployment assumptions are explicit rather than implied security;
13. protocol-v1 signed schemas remain frozen and fail closed on unsupported variants;
14. W8 negative ceremony paths can deny authority but never create it;
15. W8 audit does not overclaim human intent: only `USER_ESCAPE` is explicit-human-negative-action; close/timeout/challenge-expiry/interaction-error are fail-closed terminal outcomes.

## Required review surface

Read at minimum:

```text
AGENTS.md
README.md
docs/ARCHITECTURE.md
docs/SECURITY.md
docs/SECURITY-REVIEW-V1.md
docs/PROTOCOL-V1.md
docs/AUTHENTICATOR-ASSURANCE.md
docs/AUDIT-INTEGRITY.md
docs/BACKUP-RECOVERY.md
docs/NETWORK-EDGE.md
docs/W8-CEREMONY-OUTCOMES.md
docs/W8-NEGATIVE-DECISION-THREAT-MODEL.md
docs/W8-CEREMONY-AUDIT.md

packages/protocol/src/index.ts
packages/core/src/index.ts
packages/persistence-sqlite/src/index.ts
packages/sdk-ts/src/index.ts
apps/haa-server/src/application.ts
apps/haa-server/src/http.ts
apps/haa-server/src/server.ts
apps/mcp/src/index.ts
apps/reference-executor/src/index.ts
macos/haa-approver/Sources/HAAApprover/*.swift
scripts/validate-macos-e2e.mjs
scripts/validate-agent-macos-e2e.mjs
```

Inspect tests rather than trusting documentation claims:

```text
tests/*.test.ts
macos/haa-approver/Tests/HAAApproverTests/*.swift
```

## Reproducible automated baseline

Run from a clean checkout:

```bash
node --version
npm --version
npm ci
npm run pack:check
npm test
npx tsc --noEmit
npm audit --omit=dev --audit-level=high

docker build -t haa-review .
docker run -d --name haa-review-run -p 127.0.0.1:8787:8787 -e HAA_DEV_BOOTSTRAP=1 haa-review
curl -fsS http://127.0.0.1:8787/health
docker rm -f haa-review-run
```

On macOS where Swift/Xcode are available:

```bash
swift test --package-path macos/haa-approver
xcodebuild \
  -project macos/haa-approver-app/HAAApprover.xcodeproj \
  -target HAAApprover \
  -configuration Release \
  CODE_SIGNING_ALLOWED=NO \
  build
```

The physical Touch ID gates are evidence from W3/W4 and are repeated separately by W8-T09 after W7-T15. Lack of a physical Mac does not permit a reviewer to infer Secure Enclave attestation beyond the documented assurance level.

## Mandatory adversarial review areas

### A. Identity, roles and provisioning

Attempt to find paths where REQUESTER or EXECUTOR can obtain APPROVER-equivalent authority, nominate itself, read unrelated approval metadata, or use a stale/disabled credential.

### B. Canonicalization and signed bytes

Challenge JSON canonicalization, digest construction, cross-language decoding/display and signature verification. Look for semantically equivalent but byte-different representations, omitted/extra fields, number/string ambiguity and display/signature mismatch.

### C. Challenge/evidence binding

Try request/action/intent/authenticator substitution, foreign challenge digest, replay, revoked authenticator, wrong principal and expired evidence.

### D. Receipt versus execution authority

Prove or falsify that a receipt alone cannot execute. Inspect every executor-facing path and detached-grant verifier.

### E. Atomic consume, idempotency and concurrency

Challenge duplicate execution IDs, different execution IDs, post-approval resource mutation, stale preconditions and retry after side effect.

### F. Authority key lifecycle

Challenge ACTIVE/RETIRED semantics, unknown key IDs, algorithm mismatch, rotation across pre-existing challenge/receipt/grant and rollback/recovery behavior.

### G. Audit integrity

Challenge event mutation, removal, reordering and DBA chain recomputation. State exactly what a signed checkpoint detects and what compromise of the checkpoint signing authority would invalidate.

### H. Backup / recovery

Challenge mismatched database/key ring/private key, overwrite safeguards, restored audit head and authority-key references.

### I. Network / secrets boundary

Challenge non-loopback exposure, TLS assumptions, forwarded headers, rate limiting, API-key leakage, development bootstrap and container defaults.

### J. W8 negative ceremony semantics

Attempt to:

- reject using requester/wrong approver credentials;
- reject the wrong challenge;
- mark a live challenge `CHALLENGE_EXPIRED`;
- use `USER_ESCAPE` after challenge expiry;
- turn close/timeout/error into a claim of biometric or explicit human rejection;
- obtain receipt/grant from any REJECT path;
- confuse challenge expiry with request TTL `EXPIRED`.

## Finding classification

Every finding must use one of:

```text
BLOCKING      exploitable/architectural issue that invalidates production-readiness
P1            high-priority issue; serious but may have a bounded mitigation
P2            improvement/hardening issue without current authority-boundary failure
ACCEPTED-RISK deliberate, accurately documented residual risk with bounded impact
```

Do not report style preferences as security findings.

## Required finding format

```text
ID: HAA-REV-XXX
Severity: BLOCKING | P1 | P2 | ACCEPTED-RISK
Area:
Claim challenged:
Evidence: file/path + symbol/line or reproducible command
Attack/failure scenario:
Observed behavior:
Expected secure behavior:
Recommended remediation:
Regression test required: yes/no
```

## Required final verdict

```text
Reviewed SHA: <sha>
Automated baseline: PASS | FAIL | NOT RUN
BLOCKING findings: <count>
P1 findings: <count>
P2 findings: <count>
Accepted risks: <count>

W7-T05 verdict:
  PASS       only if BLOCKING = 0
  FAIL       if BLOCKING > 0
  INCOMPLETE if required surfaces were not reviewed
```

A PASS closes **W7-T05 only**. W7-T15 still requires the production-readiness checklist to be reconciled against the reviewed SHA and any remediation commits.
