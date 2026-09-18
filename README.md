# Human Approval Authority (HAA)

A vendor-neutral human approval authority for agentic workflows. HAA binds human approval to one exact canonical action and produces a short-lived execution grant only after atomic authorization/consumption.

## Trust flow

```text
Requester / Agent
    ↓
ActionSpec → ApprovalIntent → signed ChallengePackage
    ↓
Human-verifying Authenticator
    ↓
ApprovalEvidence → ApprovalReceipt
    ↓
authorizeAndConsume(actualAction, executionId)
    ↓
ExecutionGrant → bounded Executor
```

`ApprovalReceipt` is audit evidence. It is **not** an execution bearer token. A real action can proceed only through `authorizeAndConsume()` and an `ExecutionGrant` bound to the exact action and executor audience.

## Authenticator paths

- **macOS native:** physically validated Touch ID-gated P-256 signing with a device-bound Secure Enclave key; preferred higher-assurance path for high-risk actions.
- **WebAuthn:** physically validated optional browser/platform adapter with `UV=required`; `user-verified` assurance, browser-origin display, disabled by default.
- **DIY hardware:** deferred by product priority.

The HAA core never handles fingerprint images/templates and contains no Apple/ESP32-specific policy logic.

`user-verified-device-bound` describes the native macOS authenticator path and enrolled device-bound key behavior. HAA v1 does **not** independently perform Apple Secure Enclave/platform attestation. The optional WebAuthn path does not claim native trusted display, device binding, specific biometric modality or platform attestation. See `docs/AUTHENTICATOR-ASSURANCE.md` and `docs/W7-T04-WEBAUTHN-SPIKE.md`.

## Ceremony semantics

A terminal HAA ceremony has two operational outcomes:

```text
successful verified positive evidence -> APPROVE
anything else terminal                -> REJECT
```

Negative reasons remain typed so HAA does not overclaim human intent:

```text
USER_ESCAPE       -> explicit-human-negative-action
WINDOW_CLOSED     -> fail-closed-terminal
TIMEOUT           -> fail-closed-terminal
CHALLENGE_EXPIRED -> fail-closed-terminal
INTERACTION_ERROR -> fail-closed-terminal
```

Only APPROVE can lead to `ApprovalReceipt` and `ExecutionGrant`. Real request-TTL expiry remains lifecycle `EXPIRED`, separate from challenge-level rejection.

## Current status

```text
W0-W4   foundation/core/service/Apple/agent path     DONE
W5      hardware POC                                 DEFERRED
W6      hardware hardening                           BLOCKED by W5
W7      software production hardening                DONE
  T04   optional WebAuthn adapter                     DONE / KEEP_OPTIONAL
W8      universal ceremony + physical macOS gate     DONE
W9      reference integration / adoption gate        DONE / PASS_WITH_FOLLOWUPS

S1      external executor recovery                    DONE
S2      official Python SDK                           PARKED / NOT PRIORITIZED
S3      documentation canonicalization                DONE
```

W7 closed with independent review `PASS_WITH_FOLLOWUPS`, zero remaining BLOCKING/P1 findings after remediation. The optional W7-T04 WebAuthn spike later completed its physical browser gate on HAA SHA `52d7c8430a0d2508067f44711bc3656ee12e5887` and was retained as `KEEP_OPTIONAL`.

W8 closed on a real Apple Silicon Mac with Secure Enclave / Touch ID and validated APPROVE, rejection semantics and the bounded executor path.

W9 validated HAA as an external product boundary using `krukmat/verifiable-event-ledger`:

```text
external requester
  -> HAA
  -> physical human ceremony
  -> exact ExecutionGrant
  -> detached-verifying external Python executor
  -> bounded git merge --ff-only side effect
  -> CONSUMED exactly once
```

W9 finished `PASS_WITH_FOLLOWUPS` as its historical gate result. The external-executor recovery follow-up is now closed; the optional Python SDK idea is parked/not prioritized. There are currently **no active non-hardware software tasks**. The frozen W9 starting code baseline is `e68b6ad8b8b3901f095e47111aa5545c132cf964`. See `docs/RELEASE-BASELINE.md`, `docs/W9-REFERENCE-INTEGRATION.md` and `docs/W9-ADOPTION-REVIEW.md`.

## Self-host

```bash
docker compose build
docker compose up -d
```

The default compose deployment binds HAA to `127.0.0.1:8787`, persists SQLite state and the authority private key in separate volumes, and does not require development bootstrap credentials.

See `docs/SELF-HOSTING.md` for client provisioning, key persistence and network-boundary guidance.

## Public TypeScript packages

```bash
npm install
npm run pack:check
```

- `@haa/protocol` — frozen protocol v1 types/runtime metadata (`1.0.0`).
- `@haa/sdk` — typed requester/executor/ceremony client (`0.2.0`) with detached `ExecutionGrant` verification.

External consumers should use only the HTTP API, `@haa/protocol`, `@haa/sdk` and documented authenticator/operator surfaces. Do not import `packages/core`, persistence internals or server implementation code.

See `docs/EXTERNAL-INTEGRATION.md` for the minimum integration contract.

## Local Mac validation

```bash
npm install
npm run validate:macos
npm run validate:agent-macos
npm run validate:macos-ceremony -- --case approve
npm run validate:macos-ceremony -- --case escape
npm run validate:macos-ceremony -- --case window-close
npm run validate:macos-ceremony -- --case timeout
npm run validate:macos-ceremony -- --case challenge-expired
npm run validate:webauthn-macos
```

The physical W8 native ceremony gate is recorded in `docs/W8-PHYSICAL-CEREMONY-GATE.md`. The optional WebAuthn physical gate and adoption decision are recorded in `docs/W7-T04-WEBAUTHN-SPIKE.md`.
