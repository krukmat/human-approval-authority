# HAA active roadmap

Status: **ACTIVE / HAA-ONLY**

This is the active roadmap for `human-approval-authority` while product integrations and dedicated hardware are deliberately parked.

## Scope boundary

Active work is limited to the universal HAA product:

- protocol compatibility and lifecycle semantics;
- service/API hardening;
- requester/client credential lifecycle;
- authority key lifecycle;
- authenticator assurance and macOS approver behavior;
- audit integrity;
- self-host operational security;
- SDK / executor verification;
- APPROVE / REJECT ceremony semantics;
- HAA-only automated and physical validation.

Out of active scope:

- DubBridge or any other product repository;
- product-specific ActionProfiles;
- provider/model routing;
- hardware POC/hardening (W5/W6);
- WebAuthn spike (W7-T04) unless reprioritized.

## Current baseline

W0-W4 are complete. W5/W6 are deferred/blocked by product priority. W7-T01 through W7-T03 are complete. W7-T05 is awaiting independent/cross-model review. W7-T06 through W7-T14 are complete, leaving W7-T15 blocked only by W7-T05.

HAA protocol v1 is frozen. New work must preserve the existing signed v1 schemas and compatibility contract. `ApprovalState` already contains `REJECTED` and `EXPIRED`.

Therefore:

- terminal ceremony behavior has exactly two operational results: `APPROVE` or `REJECT`;
- only successful positive authenticator evidence may produce `APPROVE`;
- every other terminal ceremony result uses `REJECTED` with a typed reason;
- `USER_ESCAPE` is the only rejection reason that claims an explicit negative human action;
- window close, timeout, challenge expiry and terminal interaction error are fail-closed rejection reasons and do not claim biometric or explicit-human rejection;
- request TTL expiry remains lifecycle `EXPIRED`, distinct from challenge-level `CHALLENGE_EXPIRED` rejection;
- only verified approval evidence may lead to `ApprovalReceipt` and `ExecutionGrant`.

---

# W7 — Software production hardening

Goal: close the current security-review residuals and produce a defensible HAA software baseline before external product integrations.

## W7-T05 — Final independent / cross-model security review

Status: `READY_FOR_EXTERNAL_REVIEW`

Dependencies: `W7-T01`, `W7-T02`, `W7-T03`

Challenge at minimum:

- identity/provisioning assumptions;
- action canonicalization and cross-language signing;
- authenticator assurance claims;
- consume/idempotency race behavior;
- authority-key lifecycle;
- executor trust boundary;
- audit integrity;
- deployment/secrets/network boundary;
- protocol-v1 compatibility rules.

Acceptance: findings are classified as BLOCKING / P1 / P2 / ACCEPTED-RISK and the task closes only when no blocking finding remains.

## W7-T06 — Runtime API schemas and bounded inputs

Dependencies: `W2-T09`, `W7-T01`

Add explicit runtime validation for HTTP request envelopes and bounded sizes for strings, arrays and objects. TypeScript casts must not be the security boundary.

Acceptance:

- malformed/oversized inputs fail before domain execution;
- unknown fields/variants follow an explicit policy;
- negative tests cover every externally writable endpoint;
- behavior remains wire-compatible with protocol v1.

## W7-T07 — Deterministic dependency and build chain

Dependencies: `W7-T02`, `W7-T03`

Deliver:

- committed lockfile;
- deterministic `npm ci` path in CI/Docker;
- reproducible package/build checks;
- documented base-image/version policy.

Acceptance: clean checkout and Docker build resolve the committed dependency graph rather than floating semver ranges.

## W7-T08 — Client credential lifecycle and role separation

Dependencies: `W2-T02`, `W2-T08`, `W7-T01`

Add first-class lifecycle semantics for HAA clients without weakening requester / approver / executor separation.

Minimum scope:

- explicit client role/capability model;
- credential expiry;
- rotation;
- administrative disable/revoke;
- lifecycle audit events;
- no plaintext secret persistence;
- safe CLI/API administration surface.

Acceptance: a leaked/retired credential can be invalidated and replaced without deleting identity history, and agents cannot obtain an approver-equivalent role through ordinary requester APIs.

## W7-T09 — Authority key ring and rotation

Dependencies: `W1-T04`, `W1-T06`, `W7-T01`

Replace single-key operational assumptions with an explicit authority-key lifecycle.

Minimum scope:

- one ACTIVE signing key;
- RETIRED verification keys;
- stable `authorityKeyId` lookup;
- controlled rotation;
- historical receipt/grant verification across rotation;
- rollback/recovery runbook;
- no silent key downgrade.

Acceptance: newly issued objects use the active key while previously issued signed objects remain verifiable under retained trusted keys according to policy.

## W7-T10 — Network edge production profile

Dependencies: `W7-T02`, `W7-T06`

Define and validate the supported network deployment boundary:

- TLS termination requirement;
- trusted reverse-proxy/service-mesh assumptions;
- rate limiting / abuse controls;
- request-size limits;
- forwarded-header trust policy;
- secrets exposure rules;
- loopback/local default remains safe.

