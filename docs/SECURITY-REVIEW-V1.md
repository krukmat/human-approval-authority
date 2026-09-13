# HAA v1 software security / architecture review

Review date: **2026-09-13**

Decision: **PASS for internal pilot and product-integration work; NOT production-hardening complete**.

An independent cross-model review remains recommended before a production release. This review records the current first-party findings and the code changes made before that independent pass.

## Blocking findings found and resolved

### S1 — Requester could nominate itself as approver

Risk: the product thesis requires a human authority distinct from the requesting agent identity.

Resolution:
- `createApprovalRequest` now rejects `requesterId === approverPrincipalId` with `SELF_APPROVAL_FORBIDDEN`;
- HTTP maps the policy violation to 403;
- regression coverage locks the behavior.

Important boundary: HAA still relies on trusted out-of-band client provisioning. An operator must not give the agent a second credential representing a human principal.

### S2 — Software-only `test-key` verifier was enabled by default

Risk: a production instance could accept generic software-signed evidence with the same application defaults used by tests.

Resolution:
- production defaults now include only supported product authenticator types;
- `test-key` is injected explicitly by unit/integration tests;
- regression coverage verifies it is absent from default verifiers.

### S3 — Any authenticated client could read any request/audit trail

Risk: metadata disclosure across unrelated clients/tenants.

Resolution:
- `getRequest` and `listAudit` now require the authenticated actor to be one of the request participants: requester, approver principal or executor audience;
- outsider access is regression-tested.

## Existing controls reconfirmed

- exact canonical action digest binding;
- signed challenge payload bytes with nonce/expiry;
- trusted display claims derived from signed typed intent;
- ACTIVE authenticator/principal binding;
- executor audience binding;
- precondition/TOCTOU validation;
- atomic approval consumption;
- same-execution-id idempotency after resource mutation;
- different execution ID denied after consumption;
- ApprovalReceipt is audit evidence, not execution authority;
- physical Apple Secure Enclave / Touch ID end-to-end gate passed;
- MCP exposes request/status only, not generic execution;
- self-host image starts with persistent SQLite/authority-key paths and no default production credentials;
- protocol and SDK packages build and pass `npm pack --dry-run`.

## Residual hardening before production

These do not block an internal pilot but should remain explicit roadmap items.

### P1 — Client credential lifecycle / roles

Current client records are identity + API-key hash + enabled flag. There is no first-class role model, expiry, rotation history, administrative disable CLI/API or audit of credential lifecycle.

Recommendation: introduce administrative client lifecycle tooling before multi-team production use. Keep requester/approver/executor separation explicit and auditable.

### P1 — Authority key rotation

A persistent authority key exists, but there is no key ring / overlap period / rotation protocol for previously issued receipts and grants.

Recommendation: define key IDs, active/retired verification keys and a controlled rotation runbook before production.

### P1 — Authenticator assurance / attestation

HAA v1 trusts the authenticated enrollment path plus the declared authenticator type. It does not independently attest that a registered `apple-secure-enclave` key was generated in a Secure Enclave.

Recommendation: document assurance as enrollment-trust-based for v1; evaluate attestation only if the target threat model requires it.

### P1 — Audit tamper resistance

Audit is append-only through the application API but a database administrator can modify SQLite directly.

Recommendation: for compliance/high-assurance deployments add external append-only export, hash chaining, signed checkpoints or another tamper-evident sink.

### P1 — Network edge controls

HAA exposes plain HTTP and relies on deployment infrastructure for TLS. There is no built-in rate limiting.

Recommendation: require TLS termination at a trusted reverse proxy/service mesh and add rate limiting/abuse controls for networked production deployments.

### P2 — Runtime request schemas

HTTP handlers currently rely on TypeScript casts plus downstream domain validation rather than complete Fastify/Zod schemas for every request envelope.

Recommendation: add explicit runtime schemas and bounded string/array/object sizes before exposing HAA to untrusted clients.

### P2 — Dependency/build reproducibility

The current repository does not pin a package-lock in source control. Docker therefore resolves allowed semver ranges at image build time.

Recommendation: commit a lockfile and prefer deterministic `npm ci` / immutable image digests for production releases.

### P2 — Persistence availability

SQLite is intentionally a single-node persistence target.

Recommendation: do not claim HA/multi-writer support. Add a transactional server database adapter only if deployment requirements justify it.

### P2 — Detached grant verification

The reference executor receives its grant directly from HAA and trusts that authenticated/TLS channel. A future workflow that transports grants through an untrusted intermediary should independently verify the authority signature and audience/expiry/action binding.

## Release posture

| Target | Status |
|---|---|
| Local development | PASS |
| Real Mac / Touch ID E2E | PASS |
| Internal self-host pilot | PASS with documented deployment assumptions |
| Future DubBridge integration work | READY after W7 software package gates |
| Internet-exposed production | NOT READY |
| Compliance/high-assurance production | NOT READY |

## Independent review handoff

Before declaring a production release, ask an independent model/reviewer to challenge at minimum:

- identity/provisioning assumptions;
- evidence/authenticator assurance claims;
- action canonicalization and cross-language signing;
- consume/idempotency race behavior;
- authority-key lifecycle;
- executor trust boundary;
- audit integrity;
- self-host deployment/secrets/network boundary;
- v1 compatibility rules.
