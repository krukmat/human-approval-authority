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

- **macOS:** physically validated Touch ID-gated P-256 signing with a device-bound Secure Enclave key.
- **DIY hardware:** deferred by product priority.
- Future authenticators plug into the evidence-verifier boundary without changing core execution semantics.

The HAA core never handles fingerprint images/templates and contains no Apple/ESP32-specific policy logic.

`user-verified-device-bound` describes the supported authenticator path and enrolled device-bound key behavior. HAA v1 does **not** independently perform Apple Secure Enclave/platform attestation; see `docs/AUTHENTICATOR-ASSURANCE.md`.

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
W8      universal ceremony + physical macOS gate     DONE
W9      reference integration / adoption gate        ACTIVE
```

W7 closed with independent review `PASS_WITH_FOLLOWUPS`, zero remaining BLOCKING/P1 findings after remediation. W8 closed on a real Apple Silicon Mac with Secure Enclave / Touch ID and validated APPROVE, rejection semantics and the bounded executor path.

W9 now tests HAA as an **external product** rather than continuing to harden the core speculatively:

```text
W9-T01 release baseline                  DONE
W9-T02 external integration contract     DONE
W9-T03 reference external consumer       READY
W9-T04 real ActionProfile                BLOCKED by T03
W9-T05 external executor                 BLOCKED
W9-T06 external E2E                      BLOCKED
W9-T07 adoption-gap review               BLOCKED
W9-T08 integration-readiness gate        BLOCKED
```

The frozen W9 code baseline is `e68b6ad8b8b3901f095e47111aa5545c132cf964`. See `docs/RELEASE-BASELINE.md` and `docs/W9-REFERENCE-INTEGRATION.md`.

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
```

The physical W8 gate is recorded in `docs/W8-PHYSICAL-CEREMONY-GATE.md`.

## Security posture

HAA is suitable for internal pilot/integration work under its documented trust assumptions. It is not presented as an Internet-exposed/compliance-ready managed service.

Important boundaries remain explicit:

- Secure Enclave-backed signing is not claimed as remote/platform attestation;
- operator-managed edge controls provide TLS/rate limiting/network exposure protection;
- hardware authenticator hardening remains deferred;
- administrative credential audit remains separate from request-audit checkpoint evidence;
- a receipt or `APPROVED` request state never authorizes execution.

## Project control

- Architecture: `docs/ARCHITECTURE.md`
- Protocol v1: `docs/PROTOCOL-V1.md`
- Security invariants: `docs/SECURITY.md`
- Authenticator assurance: `docs/AUTHENTICATOR-ASSURANCE.md`
- Production-readiness gate: `docs/W7-PRODUCTION-READINESS.md`
- W8 ceremony contract: `docs/W8-CEREMONY-OUTCOMES.md`
- W8 physical gate: `docs/W8-PHYSICAL-CEREMONY-GATE.md`
- Frozen release baseline: `docs/RELEASE-BASELINE.md`
- External integration contract: `docs/EXTERNAL-INTEGRATION.md`
- W9 adoption wave: `docs/W9-REFERENCE-INTEGRATION.md`
- Completed HAA-only roadmap: `docs/HAA-ACTIVE-ROADMAP.md`
- Self-hosting: `docs/SELF-HOSTING.md`
- Current status: `docs/STATUS.md`
- Changelog: `CHANGELOG.md`
- Dependency graph/status: `tasks/manifest.yaml`
- Agent working contract: `AGENTS.md`
