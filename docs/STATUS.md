# Implementation status

## Functional status

```text
W0 Foundation                              DONE
W1 Universal core                          DONE
W2 Service / enforcement                   DONE
W3 Apple authenticator                     DONE + physical validation
W4 Agent integration                       DONE + physical bounded-executor validation
W5 Hardware POC                            DEFERRED
W6 Hardware hardening                      BLOCKED by W5
W7 Software production hardening           DONE
W8 Universal ceremony outcomes             DONE + physical macOS gate
W9 Reference integration / adoption        DONE / PASS_WITH_FOLLOWUPS
```

### W7

- independent/cross-model review: `PASS_WITH_FOLLOWUPS`;
- remaining BLOCKING findings: `0`;
- remaining P1 findings: `0`;
- production-readiness gate: DONE;
- accepted W7 code SHA: `7720ac04e5b35637dcc56952925af15386cdc226`.

### W8

- APPROVE / REJECT ceremony semantics: DONE;
- physical macOS ceremony compatibility gate: DONE;
- validated physical SHA: `1bec7bb76f0bb7119045bea6d59ed896364e2895`;
- HAA-only software/ceremony baseline: CLOSED / ACCEPTED.

### W9

```text
W9-T01 Release baseline freeze                 DONE
W9-T02 Minimal external integration contract   DONE
W9-T03 Reference external consumer             DONE
W9-T04 Real ActionProfile                      DONE
W9-T05 External executor integration           DONE_WITH_FOLLOWUP
W9-T06 External integration E2E                DONE + physical macOS/Touch ID
W9-T07 Adoption-gap review                     DONE
W9-T08 Integration-readiness gate              DONE / PASS_WITH_FOLLOWUPS
```

Frozen W9 starting code baseline: `e68b6ad8b8b3901f095e47111aa5545c132cf964`.

Reference external consumer: `krukmat/verifiable-event-ledger`.

Physical W9 external-consumer VEL baseline: `faa3561a0796c088ad4d7a8b6f9eeb79b22d8565`.

The external physical gate proved a real cross-repository requester → HAA → Touch ID → detached-verifying external executor → bounded Git fast-forward side effect, ending in one `CONSUMED` event.

W9 remaining findings are P2/P3 adoption/DX follow-ups only; open BLOCKING findings: `0`; open P1 findings: `0`.

Canonical task/dependency source: `tasks/manifest.yaml`.

W9 plan: `docs/W9-REFERENCE-INTEGRATION.md`.

W9 adoption/readiness review: `docs/W9-ADOPTION-REVIEW.md`.

External integration contract: `docs/EXTERNAL-INTEGRATION.md`.

Release baseline: `docs/RELEASE-BASELINE.md`.

## Accepted quality gates

The closed HAA software baseline and adoption gates have validated:

- committed npm lockfile and deterministic `npm ci` paths;
- publishable `@haa/protocol` / `@haa/sdk` package boundaries;
- runtime security/adversarial tests and strict TypeScript typecheck;
- Docker build/start/health smoke;
- Swift package tests and Xcode app-wrapper compilation;
- CodeQL JavaScript/TypeScript analysis;
- strict request/credential role separation;
- authority-key rotation and ACTIVE-key live grant policy;
- tamper-evident request audit plus signed checkpoints;
- transactional backup/restore consistency checks;
- detached `ExecutionGrant` verification;
- physical Secure Enclave / Touch ID approval;
- MCP requester → human Touch ID → bounded executor scenario;
- APPROVE / REJECT automated ceremony matrix;
- physical APPROVE, Escape, window-close, timeout and challenge-expiry behavior;
- exact-action/precondition/replay/idempotency enforcement;
- request TTL `EXPIRED` remaining distinct from challenge-level `REJECTED / CHALLENGE_EXPIRED`;
- external consumer integration without private HAA imports;
- real `git.merge.v1` trusted display and stale-state binding;
- external Python detached grant verification;
- external bounded Git side effect only after HAA authorization.

## Authority model

Only verified positive approval may lead to execution authority:

```text
trusted display
  -> positive human verification
  -> ApprovalEvidence
  -> ApprovalReceipt
  -> authorizeAndConsume(actualAction, executionId)
  -> ExecutionGrant
  -> executor verification
  -> side effect
```

`ApprovalReceipt` and request state `APPROVED` are never execution bearer capabilities.

Terminal negative ceremony semantics remain:

```text
Esc                      -> REJECT / USER_ESCAPE
window close / Command-W -> REJECT / WINDOW_CLOSED
local timeout            -> REJECT / TIMEOUT
challenge expiry         -> REJECT / CHALLENGE_EXPIRED
interaction failure      -> REJECT / INTERACTION_ERROR
request TTL              -> lifecycle EXPIRED
```

Only `USER_ESCAPE` claims explicit negative human action; all other rejection reasons use fail-closed terminal assurance.

## Residual boundaries accepted for the current baseline

- Apple Secure Enclave-backed signing is not claimed as remote/platform attestation.
- TLS/rate limiting and network-edge protections are operator-managed deployment responsibilities.
- `audit_events` are checkpoint-protected; administrative credential lifecycle audit remains a separate operational stream.
- SQLite remains single-node/single-writer for the current supported deployment model.
- the Python reference executor does not yet automate post-merge same-execution reconciliation; it fails closed and this remains a P2 integration follow-up;
- no official Python HAA SDK exists; the reference integration uses the public HTTP/protocol contract and a local detached verifier;
- hardware authenticator work remains deferred;
- WebAuthn remains optional/deferred.

## Evidence references

- `docs/W7-T05-REVIEW-2026-09-13.md`
- `docs/W7-PRODUCTION-READINESS.md`
- `docs/W8-CEREMONY-OUTCOMES.md`
- `docs/W8-PHYSICAL-CEREMONY-GATE.md`
- `docs/W9-GIT-MERGE-PROFILE-REVIEW.md`
- `docs/W9-ADOPTION-REVIEW.md`
- `docs/RELEASE-BASELINE.md`
- `CHANGELOG.md`