Acceptance: self-host documentation and smoke tests clearly distinguish local/internal mode from internet/network-exposed deployment requirements.

## W7-T11 — Audit tamper-evidence

Dependencies: `W2-T08`, `W7-T09`

Keep SQLite as the current transactional store but add a tamper-evident audit strategy.

Preferred first increment:

- deterministic audit-event digest;
- hash chaining or equivalent sequence binding;
- signed periodic checkpoint/export using an explicitly scoped authority mechanism;
- offline verification command;
- documented DBA threat boundary.

Acceptance: post-hoc mutation/removal/reordering of protected audit history is detectable by the verification path.

## W7-T12 — Authenticator assurance model

Dependencies: `W3-T06`, `W7-T01`

Document and encode what HAA v1 can actually claim about authenticators.

Must distinguish:

- authenticated enrollment;
- possession of enrolled key;
- user verification;
- device-bound user verification;
- hardware attestation (not currently proven by HAA v1).

Acceptance: product docs, API terminology and tests do not claim Secure Enclave attestation when only enrollment trust + Secure Enclave-backed signing behavior has been demonstrated.

## W7-T13 — Detached ExecutionGrant verification

Dependencies: `W1-T06`, `W4-T01`, `W7-T03`, `W7-T09`

Add a public verification path for executors that receive an `ExecutionGrant` through an untrusted intermediary.

Verification must cover:

- authority signature/key ID;
- request/action digest;
- executor audience;
- expiry;
- supported schema/algorithm;
- explicit fail-closed error taxonomy.

Acceptance: executor code can verify a detached grant without importing private HAA core internals.

## W7-T14 — Persistence, backup and recovery contract

Dependencies: `W2-T01`, `W7-T02`, `W7-T09`

Preserve SQLite as the supported single-node store for the current product while defining operational recovery.

Deliver:

- explicit no-HA/no-multi-writer claim;
- transactional backup procedure;
- restore procedure;
- authority-key/database consistency checks;
- corruption/failure recovery notes;
- testable backup/restore smoke path.

Acceptance: an operator can restore a self-host instance without silently invalidating authority-key references or audit history.

## W7-T15 — Software production-readiness gate

Dependencies: `W7-T05`, `W7-T06`, `W7-T07`, `W7-T08`, `W7-T09`, `W7-T10`, `W7-T11`, `W7-T12`, `W7-T13`, `W7-T14`

Final HAA-only gate for the software product.

Acceptance:

- all blocking findings closed;
- CI/package/Docker gates green;
- credential rotation validated;
- authority key rotation validated;
- audit verification validated;
- backup/restore validated;
- detached grant verification validated;
- deployment assumptions documented;
- remaining risks explicitly accepted and scoped.

This gate does **not** require hardware, WebAuthn, DubBridge or any other product integration.

---

# W8 — Universal ceremony outcomes

Goal: make HAA's human ceremony semantics explicit and usable independently of any product integration.

The target terminal UX semantics are:

```text
successful Touch ID   -> APPROVE
Esc                    -> REJECT / USER_ESCAPE
window close           -> REJECT / WINDOW_CLOSED
local timeout          -> REJECT / TIMEOUT
challenge expiry       -> REJECT / CHALLENGE_EXPIRED
interaction failure    -> REJECT / INTERACTION_ERROR
```

Actual request TTL expiry remains lifecycle `EXPIRED` and is not a ceremony rejection.

## W8-T01 — Ceremony outcome ADR

Dependencies: `W7-T01`

Freeze the semantic model:

```text
APPROVE = verified positive human authorization
REJECT  = every other terminal ceremony outcome
```

Reason/assurance metadata prevents a fail-closed technical outcome from being mislabeled as explicit human rejection.

Acceptance: only APPROVE can create execution authority; every other terminal ceremony fails closed as REJECT without modifying signed protocol-v1 schemas.

## W8-T02 — Negative-decision provenance and threat model

Dependencies: `W8-T01`, `W7-T12`

Define how negative terminal outcomes are attributed to the trusted approver channel without requiring Touch ID and without allowing a requester/agent to forge the claim.

Must distinguish:

- `USER_ESCAPE` -> `explicit-human-negative-action`;
- close/timeout/challenge-expiry/interaction-error -> `fail-closed-terminal`;
- authenticated control channel/session;
- exact challenge binding;
- denial-of-service implications;
- audit assurance wording.

Acceptance: the design states exactly what each negative reason proves and does not prove.

## W8-T03 — Explicit REJECT service path

Dependencies: `W8-T02`, `W7-T06`, `W7-T08`

Implement rejection using the existing `REJECTED` lifecycle semantics.

Rules:

- reject is challenge/request bound;
- requester/wrong approver cannot manufacture trusted rejection;
- wrong/consumed challenge fails closed;
- rejection reason is allow-listed and validated;
- `CHALLENGE_EXPIRED` is accepted only for an actually expired challenge;
- reject never creates `ApprovalEvidence`, `ApprovalReceipt` or `ExecutionGrant`;
- reason/provenance/assurance are auditable.

