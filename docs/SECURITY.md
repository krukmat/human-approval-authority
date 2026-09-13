# Security invariants

1. Exact-action binding: approval is valid only for one canonical ActionSpec digest.
2. Freshness: every ceremony uses a cryptographically random nonce and expiry.
3. Trusted presentation: visible fields derive from signed/canonical intent data, never free requester prose.
4. Authenticator independence: core types never branch on biometric or device technology.
5. No biometric data in HAA: no images, templates, minutiae or raw sensor frames.
6. Registered-key binding: evidence only from an ACTIVE authenticator bound to the expected principal.
7. Requester identity: anonymous clients cannot create approval requests.
8. Executor audience: approvals constrain the executor to reduce confused-deputy attacks.
9. TOCTOU protection: mutable resources carry immutable/version preconditions and are rechecked before execution.
10. Atomic single use: authorizeAndConsume verifies and consumes state in one transaction.
11. Idempotent retry: same executionId can return the prior result; a new ID after consumption is denied.
12. Receipt is not authority: receipt is audit evidence and cannot bypass server state.
13. Device loss/revocation: revoke and re-enroll; do not recover private keys.
14. Hardware firmware is TCB: secure element alone does not prove fingerprint use.
15. Fail closed on unknown profile/version, invalid signature, expired challenge or ambiguous payload.
