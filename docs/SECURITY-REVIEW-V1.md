# HAA v1 software security / architecture review

Initial review date: **2026-09-13**

Current decision: **engineering hardening complete through W7-T14; independent/cross-model review still required before W7 production-readiness can close**.

This document records the first-party findings and their remediation. It is not the independent review required by W7-T05.

## Blocking findings found and resolved

### S1 — Requester could nominate itself as approver — RESOLVED

Risk: the product thesis requires a human authority distinct from the requesting agent identity.

Resolution:
- `createApprovalRequest` rejects `requesterId === approverPrincipalId` with `SELF_APPROVAL_FORBIDDEN`;
- HTTP maps the policy violation to 403;
- regression coverage locks the behavior.

Boundary: HAA still relies on trusted provisioning. An operator must not give an agent a second credential representing a human approver principal.

### S2 — Software-only `test-key` verifier was enabled by default — RESOLVED

Resolution:
- production defaults contain only supported product authenticator types;
- `test-key` is test-only through explicit injection;
- regression coverage verifies it is absent from defaults.

### S3 — Any authenticated client could read unrelated request/audit metadata — RESOLVED

Resolution:
- request/audit reads require requester, approver principal or executor audience participation;
- outsider access is regression-tested.

## Existing controls reconfirmed

- canonical exact-action digest binding;
- signed challenge payload bytes with nonce/expiry;
- trusted display claims from signed typed intent;
- ACTIVE authenticator/principal binding;
- requester/approver separation;
- executor audience binding;
- precondition/TOCTOU validation;
- atomic approval consumption;
- same-execution-id idempotency after resource mutation;
- different execution ID denied after consumption;
- ApprovalReceipt is audit evidence, never execution authority;
- physical Apple Secure Enclave / Touch ID gate passed;
- MCP exposes request/status only, not generic execution;
- self-host package has persistent DB/authority-key paths and no default production credentials;
- protocol and SDK packages build and package independently.

## Production-hardening follow-up

The original review identified the following residuals. They are now mapped to completed W7 tasks.

### P1 — Client credential lifecycle / roles — RESOLVED BY W7-T08

Delivered:
- explicit `REQUESTER` / `APPROVER` / `EXECUTOR` roles;
- role enforcement at sensitive application boundaries;
- credential expiry, rotation and disable/revoke;
- credential-version history without plaintext secret storage;
- administrative lifecycle audit;
- provisioning/rotation/disable CLI and documentation.

### P1 — Authority key rotation — RESOLVED BY W7-T09

Delivered:
- one ACTIVE authority signing key;
- RETIRED public verification keys;
- `authorityKeyId` resolution;
- controlled rotation CLI and persisted key-ring metadata;
- historical challenge/artifact verification across rotation;
- fail-closed key/ring mismatch behavior and recovery runbook.

### P1 — Authenticator assurance / attestation — RESOLVED BY W7-T12

HAA now explicitly distinguishes enrollment trust, key possession, user verification, device-bound user verification and hardware attestation. HAA v1 does **not** claim Apple platform/Secure Enclave attestation when it has only demonstrated enrolled Secure-Enclave-backed signing behavior.

### P1 — Audit tamper resistance — RESOLVED BY W7-T11 FOR REQUEST AUDIT

Delivered:
- transactional hash chain over protocol request `audit_events`;
- signed `haa.audit-checkpoint.v1` checkpoints;
- ACTIVE/RETIRED authority-key verification of checkpoints;
- offline audit verification command;
- adversarial tests for mutation, deletion/reordering and DBA hash-chain recomputation.

Boundary: `admin_audit_events` remains a separate operational stream and is not represented as request-audit checkpoint evidence in this increment.

### P1 — Network edge controls — RESOLVED BY W7-T10

Delivered:
- default `local` profile requires loopback;
- explicit `edge` profile for non-loopback binds;
- TLS, rate-limit, request-size, ACL/secrets/logging responsibilities documented at the trusted ingress boundary;
- Fastify does not trust forwarded headers as identity inputs;
- direct plain-HTTP exposure to an untrusted network is unsupported.

### P2 — Runtime request schemas — RESOLVED BY W7-T06

HTTP inputs use strict bounded runtime validation before domain execution, including body size, identifiers, strings, nested JSON and exact request shapes.

### P2 — Dependency/build reproducibility — RESOLVED BY W7-T07

`package-lock.json` v3 is committed. CI uses `npm ci`; Docker uses `npm ci --omit=dev`. Build/package/test/typecheck/container gates run from the committed graph. Base-image policy is documented separately.

### P2 — Persistence availability — BOUNDED BY W7-T14

SQLite remains intentionally single-node/single-writer. W7-T14 adds a transactional backup/verified restore contract rather than claiming HA or multi-writer semantics.

### P2 — Detached grant verification — RESOLVED BY W7-T13

The public TypeScript SDK verifies detached `ExecutionGrant` signature/key ID, schema/algorithm, request/action/execution/audience binding and expiry against ACTIVE/RETIRED authority public keys.

## New hardening controls added after the initial review

- coordinated DB + authority-key-ring backup bundle with checksums and audit-head binding;
- pre/post restore consistency verification;
- explicit network deployment profiles;
- public authority key-ring endpoint;
- deterministic npm installation path;
- tamper-evident audit verification tooling.

## Current release posture

| Target | Status |
|---|---|
| Local development | PASS |
| Real Mac / Touch ID E2E | PASS |
| Internal self-host pilot | PASS with documented deployment assumptions |
| HAA engineering hardening W7-T06..T14 | PASS |
| W7 production-readiness gate | BLOCKED on independent W7-T05 review |
| Internet-exposed production | NOT DECLARED READY until W7-T05/T15 close |
| Compliance/high-assurance deployment | Requires deployment-specific threat/compliance review |

## Independent review requirement

The independent reviewer must assess the **current** post-hardening code, not only this first-party report. Challenge at minimum:

- identity/provisioning and client-role escalation assumptions;
- action canonicalization / signed-byte compatibility;
- authenticator assurance wording;
- challenge/evidence behavior across authority-key rotation;
- receipt/grant key lifecycle and detached verification;
- consume/idempotency/concurrency behavior;
- audit hash-chain/checkpoint migration and DBA threat model;
- backup/key-ring/database consistency and recovery failure modes;
- self-host network/TLS/rate-limit/secrets boundary;
- protocol-v1 compatibility and downgrade/fail-closed rules.

Classify findings as `BLOCKING`, `P1`, `P2` or `ACCEPTED-RISK`. W7-T05 may close only when no BLOCKING finding remains.
