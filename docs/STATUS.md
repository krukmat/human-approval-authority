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
- **W8 Universal ceremony outcomes:** HAA-ONLY future work
- **Product integrations:** PARKED

The canonical task/dependency source is `tasks/manifest.yaml`. The active roadmap is `docs/HAA-ACTIVE-ROADMAP.md`.

## Current quality gates

Current `main` validates:

- committed npm lockfile v3;
- `npm ci` in CI and `npm ci --omit=dev` in Docker;
- publishable `@haa/protocol` and `@haa/sdk` package builds / `npm pack --dry-run`;
- all TypeScript tests, including security/adversarial cases;
- strict `tsc --noEmit`;
- Docker build/start/health smoke;
- Swift package tests and app-wrapper compilation on macOS CI;
- prior physical Secure Enclave / Touch ID / bounded-executor gate.

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

## W8 boundary

W8 remains HAA-only and product-independent. Its target ceremony semantics are:

```text
successful Touch ID   -> APPROVE
Esc                    -> REJECT
window close           -> UNKNOWN
local timeout          -> UNKNOWN
technical interruption -> UNKNOWN
```

`UNKNOWN` is not added to frozen `ApprovalState`; only verified APPROVE evidence may result in `ApprovalReceipt` / `ExecutionGrant`.

## Scope boundaries

Hardware remains deliberately deferred. No external product repository is part of the active HAA roadmap, and parked integration notes do not define HAA core dependencies.