## W8-T04 — Fail-closed terminal rejection semantics

Dependencies: `W8-T01`

Define all terminal negative mappings without creating a third ceremony state:

```text
Esc                 -> REJECT / USER_ESCAPE
window close        -> REJECT / WINDOW_CLOSED
local timeout       -> REJECT / TIMEOUT
challenge expiry    -> REJECT / CHALLENGE_EXPIRED
interaction error   -> REJECT / INTERACTION_ERROR
```

Rules:

- all terminal negative outcomes end `REJECTED` when the request itself remains valid;
- only `USER_ESCAPE` claims explicit negative human action;
- all other reasons use fail-closed assurance;
- request TTL expiry remains `EXPIRED`;
- no negative outcome can create execution capability.

## W8-T05 — macOS approver UX

Dependencies: `W8-T03`, `W8-T04`, `W3-T06`

Implement the ceremony UX:

- trusted display remains mandatory;
- approve invokes Touch ID and Secure Enclave signing;
- Esc produces `USER_ESCAPE`;
- close produces `WINDOW_CLOSED`;
- local timeout produces `TIMEOUT`;
- a verified-but-expired challenge produces `CHALLENGE_EXPIRED`;
- terminal authenticator/interaction failure produces `INTERACTION_ERROR`;
- all negative terminal outputs use the rejection path and no positive evidence.

## W8-T06 — SDK / CLI ceremony result contract

Dependencies: `W8-T03`, `W8-T04`, `W7-T03`

Expose a stable two-outcome caller-facing model:

- approved;
- rejected with typed reason/provenance/assurance;
- expired request lifecycle remains visible through request state/errors;
- transport/pre-ceremony validation failures remain errors rather than forged human decisions.

## W8-T07 — Audit and observability semantics

Dependencies: `W8-T03`, `W8-T04`, `W7-T11`

Define the audit representation for terminal rejection while preserving frozen `haa.audit.v1` compatibility.

Use existing `details` extension points for:

```text
challengeDigest
authenticatorId
reason
provenance
assurance
```

Acceptance: an operator can distinguish explicit Escape from close/timeout/expiry/error and from request lifecycle `EXPIRED`, without claiming unsupported human assurance.

## W8-T08 — HAA-only automated ceremony E2E

Dependencies: `W8-T05`, `W8-T06`, `W8-T07`

Automated matrix must prove:

- valid approval -> receipt/grant path succeeds;
- Esc -> REJECT and no grant;
- close -> REJECT and no grant;
- local timeout -> REJECT and no grant;
- interaction error -> REJECT and no grant;
- actual challenge expiry can be classified as `CHALLENGE_EXPIRED` but not forged before expiry;
- actual request TTL -> EXPIRED and no grant;
- stale/wrong challenge -> fail closed;
- replay -> fail closed/idempotent according to existing semantics;
- requester cannot fabricate an approval or trusted rejection provenance.

No external product repository is used.

## W8-T09 — Physical macOS ceremony and compatibility gate

Dependencies: `W8-T08`, `W7-T15`

Run on the real provisioned Apple Silicon path:

1. trusted display + Touch ID -> APPROVE;
2. Esc -> REJECT / USER_ESCAPE;
3. window close -> REJECT / WINDOW_CLOSED;
4. timeout -> REJECT / TIMEOUT;
5. challenge expiry -> REJECT / CHALLENGE_EXPIRED;
6. terminal interaction failure -> REJECT / INTERACTION_ERROR where safely reproducible;
7. only the approval path can produce a usable `ExecutionGrant`;
8. existing W3/W4 physical approval behavior remains regression-safe.

Acceptance: HAA is integration-ready with generic, independently validated human ceremony semantics.

---

# Dependency view

```text
W7-T05 external review

W7-T06 runtime schemas ─────┐
W7-T07 deterministic build │
W7-T08 client lifecycle    │
W7-T09 authority rotation ─┼─> W7-T15 production-readiness gate
W7-T10 network edge        │
W7-T11 audit integrity     │
W7-T12 assurance model     │
W7-T13 detached grants     │
W7-T14 backup/recovery ────┘

W8-T01 ceremony ADR
   ├─> W8-T02 reject provenance -> W8-T03 reject service ─┐
   └─> W8-T04 fail-closed terminal semantics ─────────────┤
                                                           v
                                                        W8-T05 macOS UX
                                                           │
                          W8-T06 SDK/CLI <──────────────────┤
                          W8-T07 audit semantics <──────────┤
                                   │                       │
                                   └──────────┬────────────┘
                                              v
                                           W8-T08
                                              │
                              W7-T15 ─────────┤
                                              v
                                           W8-T09
```

## Active priority

Current order:

1. complete `W7-T05` independent/cross-model review;
2. close `W7-T15` only when W7-T05 has no blocking findings and readiness evidence remains green;
3. execute `W8-T09` on the physical provisioned Mac;
4. keep product integrations parked until this HAA-only baseline is deliberately accepted.
