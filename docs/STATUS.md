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
W7 Software production hardening           DONE + optional WebAuthn spike closed
W8 Universal ceremony outcomes             DONE + physical macOS gate
W9 Reference integration / adoption        DONE / PASS_WITH_FOLLOWUPS
```

## Canonical current software posture

`tasks/manifest.yaml` is canonical for W0-W9 task/dependency status. This document is canonical for current software follow-up priority and parked/optional directions.

```text
S1 External executor recovery      DONE
S2 Official Python SDK             PARKED / NOT PRIORITIZED
S3 Documentation canonicalization  DONE
active non-hardware software       NONE
```

S3 was documentation-only. It synchronized roadmap, plan, status, W9 review, README, manifest ownership wording and changelog without changing HAA protocol, architecture or runtime behavior.

### W7

The accepted software production baseline remains closed. The optional WebAuthn spike has now also completed without reopening protocol v1 or the accepted production baseline.

- independent/cross-model review: `PASS_WITH_FOLLOWUPS`;
- remaining BLOCKING findings: `0`;
- remaining P1 findings: `0`;
- production-readiness gate: DONE;
- accepted W7 production baseline SHA: `7720ac04e5b35637dcc56952925af15386cdc226`.

Optional WebAuthn spike status:

```text
W7-T04    Optional WebAuthn adapter spike      DONE / KEEP_OPTIONAL
W7-T04.1  Assurance contract                   DONE
W7-T04.2  Authenticator model                  DONE
W7-T04.3  Registration ceremony                DONE
W7-T04.4  HAA challenge binding                DONE
W7-T04.5  Assertion verifier                   DONE
W7-T04.6  Evidence adapter                     DONE
W7-T04.7  Browser approval UI                  DONE
W7-T04.8  Negative-path automated tests        DONE
W7-T04.9  Physical browser gate                DONE / PASS
W7-T04.10 Adoption decision                    DONE / KEEP_OPTIONAL
```

Physical WebAuthn validation ran on HAA SHA `52d7c8430a0d2508067f44711bc3656ee12e5887` and proved:

```text
PENDING request
  -> executor blocked
  -> physical browser/platform WebAuthn ceremony
  -> HAA user-verified evidence
  -> exact ExecutionGrant
  -> CONSUMED exactly once
```

The WebAuthn adapter remains disabled by default and preserves protocol v1. Its assurance remains intentionally lower than the native macOS approver:

```text
WebAuthn evidence       user-verified
human-visible display  authenticated web origin / DOM
platform attestation   not claimed
native trusted display not claimed
specific UV modality   not protocol-attested
```

Decision rationale and physical evidence: `docs/W7-T04-WEBAUTHN-SPIKE.md`.

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
W9-T05 External executor integration           DONE
W9-T06 External integration E2E                DONE + physical macOS/Touch ID
W9-T07 Adoption-gap review                     DONE
W9-T08 Integration-readiness gate              DONE / PASS_WITH_FOLLOWUPS
```

Frozen W9 starting code baseline: `e68b6ad8b8b3901f095e47111aa5545c132cf964`.

Reference external consumer: `krukmat/verifiable-event-ledger`.

Physical W9 external-consumer VEL baseline: `faa3561a0796c088ad4d7a8b6f9eeb79b22d8565`.

The external physical gate proved a real cross-repository requester → HAA → Touch ID → detached-verifying external executor → bounded Git fast-forward side effect, ending in one `CONSUMED` event.

W9 executor-recovery follow-up is closed in `krukmat/verifiable-event-ledger` at `0e942480b2b8a9b5a0fb2f17c9ea5de4161a28a5` with CI green. The former P2 Python SDK/DX idea is now PARKED / NOT PRIORITIZED, so there is no active W9 software follow-up. Open BLOCKING findings: `0`; open P1 findings: `0`.

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

The optional WebAuthn adapter has additionally validated:

- principal-bound single-use WebAuthn registration;
- exact RP/origin binding;
- `UP` and `UV` enforcement;
- exact HAA challenge-digest binding;
- P-256/ES256 assertion verification;
- wrong-origin, wrong-challenge, wrong-RP and wrong-credential denial;
- authenticator revocation and assertion replay denial;
- signature-counter regression denial when counters are exposed;
- `VerifiedEvidence` mapping to `user-verified` without protocol-v1 changes;
- physical browser/platform WebAuthn approval through exact grant issuance and one-shot consumption.

## Authority model

Only verified positive approval may lead to execution authority:

```text
human-visible action
  -> positive human verification
  -> ApprovalEvidence
  -> ApprovalReceipt
  -> authorizeAndConsume(actualAction, executionId)
  -> ExecutionGrant
  -> executor verification
  -> side effect
```

For the native macOS approver, the action is rendered in the native trusted display. For the WebAuthn adapter, the display is web-origin/DOM protected and must not be represented as equivalent assurance.

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
- the Python reference executor now automates bounded same-`executionId` post-merge reconciliation: an already-applied approved source is accepted only after HAA returns and the executor detached-verifies the original grant; a different execution ID remains denied;
- no official Python HAA SDK exists; S2 is PARKED / NOT PRIORITIZED because the current reference integration is already functional through the public HTTP/protocol contract;
- hardware authenticator work remains deferred;
- WebAuthn is DONE / `KEEP_OPTIONAL` and disabled by default; it provides `user-verified` assurance with a browser-origin display rather than the native trusted-display/device-bound assurance path;
- before broader WebAuthn production promotion, the bounded dependency-free CBOR/WebAuthn parser should be replaced or independently reviewed against a mature implementation and production RP/origin/TLS operations should be validated.

## Evidence references

- `docs/W7-T04-WEBAUTHN-SPIKE.md`
- `docs/W7-T05-REVIEW-2026-09-13.md`
- `docs/W7-PRODUCTION-READINESS.md`
- `docs/W8-CEREMONY-OUTCOMES.md`
- `docs/W8-PHYSICAL-CEREMONY-GATE.md`
- `docs/W9-GIT-MERGE-PROFILE-REVIEW.md`
- `docs/W9-ADOPTION-REVIEW.md`
- `docs/RELEASE-BASELINE.md`
- `CHANGELOG.md`
