# Changelog

## Post-baseline optional WebAuthn adapter — 2026-09-17

This work does **not** redefine the frozen HAA integration baseline or protocol-v1 package versions.

Delivered:

- optional WebAuthn authenticator/evidence adapter, disabled by default;
- exact RP ID/origin/credential/challenge binding;
- `UP` + `UV=required` enforcement with P-256/ES256 verification;
- principal-bound single-use registration, authenticator revocation, assertion replay and counter-regression controls;
- strict WebAuthn HTTP input envelopes and bounded credential fields;
- browser approval UI with explicit web-origin display assurance wording;
- physical macOS browser/platform validation on HAA SHA `52d7c8430a0d2508067f44711bc3656ee12e5887` through exact `ExecutionGrant` issuance and one-shot `CONSUMED` state.

Decision: `KEEP_OPTIONAL`.

The native macOS Secure Enclave approver remains the preferred higher-assurance path for high-risk actions because it provides the native trusted-display/device-bound path. WebAuthn remains useful where browser portability and reach justify a web-origin presentation trust boundary. HAA records `user-verified`; it does not claim which local verification modality satisfied WebAuthn UV.

Before broader production promotion, the bounded dependency-free CBOR/WebAuthn parser should be replaced or independently reviewed against a mature implementation and production RP/origin/TLS operations should be validated.

See `docs/W7-T04-WEBAUTHN-SPIKE.md`.

## HAA integration baseline 0.1.0 — 2026-09-15

Immutable code baseline: `e68b6ad8b8b3901f095e47111aa5545c132cf964`

Package versions:

- `@haa/protocol` `1.0.0`
- `@haa/sdk` `0.2.0`
- repository/product baseline `0.1.0`

Delivered baseline:

- frozen protocol-v1 approval/challenge/evidence/receipt/grant contracts;
- authenticated REQUESTER / APPROVER / EXECUTOR role separation;
- strict typed ActionProfiles and canonical exact-action digests;
- atomic `authorizeAndConsume(...)` with one-shot execution semantics;
- detached `ExecutionGrant` verification through the public SDK;
- authority-key rotation and ACTIVE-key enforcement;
- tamper-evident request audit with signed checkpoints;
- deterministic dependency/build path, Docker/self-host packaging and backup/restore contract;
- physically validated macOS Secure Enclave / Touch ID approval path;
- explicit APPROVE / REJECT ceremony semantics with typed fail-closed reasons;
- W8 physical ceremony compatibility gate closed.

Validation references:

- W7 production-ready accepted code SHA: `7720ac04e5b35637dcc56952925af15386cdc226`;
- W8 physical macOS validated SHA: `1bec7bb76f0bb7119045bea6d59ed896364e2895`;
- the integration baseline SHA differs from the W8 physical SHA only in closure/document-control files; the macOS project file was restored to the physically validated signing-neutral form before freezing this baseline.

Known scoped residuals:

- hardware authenticator work remains deferred;
- WebAuthn is now an optional physically validated adapter kept disabled by default;
- Apple Secure Enclave-backed signing is not represented as remote/platform attestation;
- network-edge TLS/rate limiting remain operator-managed deployment controls;
- administrative credential audit is separate from the request-audit checkpoint chain.

This baseline is the input to W9 external adoption work. W9 validates HAA from outside the monorepo rather than expanding the core without evidence from a real consumer.
