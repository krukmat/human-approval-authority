# W7-T15 software production-readiness gate

Status: **BLOCKED BY W7-T05**

This checklist is the closure contract for W7-T15. It is HAA-only and deliberately does not depend on DubBridge, hardware, WebAuthn or any product integration.

W7-T15 may move to DONE only after an independent W7-T05 review has no BLOCKING findings and the evidence below is green on the accepted commit.

## Gate identity

Record at closure:

```text
Accepted commit SHA:
W7-T05 reviewed SHA:
W7-T05 verdict:
Readiness date:
Operator/reviewer:
```

If the accepted SHA differs from the reviewed SHA, list every security-relevant delta and its review evidence. A large or architectural delta requires a fresh W7-T05 review.

## G1 — Build / package / test chain

Required:

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

Result: `PENDING W7-T05 FINAL SHA`

## G2 — Container / self-host baseline

Required:

```bash
docker build -t haa-readiness .
docker run -d --name haa-readiness-run \
  -p 127.0.0.1:8787:8787 \
  -e HAA_DEV_BOOTSTRAP=1 \
  haa-readiness
curl -fsS http://127.0.0.1:8787/health
docker rm -f haa-readiness-run
```

Verify local profile remains loopback-safe and production edge assumptions remain documented in `docs/NETWORK-EDGE.md`.

Result: `PENDING W7-T05 FINAL SHA`

## G3 — Client credential lifecycle

Evidence must prove:

- role separation REQUESTER / APPROVER / EXECUTOR;
- API keys persisted only as hashes;
- expiry enforced;
- rotation invalidates old credential;
- disable/revoke works without deleting identity history;
- lifecycle actions are operationally auditable.

Primary evidence: client lifecycle tests + `docs/SELF-HOSTING.md`.

Result: `IMPLEMENTED / REVERIFY ON FINAL SHA`

## G4 — Authority key lifecycle

Evidence must prove:

- exactly one ACTIVE signing key;
- RETIRED public keys remain usable for legitimate historical verification;
- new signatures use only ACTIVE key;
- unknown/mismatched algorithms fail closed;
- challenge issued before rotation remains verifiable under retained key policy;
- rotation/recovery behavior is documented.

Primary evidence: authority-keyring tests + self-hosting/recovery docs.

Result: `IMPLEMENTED / REVERIFY ON FINAL SHA`

## G5 — Audit integrity

Evidence must prove:

- deterministic event digest/hash chain;
- mutation is detected;
- removal/reordering is detected;
- signed checkpoint detects a DBA recomputing the local chain after tampering;
- offline verification path works;
- threat boundary does not claim protection after compromise of the checkpoint-signing authority.

Primary evidence: audit integrity tests + `docs/AUDIT-INTEGRITY.md`.

Result: `IMPLEMENTED / REVERIFY ON FINAL SHA`

## G6 — Backup / restore

Evidence must prove:

- transactional SQLite snapshot;
- authority private key/key ring bundled consistently;
- checksums and active key ID verified;
- audit head consistency verified;
- tampered bundle rejected;
- accidental overwrite refused unless explicit;
- restored instance does not silently invalidate authority references.

Primary evidence: backup/recovery tests + `docs/BACKUP-RECOVERY.md`.

Result: `IMPLEMENTED / REVERIFY ON FINAL SHA`

## G7 — Detached execution grant verification

Evidence must prove strict verification of:

- schema/shape;
- authority key ID and algorithm;
- authority signature;
- request ID;
- optional exact execution ID;
- action digest;
- executor audience;
- expiry;
- unknown key and extra-field fail-closed behavior.

Primary evidence: detached grant tests + public `@haa/sdk` API.

Result: `IMPLEMENTED / REVERIFY ON FINAL SHA`

## G8 — Authenticator assurance

Documentation and code must distinguish:

```text
authenticated enrollment
enrolled-key possession
user verification
device-bound user verification
hardware/platform attestation
```

HAA v1 must not claim Apple platform attestation when it only proves the documented enrollment + Secure Enclave-backed signing behavior.

Result: `IMPLEMENTED / REVERIFY ON FINAL SHA`

## G9 — W8 ceremony authority boundary

Automated evidence must prove:

```text
successful positive evidence -> APPROVE -> receipt/grant possible
USER_ESCAPE                  -> REJECTED -> no receipt/grant
WINDOW_CLOSED                -> REJECTED -> no receipt/grant
TIMEOUT                      -> REJECTED -> no receipt/grant
CHALLENGE_EXPIRED            -> REJECTED -> no receipt/grant
INTERACTION_ERROR            -> REJECTED -> no receipt/grant
request TTL                  -> EXPIRED  -> no receipt/grant
```

Reason/assurance must prevent close/timeout/error from being described as biometric or explicit human rejection.

Result: `IMPLEMENTED / REVERIFY ON FINAL SHA`

## G10 — Independent review

Required artifact: completed `docs/W7-INDEPENDENT-REVIEW-PACKET.md` output from an independent reviewer/model.

Closure rule:

```text
BLOCKING = 0
```

P1/P2 may remain only if their disposition is explicit and does not contradict the W7-T15 acceptance criteria. Accepted risks must be bounded and documented.

Result: `BLOCKED — W7-T05 PENDING`

## Final closure statement

Use only after every gate is reconciled:

```text
W7-T15: PASS
Accepted SHA: <sha>
Independent review: PASS, BLOCKING=0
CI/package/Docker: PASS
Credential lifecycle: PASS
Authority rotation: PASS
Audit integrity: PASS
Backup/restore: PASS
Detached grants: PASS
Authenticator assurance: PASS
W8 automated authority boundary: PASS
Residual risks: <references>
```

Until that statement is supportable by evidence, `tasks/manifest.yaml` must keep W7-T15 as `BLOCKED`.
