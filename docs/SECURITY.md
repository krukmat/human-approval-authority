# Security invariants

1. Exact-action binding: approval is valid only for one canonical ActionSpec digest.
2. Freshness: every ceremony uses a cryptographically random nonce and expiry.
3. Trusted presentation: visible fields derive from signed/canonical intent data, never free requester prose.
4. Authenticator independence: core types never branch on biometric or device technology.
5. No biometric data in HAA: no images, templates, minutiae or raw sensor frames.
6. Registered-key binding: evidence only from an ACTIVE authenticator bound to the expected principal.
7. Requester identity: anonymous clients cannot create approval requests.
8. Human separation: the authenticated requester cannot nominate the same principal identity as approver (`requesterId != approverPrincipalId`).
9. Trusted client provisioning: requester/approver/executor credentials are provisioned out of band. The security model assumes an agent receives only its intended requester/executor credentials and cannot provision a second credential that represents a human principal.
10. Production verifier defaults: software-only `test-key` evidence is never enabled by default; tests must inject it explicitly.
11. Participant confidentiality: request and audit metadata are readable only by the requester, approver principal or executor audience bound into the intent.
12. Executor audience: approvals constrain the executor to reduce confused-deputy attacks.
13. TOCTOU protection: mutable resources carry immutable/version preconditions and are rechecked before execution.
14. Atomic single use: authorizeAndConsume verifies and consumes state in one transaction.
15. Idempotent retry: same executionId can return the prior result; a new ID after consumption is denied.
16. Receipt is not authority: receipt is audit evidence and cannot bypass server state.
17. Device loss/revocation: revoke and re-enroll; do not recover private keys.
18. Hardware firmware is TCB: secure element alone does not prove fingerprint use.
19. Assurance terminology: `user-verified-device-bound` describes the supported authenticator path and enrolled device-bound key behavior; it is not a claim of remote platform/hardware attestation.
20. Fail closed on unknown profile/version, invalid signature, malformed/ambiguous payload, or unsupported evidence.
21. Terminal ceremony authority: only successful verified positive authenticator evidence can produce APPROVE; every other terminal ceremony outcome is REJECT and can never create `ApprovalReceipt` or `ExecutionGrant`.
22. Negative-assurance truthfulness: `USER_ESCAPE` may claim `explicit-human-negative-action`; `WINDOW_CLOSED`, `TIMEOUT`, `CHALLENGE_EXPIRED` and `INTERACTION_ERROR` are only `fail-closed-terminal` outcomes and must not be described as biometric or explicit human rejection.
23. Expiry separation: challenge-level `CHALLENGE_EXPIRED` rejection is distinct from request-TTL lifecycle `EXPIRED`.

## Current trust assumptions

- HAA client provisioning is an administrative boundary. Compromise of the operator that provisions a human principal can defeat identity separation by issuing additional credentials.
- Authenticator assurance currently trusts the enrollment path and registered authenticator type. HAA v1 verifies evidence against the enrolled public key but does not independently attest Apple Secure Enclave provenance.
- Normal application/persistence APIs enforce append-only request audit behavior. A database administrator with direct SQLite write access can mutate storage, but event hash chaining plus a previously trusted signed audit checkpoint makes protected post-hoc mutation/removal/reordering — including local chain recomputation — detectable relative to that checkpoint. Compromise of the authority/checkpoint signing key remains inside the TCB and can undermine future checkpoint trust.
- Administrative credential-lifecycle audit is separate from the request `audit_events` checkpoint chain unless explicitly documented otherwise.
- TLS is expected to be provided by the deployment boundary (reverse proxy/service mesh) when HAA is accessed over a network.
- SQLite is the current single-node/single-writer persistence target; HA/multi-writer deployment is outside v0.x scope.

See `docs/AUTHENTICATOR-ASSURANCE.md`, `docs/AUDIT-INTEGRITY.md` and `docs/W8-CEREMONY-OUTCOMES.md` for detailed assurance boundaries.
