# Changelog

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
- WebAuthn remains an optional deferred adapter;
- Apple Secure Enclave-backed signing is not represented as remote/platform attestation;
- network-edge TLS/rate limiting remain operator-managed deployment controls;
- administrative credential audit is separate from the request-audit checkpoint chain.

This baseline is the input to W9 external adoption work. W9 must validate HAA from outside the monorepo rather than expanding the core without evidence from a real consumer.
